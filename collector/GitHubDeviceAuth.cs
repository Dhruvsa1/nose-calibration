using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

namespace NoseCalibration;

// Device flow for this application's pinned GitHub App. No credentials are persisted.
internal sealed class GitHubDeviceAuth : IDisposable
{
    internal sealed record Account(long Id, string Login);
    const string VerificationUrl = "https://github.com/login/device";
    internal const string ClientId = GitHubAppAccess.PinnedClientId;
    const int ResponseLimit = 65536;
    readonly object gate = new();
    readonly string clientId;
    readonly GitHubAppAccess.Registration registration;
    GitHubAppAccess.VerifiedRepository? repository;
    readonly HttpClient http;
    readonly Action<Uri> openBrowser;
    readonly Func<TimeSpan, CancellationToken, Task> delay;
    readonly Func<DateTimeOffset> now;
    readonly Func<TimeSpan, Action, IDisposable> scheduleExpiry;
    CancellationTokenSource? pending;
    CancellationTokenSource? authorizationLifetime;
    IDisposable? expiryTimer;
    string? token;
    DateTimeOffset? tokenExpires;
    Account? account;
    bool disposed;

    internal GitHubDeviceAuth(string configPath, HttpMessageHandler? handler = null,
        Action<Uri>? openBrowser = null,
        Func<TimeSpan, CancellationToken, Task>? delay = null,
        Func<DateTimeOffset>? now = null,
        Func<TimeSpan, Action, IDisposable>? scheduleExpiry = null)
    {
        try
        {
            using var input = File.OpenRead(configPath);
            if (input.Length > 4096) throw new InvalidDataException();
            using var config = JsonDocument.Parse(input, new JsonDocumentOptions { MaxDepth = 4 });
            registration = GitHubAppAccess.ReadRegistration(config.RootElement, handler != null);
            clientId = registration.ClientId;
        }
        catch { throw new GitHubAppAccess.AccessException("app_unconfigured", "This installation has no verified GitHub App configuration. Contact the organizer."); }
        http = new HttpClient(handler ?? new HttpClientHandler { AllowAutoRedirect = false, UseCookies = false }) { Timeout = TimeSpan.FromSeconds(30) };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("NoseCalibration/0.1");
        this.openBrowser = openBrowser ?? (uri => Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true }));
        this.delay = delay ?? ((duration, cancellation) => Task.Delay(duration, cancellation));
        this.now = now ?? (() => DateTimeOffset.UtcNow);
        this.scheduleExpiry = scheduleExpiry ?? ((duration, expire) => new System.Threading.Timer(_ => expire(), null, duration, Timeout.InfiniteTimeSpan));
    }

    internal Account? CurrentAccount { get { lock (gate) { Expire(); return account; } } }
    void ClearAuthorization()
    {
        token = null; account = null; repository = null; tokenExpires = null;
        expiryTimer?.Dispose(); expiryTimer = null;
        var lifetime = authorizationLifetime; authorizationLifetime = null;
        if (lifetime != null) { lifetime.Cancel(); lifetime.Dispose(); }
    }
    void Expire() { if (tokenExpires.HasValue && now() >= tokenExpires) ClearAuthorization(); }
    // Carries a revocable lifetime, never a cached token string. Each request
    // checks the current expiry again even if a timer callback is delayed.
    internal sealed class Authorization
    {
        readonly GitHubDeviceAuth owner;
        internal CancellationToken Lifetime { get; }
        internal GitHubAppAccess.VerifiedRepository Repository { get; }
        internal Authorization(GitHubDeviceAuth owner, CancellationToken lifetime) { this.owner = owner; Lifetime = lifetime; Repository = owner.repository ?? throw new InvalidOperationException("Verify the selected repository before sharing."); }
        internal Task<GitHubAppAccess.VerifiedRepository> RevalidateRepository(CancellationToken ct = default) => owner.RevalidateRepository(this,ct);
        internal bool OwnedBy(GitHubDeviceAuth candidate) => ReferenceEquals(owner,candidate);
        internal string RequireToken()
        {
            lock (owner.gate)
            {
                owner.Expire(); Lifetime.ThrowIfCancellationRequested();
                if (owner.authorizationLifetime == null || owner.authorizationLifetime.Token != Lifetime) throw new OperationCanceledException();
                return owner.RequireToken();
            }
        }
    }
    internal Authorization AcquireAuthorization()
    {
        lock (gate) { RequireToken(); return new Authorization(this, authorizationLifetime!.Token); }
    }
    internal string RequireToken()
    {
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this); Expire();
            return token ?? throw new InvalidOperationException("Sign in to GitHub in this app before sharing. Sign-in is not retained after the app closes.");
        }
    }
    internal void Disconnect()
    {
        lock (gate) { ClearAuthorization(); pending?.Cancel(); }
    }
    internal async Task<Account> SignIn(Action<string> status, CancellationToken cancellationToken = default)
    {
        CancellationTokenSource flow;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (pending != null) throw new InvalidOperationException("GitHub sign-in is already in progress.");
            ClearAuthorization();
            flow = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            flow.CancelAfter(TimeSpan.FromMinutes(15)); pending = flow;
        }
        try
        {
            var ct = flow.Token;
            DateTimeOffset overallDeadline = now().AddMinutes(15);
            using var device = await Request("https://github.com/login/device/code", new Dictionary<string, string> { ["client_id"] = clientId }, null, ct);
            var d = device.RootElement;
            string code = Text(d, "device_code"), userCode = Text(d, "user_code");
            if (!Regex.IsMatch(code, "\\A[a-fA-F0-9]{40}\\z") || !Regex.IsMatch(userCode, "\\A[A-Z0-9]{4}-[A-Z0-9]{4}\\z") || Text(d, "verification_uri") != VerificationUrl)
                throw new InvalidDataException();
            int expires = d.GetProperty("expires_in").GetInt32();
            int interval = d.GetProperty("interval").GetInt32();
            if (expires is < 1 or > 900 || interval is < 1 or > 900) throw new InvalidDataException();
            DateTimeOffset deadline = now().AddSeconds(expires);
            if (deadline > overallDeadline) deadline = overallDeadline;
            TimeSpan remaining = deadline - now();
            if (remaining <= TimeSpan.Zero) throw new OperationCanceledException();
            flow.CancelAfter(remaining);
            status("GitHub device code: " + userCode + ". Open " + VerificationUrl + ". Authorize the GitHub App only for your private nose-calibration-submissions repository. Signing in uploads no recording.");
            ct.ThrowIfCancellationRequested();
            try { openBrowser(new Uri(VerificationUrl)); }
            catch { status("Open " + VerificationUrl + " in your browser and enter the displayed device code."); }
            while (true)
            {
                await delay(TimeSpan.FromSeconds(interval), ct);
                ct.ThrowIfCancellationRequested();
                if (now() >= deadline) throw new OperationCanceledException();
                using var response = await Request("https://github.com/login/oauth/access_token", new Dictionary<string, string> {
                    ["client_id"] = clientId, ["device_code"] = code, ["grant_type"] = "urn:ietf:params:oauth:grant-type:device_code" }, null, ct);
                var r = response.RootElement;
                if (r.TryGetProperty("error", out var error))
                {
                    switch (error.GetString())
                    {
                        case "authorization_pending": continue;
                        case "slow_down": interval = checked(interval + 5); continue;
                        case "access_denied": throw new InvalidOperationException("GitHub authorization was declined. No recording was uploaded.");
                        case "expired_token": throw new OperationCanceledException();
                        default: throw new InvalidOperationException("GitHub device authorization failed. Check the app registration or retry sign-in.");
                    }
                }
                string received = Text(r, "access_token");
                if (!Regex.IsMatch(received, "\\Aghu_[A-Za-z0-9]{20,508}\\z") || !Text(r, "token_type").Equals("bearer", StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
                if (r.TryGetProperty("scope", out var scope) && (scope.ValueKind != JsonValueKind.String || scope.GetString() != ""))
                    throw new GitHubAppAccess.AccessException("scope_expansion", "Broad GitHub OAuth scopes are not accepted. Use the selected-repository GitHub App.");
                // Local lifetime never exceeds the app's eight-hour policy, even
                // if GitHub omits expiry or a future registration changes it.
                DateTimeOffset? expiry = now().AddHours(8);
                if (r.TryGetProperty("expires_in", out var lifetime))
                {
                    long seconds = lifetime.GetInt64(); if (seconds is < 1 or > 31536000) throw new InvalidDataException();
                    expiry = now().AddSeconds(Math.Min(seconds, 8 * 60 * 60));
                }
                response.Dispose(); // Drop and wipe unused refresh-token bytes before further network requests.
                using var identity = await Request("https://api.github.com/user", null, received, ct);
                var u = identity.RootElement;
                long id = u.GetProperty("id").GetInt64(); string login = Text(u, "login");
                if (id <= 0 || !Regex.IsMatch(login, "\\A[A-Za-z0-9][A-Za-z0-9-]{0,38}\\z") || Text(u, "type") != "User") throw new InvalidDataException();
                var verified = new Account(id, login);
                var verifiedRepository = await GitHubAppAccess.Verify(registration,id,login,
                    (url,cancel)=>Request(url,null,received,cancel,rejectPagination:true),ct);
                lock (gate)
                {
                    ct.ThrowIfCancellationRequested();
                    if (disposed || now() >= deadline || expiry.HasValue && now() >= expiry) throw new OperationCanceledException();
                    token = received; account = verified; repository = verifiedRepository; tokenExpires = expiry;
                    var active = new CancellationTokenSource(); authorizationLifetime = active;
                    TimeSpan activeFor = expiry!.Value - now();
                    if (activeFor < TimeSpan.Zero) activeFor = TimeSpan.Zero;
                    expiryTimer = scheduleExpiry(activeFor, () =>
                    {
                        lock (gate) { if (ReferenceEquals(authorizationLifetime, active)) ClearAuthorization(); }
                    });
                }
                return verified;
            }
        }
        catch (OperationCanceledException) { throw new InvalidOperationException("GitHub sign-in was cancelled or expired. Sign in again when ready."); }
        catch (TransientRequestException) { throw new TransientRequestException(retained:false); }
        catch (InvalidOperationException) { throw; }
        catch { throw new InvalidOperationException("GitHub sign-in failed or returned an invalid response. Retry when ready."); }
        finally
        {
            lock (gate) { if (ReferenceEquals(pending, flow)) pending = null; }
            flow.Dispose();
        }
    }
    internal sealed class TransientRequestException : InvalidOperationException
    {
        internal TransientRequestException(bool retained=true) : base(retained
            ? "GitHub is temporarily unavailable. Your sign-in is retained; retry sharing when ready. [github_temporarily_unavailable]"
            : "GitHub is temporarily unavailable. Sign-in did not complete; try signing in again when ready. [github_temporarily_unavailable]") {}
    }
    internal async Task<GitHubAppAccess.VerifiedRepository> RevalidateRepository(Authorization authorization, CancellationToken cancellationToken = default)
    {
        if (!authorization.OwnedBy(this)) throw new InvalidOperationException("Authorization belongs to another sign-in.");
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken,authorization.Lifetime);
        try
        {
            using var identity=await Request("https://api.github.com/user",null,authorization.RequireToken(),linked.Token);
            var u=identity.RootElement; var expected=authorization.Repository;
            if(u.GetProperty("id").GetInt64()!=expected.AccountId || Text(u,"type")!="User" ||
                !string.Equals(Text(u,"login"),expected.OwnerLogin,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException();
            var verified=await GitHubAppAccess.Verify(registration,expected.AccountId,expected.OwnerLogin,
                (url,ct)=>Request(url,null,authorization.RequireToken(),ct,rejectPagination:true),linked.Token);
            authorization.RequireToken();
            if(verified!=expected)throw new InvalidDataException();
            return verified;
        }
        catch (OperationCanceledException) { throw; }
        catch (TransientRequestException) { throw; }
        catch (HttpRequestException) { throw new TransientRequestException(); }
        catch (IOException) { throw new TransientRequestException(); }
        catch (GitHubAppAccess.AccessException)
        {
            lock(gate) { if(authorizationLifetime?.Token==authorization.Lifetime)ClearAuthorization(); }
            throw;
        }
        catch
        {
            lock(gate) { if(authorizationLifetime?.Token==authorization.Lifetime)ClearAuthorization(); }
            throw new InvalidOperationException("Selected GitHub App repository access could not be reverified. Sign in again after checking the installation.");
        }
    }
    static string Text(JsonElement root, string name) => root.GetProperty(name).GetString() ?? throw new InvalidDataException();
    // Own the exact UTF-8 buffer backing JsonDocument, wiping it on all disposal paths.
    // Refresh tokens are never extracted, stored in auth fields, logged, or refreshed.
    // Managed strings, HTTP internals, OS buffers and runtime copies cannot be guaranteed erased.
    internal sealed class Response : IDisposable
    {
        readonly byte[] bytes;
        readonly JsonDocument document;
        internal JsonElement RootElement => document.RootElement;
        internal Response(byte[] bytes, int length)
        {
            this.bytes = bytes;
            document = JsonDocument.Parse(bytes.AsMemory(0,length),new JsonDocumentOptions { MaxDepth=8 });
        }
        public void Dispose() { document.Dispose(); CryptographicOperations.ZeroMemory(bytes); }
    }
    async Task<Response> Request(string url, Dictionary<string, string>? form, string? bearer, CancellationToken cancellation, bool rejectPagination = false)
    {
        // Never follow a server-supplied URL or attach the token to an OAuth endpoint.
        using var request = new HttpRequestMessage(form == null ? HttpMethod.Get : HttpMethod.Post, url);
        request.Headers.Accept.ParseAdd("application/json");
        if (form != null) request.Content = new FormUrlEncodedContent(form);
        if (bearer != null) { request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer); request.Headers.Add("X-GitHub-Api-Version", "2022-11-28"); }
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        if ((int)response.StatusCode is >=500 and <=599 or 408 or 429) throw new TransientRequestException();
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException("GitHub sign-in request failed (HTTP " + (int)response.StatusCode + "). Retry when ready.");
        if (rejectPagination && response.Headers.Contains("Link")) throw new InvalidDataException();
        if (response.Content.Headers.ContentLength > ResponseLimit) throw new InvalidDataException();
        using var stream = await response.Content.ReadAsStreamAsync(cancellation);
        var buffer = new byte[ResponseLimit+1]; int length=0;
        Response? document=null;
        try
        {
            int count;
            while ((count=await stream.ReadAsync(buffer.AsMemory(length),cancellation))!=0)
            {
                length+=count;
                if(length>ResponseLimit)throw new InvalidDataException();
            }
            document = new Response(buffer,length);
            if (document.RootElement.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
            void Unique(JsonElement value)
            {
                if(value.ValueKind==JsonValueKind.Object) { var names=new HashSet<string>(StringComparer.Ordinal); foreach(var property in value.EnumerateObject()) { if(!names.Add(property.Name))throw new InvalidDataException(); Unique(property.Value); } }
                else if(value.ValueKind==JsonValueKind.Array) foreach(var item in value.EnumerateArray())Unique(item);
            }
            Unique(document.RootElement);
            return document;
        }
        catch { document?.Dispose(); CryptographicOperations.ZeroMemory(buffer); throw; }
    }
    public void Dispose()
    {
        lock (gate) { if (disposed) return; disposed = true; Disconnect(); }
        http.Dispose();
    }
}
