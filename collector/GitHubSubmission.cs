using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace NoseCalibration;
// Uploads to the participant's one selected private repository through the
// GitHub App user token (contents write + metadata read). It never creates
// repositories, invites collaborators, or supplies a blob sha, so it cannot
// overwrite an existing remote file.
internal static class GitHubSubmission
{
    internal const string Researcher = "Dhruvsa1";
    internal const long ResearcherId = 135009056;
    internal const string RecipientKeySha256 = "d23bfc4486b4a270db2a479de1b9f2dee6907d7ae4113f3110633bc763009661";
    internal const int StateVersion = 3;
    const int MaxEnvelope = 31 * 1024 * 1024, MaxJson = 2 * 1024 * 1024, MaxState = 16384;
    const string Preserved = " Your recording and encrypted file remain on this computer.";
    sealed class RequestFailure(HttpStatusCode status) : InvalidOperationException("GitHub request failed (HTTP " + (int)status + ")." + Preserved + " Retry sharing.")
    {
        internal HttpStatusCode Status { get; } = status;
    }
    // The encrypted file is uploaded and verified, but organizer access is not
    // confirmed. Pending invitations need Administration permission to list, so
    // the participant retries after the organizer accepts.
    internal sealed class OrganizerAccessPending() : InvalidOperationException("Your encrypted submission was uploaded and verified, but organizer " + Researcher + " does not have access to your nose-calibration-submissions repository yet. If you have not invited " + Researcher + ", add them as a collaborator in the repository settings. If you already did, the organizer still needs to accept; this app cannot see pending invitations. Share again later to confirm; the same encrypted file is reused.");

