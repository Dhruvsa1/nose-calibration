; Compile only through tools/build_installer.py, against a staged package that passed
; tools/verify_package.py and a WebView2 bootstrapper that passed tools/webview2_bootstrapper.py.
; No administrator access, startup entry, service, credential, or recording.
#ifndef PayloadDir
  #error PayloadDir must identify the verified extracted NoseCalibration directory
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef PackageVersion
  #error PackageVersion is required
#endif
#ifndef PayloadId
  #error PayloadId must be the verified ZIP SHA256 prefix
#endif
#ifndef WebView2Bootstrapper
  #error WebView2Bootstrapper must identify the verified Microsoft bootstrapper snapshot
#endif
#ifndef WebView2BootstrapperSha256
  #error WebView2BootstrapperSha256 must be the pinned bootstrapper SHA-256
#endif

[Setup]
AppId={{BA227D84-FAAE-4A9F-BFA4-AD9D6DD34272}
AppName=Nose Calibration
AppVersion={#PackageVersion}
AppPublisher=Nose Calibration
DefaultDirName={localappdata}\Programs\NoseCalibration\releases\{#PayloadId}
DefaultGroupName=Nose Calibration
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=no
OutputDir={#OutputDir}
OutputBaseFilename=NoseCalibration-Setup-{#PackageVersion}-win-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\NoseCalibration.exe
CloseApplications=no
RestartApplications=no
AppMutex=Local\NoseCalibration.Collector.Running
SetupMutex=Local\NoseCalibration.Collector.Setup
SetupLogging=yes

[Files]
; Listed first so solid-compressed extraction is quick. Never copied to {app}; extracted to
; Setup's private {tmp} only when the runtime is missing. The compiler rejects a hash mismatch.
Source: "{#WebView2Bootstrapper}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy noencryption; Hash: "{#WebView2BootstrapperSha256}"
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "Install.ps1"

[Icons]
Name: "{userprograms}\Nose Calibration"; Filename: "{app}\NoseCalibration.exe"; WorkingDir: "{app}"

; Deliberately no Run, Registry, Tasks, InstallDelete, or UninstallDelete section.
; Opening the installed app and starting a recording remain explicit user actions.
; Uninstall removes installed program files, never the separate session directory
; and never the shared Microsoft Edge WebView2 Runtime.

[Code]
// Microsoft Edge WebView2 Runtime prerequisite. Detection follows Microsoft's documented
// rule (learn.microsoft.com/microsoft-edge/webview2/concepts/distribution): a pv value
// above 0.0.0.0 under the per-machine or per-user EdgeUpdate client key. If it is missing,
// the bundled, build-verified Microsoft bootstrapper runs with Setup's own unelevated
// credentials, so Microsoft installs per-user unless a per-machine updater takes over.
// Every path other than "runtime detected" stops before any program file is installed.
const
  WebView2ClientKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2SetupName = 'MicrosoftEdgeWebview2Setup.exe';
  WebView2SetupArgs = '/silent /install';
  WebView2ExpectedSha256 = '{#WebView2BootstrapperSha256}';
  WaitSliceMs = 250;
  WaitRoundSlices = 2400; // 10 minutes per round, then Retry or Cancel
  WAIT_TIMEOUT_CODE = 258;
  OpenReadDenyWrite = $0020; // fmOpenRead or fmShareDenyWrite
  ERROR_SUCCESS_REBOOT_REQUIRED = 3010;
  ERROR_SUCCESS_RESTART_REQUIRED = 3011;
  ERROR_SUCCESS_REBOOT_INITIATED = 1641;
  ParaBreak = #13#10#13#10;
  OrganizerHint = #13#10#13#10'Nose Calibration was not installed. If this happens again, contact the study organizer.';

type
  // Packed records match the Win32 layout only in a 32-bit Setup (the default; see the guard below).
  TStartupInfoW = record
    cb: DWORD;
    lpReserved, lpDesktop, lpTitle: NativeUInt;
    dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags: DWORD;
    wShowWindow, cbReserved2: Word;
    lpReserved2, hStdInput, hStdOutput, hStdError: NativeUInt;
  end;
  TProcessInformation = record
    hProcess, hThread: NativeUInt;
    dwProcessId, dwThreadId: DWORD;
  end;

function CreateProcessW(lpApplicationName, lpCommandLine: String; lpProcessAttributes, lpThreadAttributes: NativeUInt;
  bInheritHandles: Integer; dwCreationFlags: DWORD; lpEnvironment: NativeUInt; lpCurrentDirectory: String;
  var lpStartupInfo: TStartupInfoW; var lpProcessInformation: TProcessInformation): Integer;
  external 'CreateProcessW@kernel32.dll stdcall';
function WaitForSingleObject(hHandle: NativeUInt; dwMilliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function GetExitCodeProcess(hProcess: NativeUInt; var lpExitCode: DWORD): Integer;
  external 'GetExitCodeProcess@kernel32.dll stdcall';
function CloseHandle(hObject: NativeUInt): Integer;
  external 'CloseHandle@kernel32.dll stdcall';

var
  WebView2Page: TOutputMarqueeProgressWizardPage;
  BootstrapperRunning: Boolean;

function UsableRuntimeVersion(const RootKey: Integer; var Version: String): Boolean;
var
  PackedVersion: Int64;
begin
  Result := False;
  if RegQueryStringValue(RootKey, WebView2ClientKey, 'pv', Version) then
  begin
    Version := Trim(Version);
    Result := (Version <> '') and StrToVersion(Version, PackedVersion) and (PackedVersion > 0);
  end;
end;

function WebView2RuntimeReady: Boolean;
var
  Version: String;
begin
  // HKLM32 is HKLM\SOFTWARE\WOW6432Node on the 64-bit Windows this installer requires.
  Result := UsableRuntimeVersion(HKLM32, Version);
  if Result then
    Log('WebView2 Runtime detected per-machine: ' + Version)
  else begin
    Result := UsableRuntimeVersion(HKCU, Version);
    if Result then
      Log('WebView2 Runtime detected per-user: ' + Version)
    else
      Log('WebView2 Runtime not detected.');
  end;
end;

procedure InitializeWizard;
begin
  WebView2Page := CreateOutputMarqueeProgressPage('Installing Microsoft Edge WebView2 Runtime',
    'Nose Calibration needs this Microsoft component to display its interface.');
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  // While Microsoft's installer runs, the 10-minute Retry/Cancel prompt is the only way to stop
  // waiting, so every outcome still passes through detection before anything is installed.
  if BootstrapperRunning then
    Cancel := False;
end;

function RunBootstrapper(const Path: String; var ExitCode: DWORD; var Message: String): Boolean;
var
  Startup: TStartupInfoW;
  Process: TProcessInformation;
  Slices: Integer;
  Waited: DWORD;
  CancelWasEnabled: Boolean;
begin
  Result := False;
  Startup.cb := 68;
  if CreateProcessW(Path, '"' + Path + '" ' + WebView2SetupArgs, 0, 0, 0, 0, 0, ExpandConstant('{tmp}'),
                    Startup, Process) = 0 then
  begin
    Message := 'Setup could not start the included Microsoft WebView2 installer: ' + SysErrorMessage(DLLGetLastError) + OrganizerHint;
    Exit;
  end;
  try
    WebView2Page.SetText('Downloading and installing from Microsoft. This needs an internet connection and can take a few minutes.', '');
    CancelWasEnabled := WizardForm.CancelButton.Enabled;
    WizardForm.CancelButton.Enabled := False;
    BootstrapperRunning := True;
    WebView2Page.Show;
    try
      Slices := 0;
      repeat
        Waited := WaitForSingleObject(Process.hProcess, WaitSliceMs);
        WebView2Page.Animate;
        Slices := Slices + 1;
        if (Waited = WAIT_TIMEOUT_CODE) and (Slices >= WaitRoundSlices) then
        begin
          if SuppressibleMsgBox('Microsoft''s WebView2 installer has not finished after 10 minutes.'#13#10#13#10 +
               'Choose Retry to keep waiting, or Cancel to stop Setup without installing Nose Calibration.',
               mbError, MB_RETRYCANCEL, IDCANCEL) = IDRETRY then
            Slices := 0
          else begin
            // Microsoft's installer is left to finish or fail on its own; it is never killed.
            Message := 'Microsoft''s WebView2 installer did not finish in time and may still be working in the background.' +
                       ParaBreak + 'Wait a few minutes, then run this setup again. It skips this step once the runtime is ready.' + OrganizerHint;
            Exit;
          end;
        end;
      until Waited <> WAIT_TIMEOUT_CODE;
    finally
      BootstrapperRunning := False;
      WizardForm.CancelButton.Enabled := CancelWasEnabled;
      WebView2Page.Hide;
    end;
    if (Waited <> 0) or (GetExitCodeProcess(Process.hProcess, ExitCode) = 0) then
    begin
      Message := 'Setup could not confirm that Microsoft''s WebView2 installer finished.' + OrganizerHint;
      Exit;
    end;
    Result := True;
  finally
    CloseHandle(Process.hThread);
    CloseHandle(Process.hProcess);
  end;
end;

function InstallWebView2Runtime(var NeedsRestart: Boolean): String;
var
  Path: String;
  Locked: TFileStream;
  ExitCode: DWORD;
begin
  Result := '';
  if IsCurrentProcess64Bit then
  begin
    Result := 'This setup build is misconfigured (64-bit Setup process). Nothing was installed.' + OrganizerHint;
    Exit;
  end;
  if SuppressibleMsgBox('Nose Calibration needs Microsoft Edge WebView2 Runtime, which this computer does not have yet.'#13#10#13#10 +
       'Setup will now run Microsoft''s WebView2 installer, which is included in this setup, to download and install the runtime from Microsoft. ' +
       'It does not ask for administrator access. It needs an internet connection and can take a few minutes.'#13#10#13#10 +
       'Continue?', mbConfirmation, MB_YESNO, IDYES) <> IDYES then
  begin
    Result := 'Nose Calibration needs Microsoft Edge WebView2 Runtime and was not installed. Run this setup again when you are ready.';
    Exit;
  end;
  Path := ExpandConstant('{tmp}\') + WebView2SetupName;
  Locked := nil;
  try
    try
      ExtractTemporaryFile(WebView2SetupName);
      // Hold a deny-write handle from the hash check until Microsoft's installer exits,
      // so the verified file cannot be replaced or renamed in between.
      Locked := TFileStream.Create(Path, OpenReadDenyWrite);
      if CompareText(GetSHA256OfStream(Locked), WebView2ExpectedSha256) <> 0 then
      begin
        Result := 'The included Microsoft WebView2 installer failed its integrity check. Nothing was installed. Do not retry; contact the study organizer.';
        Exit;
      end;
    except
      Result := 'Setup could not prepare the included Microsoft WebView2 installer: ' + GetExceptionMessage + OrganizerHint;
      Exit;
    end;
    if not RunBootstrapper(Path, ExitCode, Result) then
      Exit;
  finally
    if Locked <> nil then
      Locked.Free;
  end;
  Log(Format('Microsoft WebView2 installer exit code: %d (0x%.8x)', [ExitCode, ExitCode]));
  // Microsoft does not document bootstrapper exit codes; registry detection decides success.
  if WebView2RuntimeReady then
    Exit;
  if (ExitCode = ERROR_SUCCESS_REBOOT_REQUIRED) or (ExitCode = ERROR_SUCCESS_RESTART_REQUIRED) or
     (ExitCode = ERROR_SUCCESS_REBOOT_INITIATED) then
  begin
    // Inno restarts a /VERYSILENT run without asking (and /SILENT /SUPPRESSMSGBOXES answers Yes)
    // unless the caller passed /NORESTART, so only an interactive run offers Inno's restart choice.
    NeedsRestart := not WizardSilent;
    Result := 'Microsoft''s WebView2 installer needs Windows to restart. Nose Calibration was not installed.' +
              ParaBreak + 'Restart Windows, then run this setup again.';
  end
  else if ExitCode = 0 then
    Result := 'Microsoft''s WebView2 installer finished, but the runtime is still not detected.' +
              ParaBreak + 'Restart Windows, then run this setup again.' + OrganizerHint
  else
    Result := Format('Microsoft Edge WebView2 Runtime could not be installed (Microsoft installer code 0x%.8x).', [ExitCode]) +
              ParaBreak + 'Check your internet connection, then run this setup again.' + OrganizerHint;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  // Runs after the AppMutex/SetupMutex checks and before any file is installed.
  if WebView2RuntimeReady then
    Result := ''
  else
    Result := InstallWebView2Runtime(NeedsRestart);
end;
