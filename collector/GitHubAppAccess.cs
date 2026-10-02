using System.Text.Json;
using System.Text.RegularExpressions;

namespace NoseCalibration;

internal static class GitHubAppAccess
{
    // Public registration identity verified in the organizer GitHub App settings.
    internal const string PinnedClientId = "Iv23li4JwAA8Kc5EWiCM";
    internal const long PinnedAppId = 5167786;
    internal const string PinnedSlug = "nose-calibration";
    internal sealed class AccessException : InvalidOperationException
    {
        internal string Code { get; }
        internal AccessException(string code,string message) : base(message+" ["+code+"]") { Code=code; }
    }
    internal const string RepositoryName = "nose-calibration-submissions";
    internal sealed record Registration(string ClientId, long AppId, string Slug);
    internal sealed record VerifiedRepository(long AccountId, long InstallationId, long RepositoryId, string OwnerLogin, string Name);

    internal static Registration ReadRegistration(JsonElement root, bool synthetic)
    {
        var fields = root.EnumerateObject().ToArray();
        if (fields.Length != 3 || fields.Select(p=>p.Name).Distinct().Count()!=3 ||
            fields.Any(p=>p.Name is not ("clientId" or "appId" or "slug"))) throw new InvalidDataException();
        string client = root.GetProperty("clientId").GetString()!, slug = root.GetProperty("slug").GetString()!;
        long app = Positive(root.GetProperty("appId"));
        if (!Regex.IsMatch(client, @"\AIv[A-Za-z0-9.]{14,62}\z") || !Regex.IsMatch(slug,@"\A[a-z0-9][a-z0-9-]{0,98}\z")) throw new InvalidDataException();
        if (!synthetic && (PinnedAppId <= 0 || app != PinnedAppId || client != PinnedClientId || slug != PinnedSlug)) throw new InvalidDataException();
        return new(client,app,slug);
    }
    static long Positive(JsonElement e) => e.TryGetInt64(out long n) && n>0 ? n : throw new InvalidDataException();
    static JsonElement Single(JsonElement root, string name)
    {
        // With per_page=100, exactly one permitted item must fit in one complete page.
        // Transport rejects any Link header; count mismatch or further pagination fails closed.
        if (name=="installations" && root.GetProperty("total_count").GetInt64()==0 && root.GetProperty(name).GetArrayLength()==0)
            throw new AccessException("not_installed","Install Nose Calibration on your personal account and select only your private nose-calibration-submissions repository.");
        if (root.GetProperty("total_count").GetInt64()!=1)
            throw new AccessException(name=="installations"?"installation_count":"repository_count",
                name=="installations"?"Exactly one accessible installation is required. Access to another participant inbox also counts; use an account with only your own installation.":"Select only your private nose-calibration-submissions repository for this GitHub App.");
        var items=root.GetProperty(name);
        if(items.ValueKind!=JsonValueKind.Array || items.GetArrayLength()!=1)throw new InvalidDataException();
        return items[0];
    }
    internal static async Task<VerifiedRepository> Verify(Registration registration, long accountId, string login,
        Func<string,CancellationToken,Task<GitHubDeviceAuth.Response>> fetch, CancellationToken ct)
    {
        using var installations = await fetch("https://api.github.com/user/installations?per_page=100&page=1",ct);
        var i=Single(installations.RootElement,"installations");
        if(i.GetProperty("repository_selection").GetString()=="all")
            throw new AccessException("all_repositories","Change the GitHub App installation to Only select repositories and select nose-calibration-submissions only.");
        long installationId=Positive(i.GetProperty("id")); var owner=i.GetProperty("account");
        if(Positive(i.GetProperty("app_id"))!=registration.AppId || i.GetProperty("app_slug").GetString()!=registration.Slug ||
            i.GetProperty("repository_selection").GetString()!="selected" || i.GetProperty("target_type").GetString()!="User" ||
            Positive(i.GetProperty("target_id"))!=accountId || Positive(owner.GetProperty("id"))!=accountId ||
            owner.GetProperty("type").GetString()!="User" || !string.Equals(owner.GetProperty("login").GetString(),login,StringComparison.OrdinalIgnoreCase) ||
            i.GetProperty("suspended_at").ValueKind!=JsonValueKind.Null || i.GetProperty("suspended_by").ValueKind!=JsonValueKind.Null) throw new InvalidDataException();
        var permissions=i.GetProperty("permissions").EnumerateObject().ToArray();
        if(permissions.Length!=2 || permissions.Select(p=>p.Name).Distinct().Count()!=2 ||
            permissions.Any(p=>p.Name is not ("contents" or "metadata")) ||
            i.GetProperty("permissions").GetProperty("contents").GetString()!="write" ||
            i.GetProperty("permissions").GetProperty("metadata").GetString()!="read") throw new AccessException("scope_expansion","The GitHub App must have only Contents read/write and Metadata read permissions.");
        using var repositories=await fetch($"https://api.github.com/user/installations/{installationId}/repositories?per_page=100&page=1",ct);
        var r=Single(repositories.RootElement,"repositories"); var repoOwner=r.GetProperty("owner");
        if(r.GetProperty("private").ValueKind==JsonValueKind.False || r.GetProperty("visibility").GetString()=="public")
            throw new AccessException("not_private","Make nose-calibration-submissions private before signing in again.");
        if(r.GetProperty("name").GetString()!=RepositoryName)
            throw new AccessException("wrong_repository","Select the repository named nose-calibration-submissions for this GitHub App.");
        long repositoryId=Positive(r.GetProperty("id"));
        if(r.GetProperty("private").ValueKind!=JsonValueKind.True || r.GetProperty("visibility").GetString()!="private" ||
            r.GetProperty("name").GetString()!=RepositoryName || Positive(repoOwner.GetProperty("id"))!=accountId ||
            repoOwner.GetProperty("type").GetString()!="User" || !string.Equals(repoOwner.GetProperty("login").GetString(),login,StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(r.GetProperty("full_name").GetString(),login+"/"+RepositoryName,StringComparison.OrdinalIgnoreCase) ||
            r.GetProperty("fork").ValueKind!=JsonValueKind.False || r.GetProperty("archived").ValueKind!=JsonValueKind.False ||
            r.GetProperty("disabled").ValueKind!=JsonValueKind.False || r.GetProperty("permissions").GetProperty("push").ValueKind!=JsonValueKind.True ||
            r.GetProperty("permissions").GetProperty("pull").ValueKind!=JsonValueKind.True) throw new InvalidDataException();
        ct.ThrowIfCancellationRequested();
        return new(accountId,installationId,repositoryId,login,RepositoryName);
    }
}
