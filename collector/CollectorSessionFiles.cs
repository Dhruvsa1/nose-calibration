using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace NoseCalibration;

// Validates saved selections without mutating the collector's active session.
internal static class CollectorSessionFiles
{
    internal static async Task WriteSnapshot(string destination, string file, byte[] data, Func<bool> stillCurrent, Action completed,
        Func<string, byte[], Task>? write = null)
    {
        string pendingFile = Path.Combine(destination, file + ".pending");
        try
        {
            await (write ?? ((path, bytes) => File.WriteAllBytesAsync(path, bytes)))(pendingFile, data);
            if (!stillCurrent()) return;
            File.Move(pendingFile, Path.Combine(destination, file), true);
            completed();
        }
        finally { if (File.Exists(pendingFile)) File.Delete(pendingFile); }
    }
    internal sealed record Completed(string Folder, string Mode, long EventCount, long ScreenshotCount, JsonElement? Answers);
    static JsonDocument ReadObject(string path, long limit)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Attributes.HasFlag(FileAttributes.ReparsePoint)) throw new InvalidDataException("Session file is unavailable");
        using var stream = File.OpenRead(path);
        if (stream.Length > limit) throw new InvalidDataException("Session file exceeds size limit");
        var document = JsonDocument.Parse(stream);
        if (document.RootElement.ValueKind != JsonValueKind.Object) { document.Dispose(); throw new InvalidDataException("Invalid session object"); }
        return document;
    }
    internal static Completed ReadCompleted(string root, string id)
    {
        if (!Regex.IsMatch(id, "\\A[a-f0-9]{32}\\z")) throw new InvalidDataException("Invalid session ID");
        string folder = Path.Combine(root, id);
        if (!Directory.Exists(folder) || new DirectoryInfo(folder).Attributes.HasFlag(FileAttributes.ReparsePoint)) throw new InvalidDataException("Session is unavailable");
        using var manifest = ReadObject(Path.Combine(folder, "manifest.json"), 200000);
        var m = manifest.RootElement;
        if (m.GetProperty("sessionId").GetString() != id || m.GetProperty("consent").ValueKind != JsonValueKind.True || m.GetProperty("schemaVersion").GetInt32() != 1)
            throw new InvalidDataException("Invalid recording manifest");
        string mode = m.GetProperty("mode").GetString()!;
        if (mode is not ("human" or "verification" or "codex")) throw new InvalidDataException("Invalid session mode");
        using var summary = ReadObject(Path.Combine(folder, "summary.json"), 200000);
        long events = summary.RootElement.GetProperty("eventCount").GetInt64(), shots = summary.RootElement.GetProperty("screenshotCount").GetInt64();
        if (events is < 0 or > 250000 || shots is < 0 or > 120 || summary.RootElement.GetProperty("mode").GetString() != mode)
            throw new InvalidDataException("Invalid session counters or mode");
        JsonElement? answers = null;
        string answersPath = Path.Combine(folder, "answers.json");
        if (File.Exists(answersPath)) { using var document = ReadObject(answersPath, 200000); answers = document.RootElement.Clone(); }
        return new Completed(folder, mode, events, shots, answers);
    }
    internal static string FrozenBundle(string session, string zip)
    {
        using var state = ReadObject(Path.Combine(session, "upload-state.json"), 16384);
        var s = state.RootElement;
        string digest = s.GetProperty("ZipSha256").GetString() ?? "";
        if (s.GetProperty("Version").GetInt32() != 2 || s.GetProperty("SessionId").GetString() != Path.GetFileName(session) || !Regex.IsMatch(digest, "\\A[a-f0-9]{64}\\z"))
            throw new InvalidDataException("Invalid saved upload state. The original upload ZIP was not changed.");
        if (!File.Exists(zip)) throw new InvalidOperationException("The original upload ZIP is missing. It cannot be recreated after sharing has begun; contact the organizer.");
        if (File.GetAttributes(zip).HasFlag(FileAttributes.ReparsePoint)) throw new InvalidDataException("Invalid upload ZIP");
        using var stream = File.OpenRead(zip);
        if (stream.Length > 30 * 1024 * 1024 || !Convert.ToHexString(SHA256.HashData(stream)).Equals(digest, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The original upload ZIP changed. It was not overwritten; contact the organizer.");
        return zip;
    }
}
