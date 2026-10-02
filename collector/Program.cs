using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Diagnostics;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace NoseCalibration;
internal static class Program
{
    [STAThread] static void Main(string[] args) { ApplicationConfiguration.Initialize(); Application.Run(new CollectorForm(args.Contains("--verification"))); }
}
internal partial class CollectorForm : Form
{
    internal readonly WebView2 web = new() { Dock = DockStyle.Fill };
    internal static readonly string DataRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NoseCalibration");
    internal bool recording;
    internal string? session;
    internal string mode = "human";
    StreamWriter? events;
    DateTime started, lastShot;
    long eventCount, shotCount, eventBytes, screenshotBytes;
    bool shotBusy, sharing;
    GitHubDeviceAuth? githubAuth;
    CancellationTokenSource? uploadCancellation;
    readonly bool verificationMode;
    readonly System.Windows.Forms.Timer clock = new() { Interval = 1000 };
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    partial void ConfigureAdmin();
    partial void AdminCommand(string command, JsonElement payload);
    internal CollectorForm(bool verification = false)
    {
        mode = verification ? "verification" : "human";
        verificationMode = verification;
        Text = "Nose Calibration - Collector" + (verification ? " (verification)" : "");
        // Visual sizing. The page lays out in CSS px (= DIPs), so sizes are given in DIPs and converted
        // with the window's DPI; 100/150/200% scaling then give the same usable page. Supported minimum
        // page: 720x560. A monitor whose work area is smaller lowers the minimum to that work area so the
        // window always fits. Recomputed (never multiplied) on DPI, monitor and display changes.
        const int MinPageWidth = 720, MinPageHeight = 560, PreferredPageWidth = 1440, PreferredPageHeight = 900;
        Size Frame(int pageWidth, int pageHeight, int dpi) => SizeFromClientSize(new Size((int)Math.Ceiling(pageWidth * dpi / 96.0), (int)Math.Ceiling(pageHeight * dpi / 96.0)));
        Size Minimum(int dpi, Rectangle work) { var min = Frame(MinPageWidth, MinPageHeight, dpi); return new Size(Math.Min(min.Width, work.Width), Math.Min(min.Height, work.Height)); }
        void ApplyMinimum()
        {
            if (IsDisposed || !IsHandleCreated) return;
            var work = Screen.FromHandle(Handle).WorkingArea;
            MinimumSize = Minimum(DeviceDpi, work);
            if (WindowState != FormWindowState.Normal) return;
            int x = Math.Max(work.Left, Math.Min(Left, work.Right - Width)), y = Math.Max(work.Top, Math.Min(Top, work.Bottom - Height));
            if (x != Left || y != Top) Location = new Point(x, y);
        }
        var startWork = Screen.FromPoint(Cursor.Position).WorkingArea;
        MinimumSize = Minimum(DeviceDpi, startWork);
        var preferred = Frame(PreferredPageWidth, PreferredPageHeight, DeviceDpi);
        var startSize = new Size(Math.Clamp(Math.Min(preferred.Width, startWork.Width * 92 / 100), MinimumSize.Width, startWork.Width), Math.Clamp(Math.Min(preferred.Height, startWork.Height * 92 / 100), MinimumSize.Height, startWork.Height));
        StartPosition = FormStartPosition.Manual;
        Bounds = new Rectangle(startWork.Left + (startWork.Width - startSize.Width) / 2, startWork.Top + (startWork.Height - startSize.Height) / 2, startSize.Width, startSize.Height);
        HandleCreated += (_, _) => ApplyMinimum();
        // Fires only under per-monitor DPI awareness; deferred so the framework applies its own DPI bounds first.
        DpiChanged += (_, _) => BeginInvoke(new Action(ApplyMinimum));
        ResizeEnd += (_, _) => ApplyMinimum();
        EventHandler displayChanged = (_, _) => { if (IsHandleCreated && !IsDisposed) BeginInvoke(new Action(ApplyMinimum)); };
        Microsoft.Win32.SystemEvents.DisplaySettingsChanged += displayChanged;
        FormClosed += (_, _) => Microsoft.Win32.SystemEvents.DisplaySettingsChanged -= displayChanged;
        Controls.Add(web);
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        ConfigureAdmin();
        Shown += async (_, _) => { try { await Initialize(); } catch (Exception ex) { MessageBox.Show("Could not start the web interface. Microsoft Edge WebView2 Runtime is required.\n" + ex.Message); } };
        FormClosing += (_, _) => { uploadCancellation?.Cancel(); githubAuth?.Disconnect(); StopSession("window closed"); };
        FormClosed += (_, _) => { clock.Dispose(); githubAuth?.Dispose(); };
        clock.Tick += (_, _) => { if (recording && (DateTime.UtcNow - started).TotalMinutes >= 30) { StopSession("time limit"); Send(new { kind = "stopped", reason = "30-minute limit reached" }); } };
    }
    async Task Initialize()
    {
        Directory.CreateDirectory(DataRoot);
        var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(DataRoot, "browser"));
        await web.EnsureCoreWebView2Async(env);
        web.CoreWebView2.SetVirtualHostNameToFolderMapping("nose.local", Path.Combine(AppContext.BaseDirectory, "web"), CoreWebView2HostResourceAccessKind.DenyCors);
        web.CoreWebView2.Settings.AreDevToolsEnabled = false;
        web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        web.CoreWebView2.Settings.AreBrowserAcceleratorKeysEnabled = false;
        web.CoreWebView2.Settings.IsPasswordAutosaveEnabled = false;
        web.CoreWebView2.Settings.IsGeneralAutofillEnabled = false;
        web.CoreWebView2.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
        web.CoreWebView2.WebResourceRequested += (_, e) =>
        {
            var uri = new Uri(e.Request.Uri);
            string name = uri.AbsolutePath.TrimStart('/');
            string[] files = { "index.html", "style.css", "app.js", "questions.js", "grader.js", "ui.js", "branding/icon-light.png", "branding/wordmark-light.png", "branding/icon-dark.png", "branding/wordmark-dark.png" };
            if (uri.Scheme != "https" || uri.Host != "nose.local" || !files.Contains(name))
            { e.Response = web.CoreWebView2.Environment.CreateWebResourceResponse(new MemoryStream(), 403, "Blocked", "Content-Type: text/plain"); return; }
            string mime = name.EndsWith(".png") ? "image/png" : name.EndsWith(".js") ? "text/javascript" : name.EndsWith(".css") ? "text/css" : "text/html";
            string policy = name == "grader.js" ? "default-src 'none'; script-src 'unsafe-eval'; connect-src 'none'; worker-src 'none'" : "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; worker-src 'self'; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'";
            e.Response = web.CoreWebView2.Environment.CreateWebResourceResponse(new MemoryStream(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "web", name))), 200, "OK", "Content-Type: " + mime + "; charset=utf-8\r\nContent-Security-Policy: " + policy + "\r\nX-Content-Type-Options: nosniff");
        };
        web.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
        web.CoreWebView2.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
        web.CoreWebView2.DownloadStarting += (_, e) => e.Cancel = true;
        web.CoreWebView2.NavigationStarting += (_, e) => { if (!e.Uri.StartsWith("https://nose.local/", StringComparison.Ordinal)) e.Cancel = true; };
        web.CoreWebView2.WebMessageReceived += async (_, e) =>
        {
            if (e.Source != "https://nose.local/index.html") return;
            try
            {
                if (e.WebMessageAsJson.Length > 1000000) throw new InvalidDataException("Message too large");
                using var doc = JsonDocument.Parse(e.WebMessageAsJson); var payload = doc.RootElement;
                string command = payload.GetProperty("command").GetString()!;
                switch (command)
                {
                    case "ready": Send(new { kind = "edition", mode = Text.Contains("Admin") ? "admin" : "collector" }); SendAccount(); ListSessions(); break;
                    case "start": if (payload.GetProperty("consent").GetBoolean()) StartSession(); break;
                    case "events":
                        if (!recording || GetForegroundWindow() != Handle || !ContainsFocus) break;
                        var batch = payload.GetProperty("events");
                        if (batch.GetArrayLength() > 512) throw new InvalidDataException("Batch too large");
                        foreach (var item in batch.EnumerateArray())
                        {
                            string line = item.GetRawText();
                            if (line.Length > 16000 || !Telemetry.Valid(item)) throw new InvalidDataException("Invalid event");
                            long bytes = System.Text.Encoding.UTF8.GetByteCount(line) + 2;
                            if (eventBytes + bytes > 18 * 1024 * 1024 || eventCount >= 250000) { StopSession("event limit"); Send(new { kind = "stopped", reason = "Recording size limit" }); break; }
                            events!.WriteLine(line); eventBytes += bytes; eventCount++;
                        }
                        events?.Flush();
                        if (eventCount > 250000) { StopSession("event limit"); Send(new { kind = "stopped", reason = "Event limit" }); }
                        break;
                    case "snapshot": if (recording) await Snapshot(payload.GetProperty("eventId").GetInt64()); break;
                    case "finish":
                        if (session != null && recording)
                        {
                            string answerJson = payload.GetProperty("answers").GetRawText();
                            if (System.Text.Encoding.UTF8.GetByteCount(answerJson) > 200000) throw new InvalidDataException("Answers exceed size limit");
                            File.WriteAllText(Path.Combine(session, "answers.json"), answerJson);
                        }
                        StopSession("completed"); Send(new { kind = "stopped", folder = session, events = eventCount, screenshots = shotCount }); break;
                    case "finalized":
                        // Grading can finish after capture has stopped. Never update a different or active session.
                        if (session == null || recording || sharing || payload.GetProperty("sessionId").GetString() != Path.GetFileName(session)) break;
                        if (File.Exists(Path.Combine(session, "upload-state.json"))) break;
                        string finalAnswers = payload.GetProperty("answers").GetRawText();
                        if (System.Text.Encoding.UTF8.GetByteCount(finalAnswers) > 200000) throw new InvalidDataException("Answers exceed size limit");
                        File.WriteAllText(Path.Combine(session, "answers.json"), finalAnswers);
                        break;
                    case "stop": StopSession("stopped by participant"); Send(new { kind = "stopped", folder = session, events = eventCount, screenshots = shotCount }); break;
                    case "open": Process.Start(new ProcessStartInfo(DataRoot) { UseShellExecute = true }); break;
                    case "export": Export(); break;
                    case "signin":
                        if (sharing) throw new InvalidOperationException("Wait for the current upload to finish or sign out to cancel it before changing accounts.");
                        githubAuth ??= new GitHubDeviceAuth(Path.Combine(AppContext.BaseDirectory, "oauth-client.json"));
                        try { await githubAuth.SignIn(message => Send(new { kind = "notice", message })); }
                        finally { SendAccount(); }
                        break;
                    case "signout": uploadCancellation?.Cancel(); githubAuth?.Disconnect(); SendAccount(); break;
                    case "list-sessions": ListSessions(); break;
                    case "load-session": LoadSession(payload.GetProperty("sessionId").GetString()); break;
                    case "share":
                        if (!payload.GetProperty("consent").GetBoolean()) break;
                        await Share(); break;
                    default: AdminCommand(command, payload.Clone()); break;
                }
            }
            catch (Exception ex) { Send(new { kind = "error", message = ex.Message }); }
        };
        web.Source = new Uri("https://nose.local/index.html"); clock.Start();
    }
    internal void StartSession()
    {
        if (recording) return;
        if (shotBusy) throw new InvalidOperationException("Wait for the pending screenshot to finish before starting another recording.");
        if (sharing) throw new InvalidOperationException("Wait for the current upload to finish before starting another recording.");
        if (!Text.Contains("Admin")) mode = verificationMode ? "verification" : "human";
        string id = Guid.NewGuid().ToString("N"); session = Path.Combine(DataRoot, "sessions", id); Directory.CreateDirectory(session);
        started = DateTime.UtcNow; eventCount = shotCount = eventBytes = screenshotBytes = 0; lastShot = DateTime.MinValue;
        File.WriteAllText(Path.Combine(session, "manifest.json"), JsonSerializer.Serialize(new { schemaVersion = 1, sessionId = id, mode, startedAt = started, appVersion = "0.1.0", consent = true, scope = "Nose Calibration web interface only", screenshot = "click-triggered page JPEG; throttled 750ms; no other apps", telemetry = "pointer,key,wheel,scroll,focus,selection,input metadata and final answers" }));
        events = new StreamWriter(Path.Combine(session, "events.jsonl")) { AutoFlush = true }; recording = true;
        Send(new { kind = "started", sessionId = id, mode });
    }
    internal void StopSession(string reason)
    {
        if (!recording) return; recording = false; events?.Dispose(); events = null;
        File.WriteAllText(Path.Combine(session!, "summary.json"), JsonSerializer.Serialize(new { reason, eventCount, screenshotCount = shotCount, durationMs = (DateTime.UtcNow - started).TotalMilliseconds, mode }));
    }
    async Task Snapshot(long eventId)
    {
        if (eventId < 1 || eventId > 250000 || shotBusy || GetForegroundWindow() != Handle || !ContainsFocus) return;
        if ((DateTime.UtcNow - lastShot).TotalMilliseconds < 750 || shotCount >= 120) return;
        shotBusy = true; string destination = session!; StreamWriter? destinationEvents = events; lastShot = DateTime.UtcNow;
        try
        {
            using var stream = new MemoryStream(); await web.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Jpeg, stream);
            if (!recording || session != destination || GetForegroundWindow() != Handle) return;
            if (stream.Length > 5 * 1024 * 1024 || screenshotBytes + stream.Length > 10 * 1024 * 1024) return;
            string file = "click-" + eventId.ToString("D8") + ".jpg";
            await CollectorSessionFiles.WriteSnapshot(destination, file, stream.ToArray(),
                () => recording && session == destination && ReferenceEquals(events, destinationEvents) && !IsDisposed,
                () => { screenshotBytes += stream.Length; shotCount++;
                    destinationEvents!.WriteLine(JsonSerializer.Serialize(new { type = "screenshot", eventId, file, capturedAt = DateTime.UtcNow })); });
        }
        finally { shotBusy = false; }
    }
    internal void Send(object value) { if (InvokeRequired) { if (!IsDisposed) BeginInvoke(new Action(() => Send(value))); return; } if (!IsDisposed && web.CoreWebView2 != null) web.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(value)); }
    string Bundle()
    {
        if (session == null || recording || shotBusy) throw new InvalidOperationException("Finish recording before exporting or sharing.");
        string zip = Path.Combine(DataRoot, Path.GetFileName(session) + ".zip");
        if (File.Exists(Path.Combine(session, "upload-state.json")))
            return CollectorSessionFiles.FrozenBundle(session, zip);
        if (File.Exists(zip)) File.Delete(zip);
        long total = 0; int entries = 0;
        using var archive = ZipFile.Open(zip, ZipArchiveMode.Create);
        foreach (var path in Directory.GetFiles(session))
        {
            string name = Path.GetFileName(path);
            if (name is "manifest.json" or "events.jsonl" or "answers.json" or "summary.json" || System.Text.RegularExpressions.Regex.IsMatch(name, @"^click-\d{8}\.jpg$")) {
                long size = new FileInfo(path).Length;
                long limit = name == "events.jsonl" ? 20 * 1024 * 1024 : name.EndsWith(".jpg") ? 5 * 1024 * 1024 : 200000;
                total += size; entries++;
                if (size > limit || total > 100 * 1024 * 1024 || entries > 124) throw new InvalidDataException("Recording exceeds export limits");
                archive.CreateEntryFromFile(path, name, CompressionLevel.Optimal);
            }
        }
        return zip;
    }
    void Export()
    {
        if (sharing) throw new InvalidOperationException("Wait for the current upload to finish or cancel it before exporting.");
        string zip = Bundle(); using var save = new SaveFileDialog { FileName = Path.GetFileName(zip), Filter = "Recording ZIP|*.zip" };
        if (save.ShowDialog() == DialogResult.OK) { File.Copy(zip, save.FileName, true); Send(new { kind = "notice", message = "Saved recording ZIP. It contains private recording data; share only with the study organizer." }); }
    }
    async Task Share()
    {
        if (sharing) return; sharing = true;
        using var cancellation = new CancellationTokenSource(); uploadCancellation = cancellation;
        try
        {
            if (mode != "human") throw new InvalidOperationException("Verification sessions cannot be shared as participant submissions.");
            if (session == null || recording || shotBusy) throw new InvalidOperationException("Finish recording before sharing.");
            string receipt = Path.Combine(session, "receipt.json");
            Send(new { kind = "notice", message = "Encrypting or verifying the saved submission. Keep the app open." });
            string zip = File.Exists(Path.Combine(session, "upload-state.json")) ? Path.Combine(DataRoot, Path.GetFileName(session) + ".zip") : Bundle();
            if (!File.Exists(zip)) throw new InvalidOperationException("Original upload ZIP is missing. Export locally and contact the organizer; no new upload was created.");
            var authorization = githubAuth?.AcquireAuthorization() ?? throw new InvalidOperationException("Sign in to GitHub in this app before sharing.");
            string url = await GitHubSubmission.Upload(zip, session, authorization, cancellation.Token);
            cancellation.Token.ThrowIfCancellationRequested();
            File.WriteAllText(receipt, JsonSerializer.Serialize(new { url, submittedAt = DateTime.UtcNow }));
            Send(new { kind = "receipt", url });
        }
        catch (OperationCanceledException) { Send(new { kind = "notice", message = "Sharing stopped. Your local files remain, and remote work GitHub already accepted may remain. If repository creation was unconfirmed, arrange a handoff of this session's encrypted submission.nose with the organizer; keep the plaintext ZIP private." }); }
        finally { uploadCancellation = null; sharing = false; }
    }
    void SendAccount() => Send(new { kind = "account", login = githubAuth?.CurrentAccount?.Login, accountId = githubAuth?.CurrentAccount?.Id });
    static bool SessionName(string? name) => name != null && System.Text.RegularExpressions.Regex.IsMatch(name, "^[a-f0-9]{32}$");
    void ListSessions()
    {
        string root = Path.Combine(DataRoot, "sessions");
        var list = new List<object>();
        if (Directory.Exists(root)) foreach (var directory in new DirectoryInfo(root).EnumerateDirectories().OrderByDescending(d => d.LastWriteTimeUtc).Take(100))
        {
            if (!SessionName(directory.Name) || directory.Attributes.HasFlag(FileAttributes.ReparsePoint)) continue;
            string manifestPath = Path.Combine(directory.FullName, "manifest.json");
            if (!File.Exists(manifestPath) || new FileInfo(manifestPath).Length > 200000) continue;
            try { using var manifest = JsonDocument.Parse(File.ReadAllText(manifestPath)); var m = manifest.RootElement; if (m.GetProperty("sessionId").GetString() != directory.Name) continue;
                list.Add(new { id = directory.Name, startedAt = m.GetProperty("startedAt").GetString(), mode = m.GetProperty("mode").GetString() }); }
            catch { /* An incomplete/corrupt session cannot be offered for loading. */ }
        }
        Send(new { kind = "sessions", sessions = list });
    }
    void LoadSession(string? id)
    {
        if (recording || sharing || shotBusy) throw new InvalidOperationException("Finish the current operation before opening an older session.");
        if (!SessionName(id)) throw new InvalidDataException("Invalid session ID");
        var loaded = CollectorSessionFiles.ReadCompleted(Path.Combine(DataRoot, "sessions"), id!);
        // Commit selection only after every source file and counter has validated.
        session = loaded.Folder; mode = loaded.Mode; eventCount = loaded.EventCount; shotCount = loaded.ScreenshotCount;
        Send(new { kind = "loaded", sessionId = id, mode, events = eventCount, screenshots = shotCount, answers = loaded.Answers });
    }
}
