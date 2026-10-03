using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace NoseCalibration;

// Fixed-origin invitation transport; NOSE1 remains unchanged.
internal static class SitesSubmission
{
    internal const string Origin="https://nose-calibration-download.ddhruvsai.chatgpt.site";
    internal sealed record Receipt(string UploadId,string ParticipantId,string SessionId,string Digest,long Bytes,string Status);
    internal sealed record State(int Version,string Transport,string StudyNamespace,string RecipientKeyId,string ParticipantId,string SessionId,
        string ZipSha256,string EnvelopeSha256,long EnvelopeBytes,string? UploadId,bool RemoteWriteStarted,bool Stored);
    static readonly JsonSerializerOptions Strict=new(){UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    internal sealed class SharingError(string code) : InvalidOperationException((code switch {
        "completed_human_required" => "Submit a completed human session before invitation sharing. Stopped or timed-out recordings can still be exported locally. ",
        "connection_failed" => "The invitation connection could not be confirmed. Check your connection and retry. ",
        "service_unavailable" => "The upload service could not be reached in time. Local files remain; retry to verify any remote submission. ",
        "legacy_github_state" => "This recording already uses GitHub sharing. Continue through GitHub; no invitation upload was created. ",
        "envelope_missing" => "The original encrypted submission is missing. Local upload state was preserved; contact the organizer. ",
        "recording_too_large" => "This recording exceeds the 30 MiB upload limit. Export it locally and contact the organizer. ",
        "stale_staging" => "A staged encrypted file has no matching upload state. It was preserved; contact the organizer for local recovery before trying again. ",
        _ => "Invitation sharing stopped. Your local recording and encrypted file are preserved. "})+"["+code+"]")
    { internal string Code {get;}=code; }
    static bool Hex(string? value,int count)=>value!=null && Regex.IsMatch(value,@"\A[a-f0-9]{"+count+@"}\z");
    static string Hash(byte[] value)=>Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
    static SharingError Error(string code)=>new(code);
    static void SafeFile(string path)
    {
        if(File.Exists(path) && (File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw Error("local_file_invalid");
        if(Directory.Exists(path))throw Error("local_file_invalid");
    }
    static byte[] ReadFile(string path,int limit)
    {
        SafeFile(path);using var f=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read);
        if(f.Length<1 || f.Length>limit)throw Error("local_file_invalid");
        using var output=new MemoryStream();byte[] buffer=new byte[65536];int count;
        while((count=f.Read(buffer))>0){if(output.Length+count>limit)throw Error("local_file_invalid");output.Write(buffer,0,count);}
        return output.ToArray();
    }
    static JsonDocument Parse(byte[] raw)
    {
        var doc=JsonDocument.Parse(raw,new JsonDocumentOptions{MaxDepth=4});
        try {if(doc.RootElement.ValueKind!=JsonValueKind.Object)throw Error("response_invalid");GitHubSubmission.RejectDuplicateProperties(doc.RootElement);return doc;}
        catch {doc.Dispose();throw;}
    }
    static void Fields(JsonElement root,params string[] fields)
    {if(!root.EnumerateObject().Select(p=>p.Name).Order().SequenceEqual(fields.Order()))throw Error("response_invalid");}
    static State? Load(string file,string sessionId)
    {
        if(!File.Exists(file))return null;
        using var doc=Parse(ReadFile(file,16384));
        if(doc.RootElement.TryGetProperty("Version",out var version) && version.TryGetInt32(out int number) && number is 2 or 3) throw Error("legacy_github_state");
        Fields(doc.RootElement,"Version","Transport","StudyNamespace","RecipientKeyId","ParticipantId","SessionId","ZipSha256","EnvelopeSha256","EnvelopeBytes","UploadId","RemoteWriteStarted","Stored");
        var s=JsonSerializer.Deserialize<State>(doc.RootElement,Strict)??throw Error("state_invalid");
        if(s.Version!=4 || s.Transport!="sites" || s.StudyNamespace!=SitesEnvelope.StudyNamespace || s.RecipientKeyId!=SitesEnvelope.RecipientKeyId ||
            s.SessionId!=sessionId || !Hex(s.ParticipantId,32) || !Hex(s.ZipSha256,64) || !Hex(s.EnvelopeSha256,64) ||
            s.EnvelopeBytes<7 || s.EnvelopeBytes>SitesEnvelope.MaxEnvelope || s.UploadId!=null&&!Hex(s.UploadId,32) ||
            s.UploadId!=null&&!s.RemoteWriteStarted || s.Stored&&(s.UploadId==null||!s.RemoteWriteStarted))throw Error("state_invalid");
        return s;
    }
    internal static State RequireState(string file,string sessionId)=>Load(file,sessionId)??throw Error("state_missing");
    static void Save(string file,State state)
    {
        SafeFile(file);string tmp=file+"."+Guid.NewGuid().ToString("N")+".pending";
        try {using(var f=new FileStream(tmp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){f.Write(JsonSerializer.SerializeToUtf8Bytes(state));f.Flush(true);}File.Move(tmp,file,true);}
        finally {if(File.Exists(tmp))File.Delete(tmp);}
    }
    internal static async Task<string> Connect(string invitation,CancellationToken cancellation)
    {
        using var handler=new HttpClientHandler{AllowAutoRedirect=false,UseCookies=false};
        using var http=new HttpClient(handler){Timeout=TimeSpan.FromSeconds(30)};
        return await ConnectCore(invitation,http,cancellation);
    }
    internal static async Task<string> ConnectCore(string invitation,HttpClient http,CancellationToken cancellation)
    {
        try
        {
            cancellation.ThrowIfCancellationRequested();
            if(invitation==null || !Regex.IsMatch(invitation,@"\A[A-Za-z0-9_-]{43}\z"))throw Error("invitation_invalid");
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancellation);timeout.CancelAfter(TimeSpan.FromSeconds(30));
            using var request=new HttpRequestMessage(HttpMethod.Get,Origin+"/api/participant");
            request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",invitation);
            using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,timeout.Token);
            if(response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)throw Error("invitation_rejected");
            if(!response.IsSuccessStatusCode)throw Error("service_unavailable");
            using var doc=Parse(await GitHubSubmission.ReadBounded(response.Content,16384,timeout.Token));var b=doc.RootElement;
            Fields(b,"protocolVersion","studyNamespace","recipientKeyId","participantId");
            string participant=b.GetProperty("participantId").GetString()!;
            SitesEnvelope.ValidateBootstrap(b.GetProperty("protocolVersion").GetInt32(),b.GetProperty("studyNamespace").GetString()!,b.GetProperty("recipientKeyId").GetString()!,participant);
            return participant;
        }
        catch(OperationCanceledException) when(!cancellation.IsCancellationRequested){throw Error("connection_failed");}
        catch(OperationCanceledException){throw;}
        catch(SharingError){throw;}
        catch{throw Error("connection_failed");}
    }
    internal static async Task<Receipt> Upload(string zip,string session,string invitation,string expectedParticipant,CancellationToken cancellation=default)
    {
        try
        {
            cancellation.ThrowIfCancellationRequested();
            using var handler=new HttpClientHandler{AllowAutoRedirect=false,UseCookies=false};
            using var http=new HttpClient(handler){Timeout=TimeSpan.FromMinutes(5)};
            string pem=Encoding.UTF8.GetString(ReadFile(Path.Combine(AppContext.BaseDirectory,"public-key.pem"),8192));
            return await UploadCore(zip,session,invitation,http,pem,cancellation,expectedParticipant);
        }
        catch(OperationCanceledException) when(!cancellation.IsCancellationRequested){throw Error("service_unavailable");}
        catch(OperationCanceledException){throw;}
        catch(SharingError){throw;}
        catch{throw Error("sharing_failed");}
    }
    // Only injectable transport for synthetic tests. Production origin/key pin cannot be supplied by users.
    internal static async Task<Receipt> UploadCore(string zip,string session,string invitation,HttpClient http,string publicKeyPem,CancellationToken cancellation=default,string? expectedParticipant=null)
    {
        try {return await Core(zip,session,invitation,http,publicKeyPem,cancellation,expectedParticipant);}
        catch(OperationCanceledException) when(!cancellation.IsCancellationRequested){throw Error("service_unavailable");}
        catch(OperationCanceledException){throw;}
        catch(SharingError){throw;}
        catch {throw Error("sharing_failed");}
    }
    static async Task<Receipt> Core(string zip,string session,string invitation,HttpClient http,string pem,CancellationToken ct,string? expectedParticipant)
    {
        ct.ThrowIfCancellationRequested();
        if(invitation==null || !Regex.IsMatch(invitation,@"\A[A-Za-z0-9_-]{43}\z"))throw Error("invitation_invalid");
        string id=Path.GetFileName(Path.TrimEndingDirectorySeparator(session));
        if(!Hex(id,32) || !Directory.Exists(session) || (File.GetAttributes(session)&FileAttributes.ReparsePoint)!=0)throw Error("session_invalid");
        string lockPath=Path.Combine(session,"upload.lock");SafeFile(lockPath);
        using var uploadLock=new FileStream(lockPath,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
        string stateFile=Path.Combine(session,"upload-state.json"),envelopeFile=Path.Combine(session,"submission.nose2"),staged=envelopeFile+".tmp";
        var state=Load(stateFile,id);
        if(state==null && (File.Exists(envelopeFile)||File.Exists(Path.Combine(session,"submission.nose"))))throw Error("orphan_envelope");
        if(state==null && File.Exists(staged))throw Error("stale_staging");
        SafeFile(envelopeFile);SafeFile(staged);
        SafeFile(zip);
        if(new FileInfo(zip).Length>SitesEnvelope.MaxPlain)throw Error("recording_too_large");
        if(state!=null && !File.Exists(envelopeFile) && !File.Exists(staged))throw Error("envelope_missing");
        byte[] plain=ReadFile(zip,SitesEnvelope.MaxPlain);byte[] envelope;
        try
        {
            if(state!=null && Hash(plain)!=state.ZipSha256)throw Error("zip_changed");
            // Validate bootstrap pins, then verify actual packaged RSA key even on retries.
            using(var rsa=RSA.Create()){rsa.ImportFromPem(pem);if(rsa.KeySize!=3072 || Hash(rsa.ExportSubjectPublicKeyInfo())!=SitesEnvelope.RecipientKeyId)throw Error("recipient_key_invalid");}
            using var bootstrap=await Api(HttpMethod.Get,"/api/participant");var b=bootstrap.RootElement;
            Fields(b,"protocolVersion","studyNamespace","recipientKeyId","participantId");
            string participant=b.GetProperty("participantId").GetString()!;
            SitesEnvelope.ValidateBootstrap(b.GetProperty("protocolVersion").GetInt32(),b.GetProperty("studyNamespace").GetString()!,b.GetProperty("recipientKeyId").GetString()!,participant);
            if(expectedParticipant!=null && expectedParticipant!=participant)throw Error("participant_changed");
            if(state!=null)
            {
                if(state.ParticipantId!=participant)throw Error("participant_changed");
                string source=File.Exists(envelopeFile)?envelopeFile:staged;
                envelope=ReadFile(source,SitesEnvelope.MaxEnvelope);
                if(envelope.Length!=state.EnvelopeBytes || Hash(envelope)!=state.EnvelopeSha256)throw Error("envelope_changed");
                if(source==staged)File.Move(staged,envelopeFile);
            }
            else
            {
                envelope=SitesEnvelope.Encrypt(plain,participant,id,pem);
                using(var f=new FileStream(staged,FileMode.CreateNew,FileAccess.Write,FileShare.None)){f.Write(envelope);f.Flush(true);}
                state=new(4,"sites",SitesEnvelope.StudyNamespace,SitesEnvelope.RecipientKeyId,participant,id,Hash(plain),Hash(envelope),envelope.Length,null,false,false);
                Save(stateFile,state);File.Move(staged,envelopeFile);
            }
        }
        finally {CryptographicOperations.ZeroMemory(plain);}
        ct.ThrowIfCancellationRequested();
        if(state.UploadId==null)
        {
            state=state with{RemoteWriteStarted=true};Save(stateFile,state);
            using var reservation=await Api(HttpMethod.Post,"/api/reservations",new{sessionId=id,digest=state.EnvelopeSha256,bytes=state.EnvelopeBytes});
            var received=CheckReceipt(reservation.RootElement,state);
            state=state with{UploadId=received.UploadId};Save(stateFile,state);
        }
        // Always reconcile durable remote status before any retry/body write.
        using var status=await Api(HttpMethod.Get,"/api/uploads/"+state.UploadId);
        var current=CheckReceipt(status.RootElement,state);
        if(current.Status=="reserved")
        {
            using var put=await Api(HttpMethod.Put,"/api/uploads/"+state.UploadId,bytes:envelope);
            current=CheckReceipt(put.RootElement,state);
            if(current.Status=="reserved")throw Error("storage_unconfirmed");
            using var verified=await Api(HttpMethod.Get,"/api/uploads/"+state.UploadId);
            current=CheckReceipt(verified.RootElement,state);
        }
        if(current.Status is not("stored" or "received_by_organizer"))throw Error("storage_unconfirmed");
        state=state with{Stored=true};Save(stateFile,state);return current;

        async Task<JsonDocument> Api(HttpMethod method,string path,object? json=null,byte[]? bytes=null)
        {
            ct.ThrowIfCancellationRequested();using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromMinutes(5));
            using var request=new HttpRequestMessage(method,Origin+path);
            request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",invitation);request.Headers.Accept.ParseAdd("application/json");
            if(json!=null)request.Content=new StringContent(JsonSerializer.Serialize(json),Encoding.UTF8,"application/json");
            if(bytes!=null){request.Content=new ByteArrayContent(bytes);request.Content.Headers.ContentType=new MediaTypeHeaderValue("application/octet-stream");request.Content.Headers.ContentLength=bytes.Length;}
            using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,timeout.Token);
            if(response.StatusCode==HttpStatusCode.Gone)throw Error("reservation_expired");
            if(response.StatusCode==HttpStatusCode.Unauthorized || response.StatusCode==HttpStatusCode.Forbidden)throw Error("invitation_rejected");
            if(response.StatusCode==HttpStatusCode.Conflict)throw Error(method==HttpMethod.Post && path=="/api/reservations" ? "submission_conflict" : "storage_unconfirmed");
            if(response.StatusCode==HttpStatusCode.NotFound && path.StartsWith("/api/uploads/",StringComparison.Ordinal))throw Error("upload_not_found");
            if(!response.IsSuccessStatusCode)throw Error("service_unavailable");
            return Parse(await GitHubSubmission.ReadBounded(response.Content,16384,timeout.Token));
        }
    }
    static Receipt CheckReceipt(JsonElement r,State state)
    {
        Fields(r,"uploadId","participantId","sessionId","digest","bytes","status","validated");
        string upload=r.GetProperty("uploadId").GetString()!,participant=r.GetProperty("participantId").GetString()!,session=r.GetProperty("sessionId").GetString()!,digest=r.GetProperty("digest").GetString()!,status=r.GetProperty("status").GetString()!;
        long bytes=r.GetProperty("bytes").GetInt64();
        if(!Hex(upload,32) || state.UploadId!=null&&upload!=state.UploadId || participant!=state.ParticipantId || session!=state.SessionId || digest!=state.EnvelopeSha256 || bytes!=state.EnvelopeBytes || r.GetProperty("validated").ValueKind!=JsonValueKind.False || status is not("reserved" or "stored" or "received_by_organizer"))throw Error("receipt_mismatch");
        return new(upload,participant,session,digest,bytes,status);
    }
}