    internal static byte[] Encrypt(byte[] plain, string sessionId, long accountId, string publicKey)
    {
        byte[] key = RandomNumberGenerator.GetBytes(32), nonce = RandomNumberGenerator.GetBytes(12), tag = new byte[16], encrypted = new byte[plain.Length];
        string aadText = $"nose-calibration:1:{sessionId}:{accountId}";
        try
        {
            using var aes = new AesGcm(key, 16); aes.Encrypt(nonce, plain, encrypted, tag, Encoding.UTF8.GetBytes(aadText));
            using var rsa = RSA.Create(); rsa.ImportFromPem(publicKey);
            var header = JsonSerializer.Serialize(new { version = 1, sessionId, accountId, aad = aadText, wrappedKey = Convert.ToBase64String(rsa.Encrypt(key, RSAEncryptionPadding.OaepSHA256)), nonce = Convert.ToBase64String(nonce), tag = Convert.ToBase64String(tag) });
            using var stream = new MemoryStream(); stream.Write(Encoding.UTF8.GetBytes("NOSE1\n" + header + "\n")); stream.Write(encrypted); return stream.ToArray();
        }
        finally { CryptographicOperations.ZeroMemory(key); }
    }
    // Version 3: one reusable selected repository, immutable per-session path.
    // RepositoryId is pinned when the state is first saved and never changes.
    internal sealed record UploadState(int Version, string SessionId, long AccountId, long RepositoryId, string RemotePath,
        string ZipSha256, string EnvelopeSha256, bool RemoteWriteStarted = false, bool Uploaded = false, bool OrganizerVerified = false);
    static readonly JsonSerializerOptions StrictState = new() { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    internal static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException("Ambiguous JSON response or upload state.");
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectDuplicateProperties(item);
    }
    internal static string RemotePath(string sessionId) => "submissions/" + sessionId + "/submission.nose";
    static string Digest(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void SaveState(string path, UploadState state)
    {
        string temp = path + ".tmp"; File.WriteAllText(temp, JsonSerializer.Serialize(state)); File.Move(temp, path, true);
    }
    static UploadState? LoadState(string path, string sessionId)
    {
        if (!File.Exists(path)) return null;
        const string legacy = "This session's saved upload state is from an earlier or unknown sharing version and cannot be moved to the selected repository automatically. No remote changes were made." + Preserved + " Contact the organizer.";
        if (new FileInfo(path).Length > MaxState) throw new InvalidDataException(legacy);
        string text = File.ReadAllText(path);
        try
        {
            using (var probe = JsonDocument.Parse(text, new JsonDocumentOptions { MaxDepth = 4 }))
            {
                RejectDuplicateProperties(probe.RootElement);
                if (probe.RootElement.ValueKind != JsonValueKind.Object || !probe.RootElement.TryGetProperty("Version", out var v) || !v.TryGetInt32(out int version) || version != StateVersion)
                    throw new InvalidDataException();
            }
            var state = JsonSerializer.Deserialize<UploadState>(text, StrictState) ?? throw new InvalidDataException();
            if (state.SessionId != sessionId || state.RemotePath != RemotePath(sessionId) || state.AccountId <= 0 || state.RepositoryId <= 0 ||
                state.ZipSha256 is not { Length: 64 } || state.EnvelopeSha256 is not { Length: 64 } ||
                !Regex.IsMatch(state.ZipSha256 + state.EnvelopeSha256, "\\A[a-f0-9]{128}\\z") || state.Uploaded && !state.RemoteWriteStarted)
                throw new InvalidDataException();
            return state;
        }
        catch { throw new InvalidDataException(legacy); }
    }
    internal static void VerifyRepo(JsonElement repo, GitHubAppAccess.VerifiedRepository expected)
    {
        var owner = repo.GetProperty("owner");
        if (repo.GetProperty("id").GetInt64() != expected.RepositoryId || repo.GetProperty("name").GetString() != GitHubAppAccess.RepositoryName ||
            repo.GetProperty("private").ValueKind != JsonValueKind.True || repo.GetProperty("visibility").GetString() != "private" ||
            owner.GetProperty("id").GetInt64() != expected.AccountId || owner.GetProperty("type").GetString() != "User" ||
            repo.GetProperty("archived").ValueKind != JsonValueKind.False || repo.GetProperty("disabled").ValueKind != JsonValueKind.False)
            throw new InvalidOperationException("Your nose-calibration-submissions repository is no longer private, personal, active, or the same repository. Sharing stopped." + Preserved);
    }
    internal static async Task<byte[]> ReadBounded(HttpContent content, int limit, CancellationToken token)
    {
        if (content.Headers.ContentLength > limit) throw new InvalidDataException("GitHub response exceeds the size limit.");
        using var stream = await content.ReadAsStreamAsync(token); using var result = new MemoryStream();
        byte[] buffer = new byte[65536]; int count;
        while ((count = await stream.ReadAsync(buffer, token)) > 0)
        { if (result.Length + count > limit) throw new InvalidDataException("GitHub response exceeds the size limit."); result.Write(buffer, 0, count); }
        return result.ToArray();
    }
    internal static async Task<string> Upload(string zip, string session, GitHubDeviceAuth.Authorization authorization, CancellationToken cancellation = default)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellation, authorization.Lifetime);
        cancellation = lifetime.Token;
        cancellation.ThrowIfCancellationRequested();
        string publicKeyPath = Path.Combine(AppContext.BaseDirectory, "public-key.pem");
        using var publicKey = RSA.Create(); publicKey.ImportFromPem(await File.ReadAllTextAsync(publicKeyPath, cancellation));
        if (publicKey.KeySize != 3072 || Digest(publicKey.ExportSubjectPublicKeyInfo()) != RecipientKeySha256) throw new InvalidDataException("Recipient key verification failed. Reinstall the official package.");
        using var handler = new HttpClientHandler { AllowAutoRedirect = false, UseCookies = false };
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromMinutes(5) };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("NoseCalibration/0.1");
        return await UploadCore(zip, session, http, authorization.Repository, authorization.RevalidateRepository,
            authorization.RequireToken, publicKey.ExportSubjectPublicKeyInfoPem(), cancellation);
    }
    // Injectable HTTP client and revalidation allow offline tests. Production handler forbids redirects.
    internal static async Task<string> UploadCore(string zip, string session, HttpClient http, GitHubAppAccess.VerifiedRepository expected,
        Func<CancellationToken, Task<GitHubAppAccess.VerifiedRepository>> revalidate, Func<string> tokenProvider, string verifiedPublicKey, CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        string id = Path.GetFileName(Path.TrimEndingDirectorySeparator(session));
        if (!Regex.IsMatch(id, "\\A[a-f0-9]{32}\\z")) throw new InvalidDataException("Invalid session ID");
        string remotePath = RemotePath(id);
        using var uploadLock = new FileStream(Path.Combine(session, "upload.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        if (new FileInfo(zip).Length > 30 * 1024 * 1024) throw new InvalidOperationException("This recording exceeds the 30 MB sharing limit.");
        string stateFile = Path.Combine(session, "upload-state.json"), envelopeFile = Path.Combine(session, "submission.nose"), stagedEnvelope = envelopeFile + ".tmp";
        // Local checks run before any request: legacy or foreign state fails closed offline.
        var saved = LoadState(stateFile, id);
        if (saved == null && File.Exists(envelopeFile))
            throw new InvalidOperationException("An encrypted submission exists for this session without matching upload state, so it was not replaced and nothing was uploaded." + Preserved + " Contact the organizer.");

        // Fresh identity and full installation inventory; any drift from the
        // sign-in record (account, installation, repository, permissions) stops sharing.
        async Task<GitHubAppAccess.VerifiedRepository> Reverify()
        {
            var current = await revalidate(cancellation);
            cancellation.ThrowIfCancellationRequested();
            if (current != expected || current.Name != GitHubAppAccess.RepositoryName || current.AccountId <= 0 || current.RepositoryId <= 0 ||
                !Regex.IsMatch(current.OwnerLogin, "\\A[A-Za-z0-9][A-Za-z0-9-]{0,38}\\z"))
                throw new InvalidOperationException("GitHub App repository access changed since sign-in. Sign in again; nothing further was uploaded." + Preserved);
            return current;
        }
        var verified = await Reverify();

        byte[] plaintext = await File.ReadAllBytesAsync(zip, cancellation); byte[] envelope; UploadState state;
        try
        {
            if (plaintext.Length > 30 * 1024 * 1024) throw new InvalidDataException("Recording size changed beyond limit");
            string zipDigest = Digest(plaintext);
            if (saved != null)
            {
                state = saved;
                if (state.AccountId != verified.AccountId)
                    throw new InvalidOperationException("This session was prepared for a different GitHub account. Sign in with the original account; no remote changes were made." + Preserved);
                if (state.ZipSha256 != zipDigest) throw new InvalidDataException("The original recording ZIP changed after sharing began. Nothing was uploaded." + Preserved);
                // The destination is pinned when state is first saved. A recreated
                // repository with the same name is a different destination.
                if (state.RepositoryId != verified.RepositoryId)
                    throw new InvalidOperationException("Your nose-calibration-submissions repository is not the one this session was prepared for (it was replaced or reselected). It will not be sent to a different repository automatically." + Preserved + " Contact the organizer.");
                if (!File.Exists(envelopeFile) && File.Exists(stagedEnvelope)) File.Move(stagedEnvelope, envelopeFile);
                if (new FileInfo(envelopeFile).Length > MaxEnvelope) throw new InvalidDataException("Invalid saved envelope size");
                envelope = await File.ReadAllBytesAsync(envelopeFile, cancellation);
                if (Digest(envelope) != state.EnvelopeSha256) throw new InvalidDataException("Saved encrypted submission changed. Nothing was uploaded.");
            }
            else
            {
                envelope = Encrypt(plaintext, id, verified.AccountId, verifiedPublicKey);
                // The final envelope name appears only after its state commits, so a
                // stateless submission.nose is never ours to replace.
                await File.WriteAllBytesAsync(stagedEnvelope, envelope, cancellation);
                state = new UploadState(StateVersion, id, verified.AccountId, verified.RepositoryId, remotePath, zipDigest, Digest(envelope));
                SaveState(stateFile, state); File.Move(stagedEnvelope, envelopeFile);
            }
        }
        finally { CryptographicOperations.ZeroMemory(plaintext); }

        string repository = "/repositories/" + verified.RepositoryId, contentPath = repository + "/contents/" + remotePath;
        async Task<(HttpStatusCode status, byte[] bytes)> Request(HttpMethod method, string path, object? body = null, bool raw = false, bool single = false)
        {
            cancellation.ThrowIfCancellationRequested();
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromMinutes(5));
            using var request = new HttpRequestMessage(method, "https://api.github.com" + path);
            // Contents responses over 1 MB require the object media type for
            // metadata; payload integrity is checked separately with raw blobs.
            bool contentsMetadata = method == HttpMethod.Get && path == contentPath;
            request.Headers.Accept.ParseAdd(raw ? "application/vnd.github.raw+json" : contentsMetadata ? "application/vnd.github.object+json" : "application/vnd.github+json");
            request.Headers.Add("X-GitHub-Api-Version", "2022-11-28");
            if (body != null) request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tokenProvider());
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            if (response.StatusCode == HttpStatusCode.NotFound && method == HttpMethod.Get) return (response.StatusCode, Array.Empty<byte>());
            if (!response.IsSuccessStatusCode) throw new RequestFailure(response.StatusCode);
            // A listing that does not fit one page cannot prove who has access.
            if (single && response.Headers.Contains("Link")) throw new InvalidDataException("GitHub returned a paginated list; sharing stopped.");
            return (response.StatusCode, await ReadBounded(response.Content, raw ? MaxEnvelope : MaxJson, timeout.Token));
        }
        async Task<JsonElement?> Api(HttpMethod method, string path, object? body = null, bool single = false)
        {
            var result = await Request(method, path, body, single: single);
            if (result.status == HttpStatusCode.NotFound) return null;
            using var document = JsonDocument.Parse(result.bytes.Length == 0 ? "{}"u8.ToArray() : result.bytes, new JsonDocumentOptions { MaxDepth = 16 });
            RejectDuplicateProperties(document.RootElement);
            return document.RootElement.Clone();
        }
        async Task CheckRepository() => VerifyRepo(await Api(HttpMethod.Get, repository) ?? throw new InvalidOperationException("Your nose-calibration-submissions repository is unavailable." + Preserved), verified);
        // Collaborator listing needs only Metadata read. Anyone besides the owner and
        // the numerically pinned organizer stops sharing. Returns organizer write access.
        async Task<bool> CheckCollaborators()
        {
            var list = await Api(HttpMethod.Get, repository + "/collaborators?affiliation=all&per_page=100", single: true) ?? throw new InvalidOperationException("Repository collaborators unavailable." + Preserved);
            if (list.ValueKind != JsonValueKind.Array || list.GetArrayLength() >= 100) throw new InvalidDataException("Unexpected collaborator list; sharing stopped.");
            bool organizer = false;
            foreach (var person in list.EnumerateArray())
            {
                long personId = person.GetProperty("id").GetInt64();
                if (personId == verified.AccountId) continue;
                if (personId != ResearcherId)
                    throw new InvalidOperationException("Your nose-calibration-submissions repository has a collaborator other than organizer " + Researcher + ". Remove other collaborators, then share again." + Preserved);
                var p = person.GetProperty("permissions");
                organizer = p.GetProperty("push").ValueKind == JsonValueKind.True && p.GetProperty("pull").ValueKind == JsonValueKind.True;
            }
            return organizer;
        }
        string blobSha;
        using (var blob = new MemoryStream())
        { blob.Write(Encoding.ASCII.GetBytes("blob " + envelope.Length + "\0")); blob.Write(envelope); blobSha = Convert.ToHexString(SHA1.HashData(blob.ToArray())).ToLowerInvariant(); }
        async Task<bool> VerifyPayload()
        {
            var content = await Api(HttpMethod.Get, contentPath);
            if (!content.HasValue) return false;
            var c = content.Value;
            if (c.ValueKind != JsonValueKind.Object || c.GetProperty("type").GetString() != "file" || c.GetProperty("path").GetString() != remotePath ||
                c.GetProperty("size").GetInt64() != envelope.Length || c.GetProperty("sha").GetString() != blobSha)
                throw new InvalidOperationException("A different file already exists at this session's path in your repository; it was not overwritten." + Preserved + " Contact the organizer.");
            var remote = await Request(HttpMethod.Get, repository + "/git/blobs/" + blobSha, raw: true);
            if (remote.status == HttpStatusCode.NotFound || remote.bytes.Length != envelope.Length || Digest(remote.bytes) != state.EnvelopeSha256)
                throw new InvalidOperationException("Remote encrypted payload verification failed." + Preserved);
            return true;
        }

        await CheckRepository();
        await CheckCollaborators();
        if (!await VerifyPayload())
        {
            if (state.Uploaded) throw new InvalidOperationException("A completed remote submission was removed. No replacement was uploaded." + Preserved + " Contact the organizer.");
            cancellation.ThrowIfCancellationRequested();
            state = state with { RemoteWriteStarted = true }; SaveState(stateFile, state);
            // Installation scope can change live; reverify with nothing between this and the write.
            await Reverify();
            try
            {
                // No sha: GitHub rejects the write if the path already exists. The noreply
                // committer keeps the participant's commit email out of the history.
                await Api(HttpMethod.Put, contentPath, new { message = "Add encrypted calibration submission " + id, content = Convert.ToBase64String(envelope),
                    committer = new { name = verified.OwnerLogin, email = verified.AccountId + "+" + verified.OwnerLogin + "@users.noreply.github.com" } });
            }
            catch (RequestFailure failure) when (failure.Status is HttpStatusCode.Conflict or HttpStatusCode.UnprocessableEntity)
            {
                // Existing path or a concurrent commit; verification below decides.
            }
            catch (OperationCanceledException) { throw; }
            catch (RequestFailure) { throw; }
            catch
            {
                throw new InvalidOperationException("Upload outcome could not be confirmed. Share again: the same encrypted file will be verified and reused, never overwritten." + Preserved);
            }
            if (!await VerifyPayload()) throw new InvalidOperationException("Upload not yet verified. Share again; the same encrypted file will be reused." + Preserved);
        }
        state = state with { Uploaded = true }; SaveState(stateFile, state);
        await Reverify();
        await CheckRepository();
        bool organizerAccess = await CheckCollaborators();
        if (verified.AccountId != ResearcherId && !organizerAccess) throw new OrganizerAccessPending();
        cancellation.ThrowIfCancellationRequested();
        SaveState(stateFile, state with { OrganizerVerified = true });
        return "https://github.com/" + verified.OwnerLogin + "/" + GitHubAppAccess.RepositoryName;
    }
}
