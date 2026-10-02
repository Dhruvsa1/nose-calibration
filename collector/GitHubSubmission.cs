using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace NoseCalibration;
internal static class GitHubSubmission
{
    internal const string Researcher = "Dhruvsa1";
    internal const long ResearcherId = 135009056;
    internal const string RecipientKeySha256 = "d23bfc4486b4a270db2a479de1b9f2dee6907d7ae4113f3110633bc763009661";
    const int MaxEnvelope = 31 * 1024 * 1024, MaxJson = 2 * 1024 * 1024;
    sealed class RequestFailure(HttpStatusCode status) : InvalidOperationException("GitHub request failed (HTTP " + (int)status + "). Your recording and upload state remain local; retry sharing.")
    {
        internal HttpStatusCode Status { get; } = status;
    }
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
    internal sealed record UploadState(int Version, long AccountId, string SessionId, string ZipSha256, string EnvelopeSha256,
        long? RepositoryId = null, bool CreationPending = false, DateTimeOffset? CreationStartedAt = null, bool Complete = false);
    static string Digest(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void SaveState(string path, UploadState state)
    {
        string temp = path + ".tmp"; File.WriteAllText(temp, JsonSerializer.Serialize(state)); File.Move(temp, path, true);
    }
    internal static void VerifyRepo(JsonElement repo, long accountId, string name, long? repositoryId)
    {
        if (!repo.GetProperty("private").GetBoolean() || repo.GetProperty("owner").GetProperty("id").GetInt64() != accountId ||
            repo.GetProperty("owner").GetProperty("type").GetString() != "User" || repo.GetProperty("name").GetString() != name ||
            repo.GetProperty("id").GetInt64() <= 0 || repositoryId.HasValue && repo.GetProperty("id").GetInt64() != repositoryId)
            throw new InvalidOperationException("Submission repository identity or privacy changed. Sharing stopped.");
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
        using var handler = new HttpClientHandler { AllowAutoRedirect = false };
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromMinutes(5) };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("NoseCalibration/0.1");
        return await UploadCore(zip, session, http, publicKeyPath, cancellation, authorization.RequireToken, publicKey.ExportSubjectPublicKeyInfoPem());
    }
    // Injectable HTTP client allows offline recovery tests. Production handler forbids redirects.
    internal static async Task<string> UploadCore(string zip, string session, HttpClient http, string publicKeyPath, CancellationToken cancellation = default, Func<string>? tokenProvider = null, string? verifiedPublicKey = null)
    {
        cancellation.ThrowIfCancellationRequested();
        string id = Path.GetFileName(Path.TrimEndingDirectorySeparator(session)), name = "nose-calibration-submission-" + id;
        if (!Regex.IsMatch(id, "^[a-f0-9]{32}$")) throw new InvalidDataException("Invalid session ID");
        using var uploadLock = new FileStream(Path.Combine(session, "upload.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        if (new FileInfo(zip).Length > 30 * 1024 * 1024) throw new InvalidOperationException("This recording exceeds the 30 MB sharing limit.");
        async Task<(HttpStatusCode status, byte[] bytes)> Request(HttpMethod method, string path, object? body = null, bool raw = false)
        {
            cancellation.ThrowIfCancellationRequested();
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromMinutes(5));
            using var request = new HttpRequestMessage(method, "https://api.github.com" + path);
            request.Headers.Accept.ParseAdd(raw ? "application/vnd.github.raw+json" : "application/vnd.github+json");
            request.Headers.Add("X-GitHub-Api-Version", "2022-11-28");
            if (body != null) request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
            if (tokenProvider != null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tokenProvider());
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            if (response.StatusCode == HttpStatusCode.NotFound && method == HttpMethod.Get) return (response.StatusCode, Array.Empty<byte>());
            if (!response.IsSuccessStatusCode) throw new RequestFailure(response.StatusCode);
            return (response.StatusCode, await ReadBounded(response.Content, raw ? MaxEnvelope : MaxJson, timeout.Token));
        }
        async Task<JsonElement?> Api(HttpMethod method, string path, object? body = null)
        {
            var result = await Request(method, path, body);
            if (result.status == HttpStatusCode.NotFound) return null;
            using var document = JsonDocument.Parse(result.bytes.Length == 0 ? "{}"u8.ToArray() : result.bytes);
            return document.RootElement.Clone();
        }
        var user = await Api(HttpMethod.Get, "/user") ?? throw new InvalidOperationException("GitHub account unavailable.");
        long accountId = user.GetProperty("id").GetInt64(); string login = user.GetProperty("login").GetString()!;
        if (accountId <= 0 || !Regex.IsMatch(login, "^[A-Za-z0-9-]+$")) throw new InvalidDataException("Invalid GitHub account");
        string stateFile = Path.Combine(session, "upload-state.json"), envelopeFile = Path.Combine(session, "submission.nose");
        byte[] plaintext = await File.ReadAllBytesAsync(zip, cancellation); byte[] envelope; UploadState state;
        try
        {
            if (plaintext.Length > 30 * 1024 * 1024) throw new InvalidDataException("Recording size changed beyond limit");
            string zipDigest = Digest(plaintext);
            if (File.Exists(stateFile))
            {
                if (new FileInfo(stateFile).Length > 16384) throw new InvalidDataException("Invalid upload state");
                state = JsonSerializer.Deserialize<UploadState>(await File.ReadAllTextAsync(stateFile, cancellation)) ?? throw new InvalidDataException("Invalid upload state");
                if (state.Version != 2 || state.AccountId != accountId || state.SessionId != id || state.ZipSha256 != zipDigest ||
                    state.RepositoryId is <= 0 || state.CreationPending && state.CreationStartedAt == null)
                    throw new InvalidOperationException("Upload state belongs to a different account, recording, or unsupported earlier version. No remote changes made.");
                if (new FileInfo(envelopeFile).Length > MaxEnvelope) throw new InvalidDataException("Invalid saved envelope size");
                envelope = await File.ReadAllBytesAsync(envelopeFile, cancellation);
                if (Digest(envelope) != state.EnvelopeSha256) throw new InvalidDataException("Saved encrypted submission changed");
            }
            else
            {
                envelope = Encrypt(plaintext, id, accountId, verifiedPublicKey ?? await File.ReadAllTextAsync(publicKeyPath, cancellation));
                // A crash before state commit creates only a local orphan, before any remote write.
                await File.WriteAllBytesAsync(envelopeFile + ".tmp", envelope, cancellation); File.Move(envelopeFile + ".tmp", envelopeFile, true);
                state = new UploadState(2, accountId, id, zipDigest, Digest(envelope)); SaveState(stateFile, state);
            }
        }
        finally { CryptographicOperations.ZeroMemory(plaintext); }
        string byName = "/repos/" + login + "/" + name;
        JsonElement repo;
        if (state.RepositoryId.HasValue)
            repo = await Api(HttpMethod.Get, "/repositories/" + state.RepositoryId) ?? throw new InvalidOperationException("Pinned submission repository no longer exists.");
        else
        {
            // A lost create response leaves no immutable repository identity to trust.
            // Names and timestamps cannot prove that a repository was not replaced.
            if (state.CreationPending)
                throw new InvalidOperationException("Repository creation was not confirmed and its immutable ID was not saved. Automatic retry is blocked. Open local recordings, find this session's encrypted submission.nose, and arrange a secure handoff with the organizer. Keep the plaintext ZIP private.");
            var existing = await Api(HttpMethod.Get, byName);
            if (existing.HasValue)
            {
                throw new InvalidOperationException("A repository already uses this submission name; refusing to adopt it. Your recording is preserved locally; start a new session or contact the organizer.");
            }
            else
            {
                cancellation.ThrowIfCancellationRequested();
                state = state with { CreationPending = true, CreationStartedAt = DateTimeOffset.UtcNow }; SaveState(stateFile, state);
                try
                {
                    repo = await Api(HttpMethod.Post, "/user/repos", new { name, @private = true, description = "Private encrypted Nose Calibration submission", has_issues = false, has_wiki = false, auto_init = false })
                        ?? throw new InvalidOperationException();
                }
                catch (RequestFailure failure) when ((int)failure.Status is >= 400 and < 500 && failure.Status != HttpStatusCode.RequestTimeout)
                {
                    // A received client-error response confirms rejection. A timeout, lost
                    // response, server error, or invalid success body is still ambiguous.
                    state = state with { CreationPending = false, CreationStartedAt = null };
                    SaveState(stateFile, state);
                    throw;
                }
                catch (OperationCanceledException) { throw; }
                catch
                {
                    throw new InvalidOperationException("Repository creation could not be confirmed. Automatic retry is blocked. Open local recordings, find this session's encrypted submission.nose, and arrange a secure handoff with the organizer. Keep the plaintext ZIP private.");
                }
            }
            VerifyRepo(repo, accountId, name, null);
            state = state with { RepositoryId = repo.GetProperty("id").GetInt64(), CreationPending = false }; SaveState(stateFile, state);
        }
        VerifyRepo(repo, accountId, name, state.RepositoryId);
        string repository = "/repositories/" + state.RepositoryId;
        string blobSha;
        using (var blob = new MemoryStream())
        { blob.Write(Encoding.ASCII.GetBytes("blob " + envelope.Length + "\0")); blob.Write(envelope); blobSha = Convert.ToHexString(SHA1.HashData(blob.ToArray())).ToLowerInvariant(); }
        async Task<bool> VerifyPayload()
        {
            var content = await Api(HttpMethod.Get, repository + "/contents/submission.nose");
            if (!content.HasValue) return false;
            var c = content.Value;
            if (c.GetProperty("type").GetString() != "file" || c.GetProperty("path").GetString() != "submission.nose" || c.GetProperty("size").GetInt64() != envelope.Length || c.GetProperty("sha").GetString() != blobSha)
                throw new InvalidOperationException("Remote submission differs from the saved encrypted payload; refusing to overwrite it.");
            var remote = await Request(HttpMethod.Get, repository + "/git/blobs/" + blobSha, raw: true);
            if (remote.status == HttpStatusCode.NotFound || remote.bytes.Length != envelope.Length || Digest(remote.bytes) != state.EnvelopeSha256)
                throw new InvalidOperationException("Remote encrypted payload verification failed.");
            return true;
        }
        if (!await VerifyPayload())
        {
            if (state.Complete) throw new InvalidOperationException("A completed remote submission was removed. No replacement uploaded.");
            await Api(HttpMethod.Put, repository + "/contents/submission.nose", new { message = "Submit encrypted calibration recording", content = Convert.ToBase64String(envelope) });
            if (!await VerifyPayload()) throw new InvalidOperationException("Upload not yet verified. Retry sharing; the same encrypted payload will be reused.");
        }
        VerifyRepo(await Api(HttpMethod.Get, repository) ?? throw new InvalidOperationException("Repository unavailable"), accountId, name, state.RepositoryId);
        if (accountId != ResearcherId)
        {
            var researcher = await Api(HttpMethod.Get, "/users/" + Researcher) ?? throw new InvalidOperationException("Organizer unavailable");
            if (researcher.GetProperty("id").GetInt64() != ResearcherId) throw new InvalidOperationException("Organizer identity changed. Sharing stopped.");
            // Personal repositories grant collaborators write access, as the consent UI discloses.
            var invitation = await Api(HttpMethod.Put, repository + "/collaborators/" + Researcher, new { permission = "push" });
            if (invitation.HasValue && invitation.Value.TryGetProperty("invitee", out var invitee))
            {
                if (invitee.GetProperty("id").GetInt64() != ResearcherId || invitation.Value.GetProperty("permissions").GetString() != "write")
                    throw new InvalidOperationException("Organizer write-access invitation could not be verified.");
            }
            else
            {
                var permission = await Api(HttpMethod.Get, repository + "/collaborators/" + Researcher + "/permission") ?? throw new InvalidOperationException("Organizer permission unavailable");
                if (permission.GetProperty("user").GetProperty("id").GetInt64() != ResearcherId || permission.GetProperty("permission").GetString() != "write")
                    throw new InvalidOperationException("Organizer write access could not be verified.");
            }
        }
        VerifyRepo(await Api(HttpMethod.Get, repository) ?? throw new InvalidOperationException("Repository unavailable"), accountId, name, state.RepositoryId);
        cancellation.ThrowIfCancellationRequested();
        SaveState(stateFile, state with { Complete = true });
        return "https://github.com/" + login + "/" + name;
    }
}
