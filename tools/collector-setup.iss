; Compile only against a staged package that passed tools/verify_package.py.
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
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "Install.ps1"

[Icons]
Name: "{userprograms}\Nose Calibration"; Filename: "{app}\NoseCalibration.exe"; WorkingDir: "{app}"

; Deliberately no Run, Registry, Tasks, InstallDelete, or UninstallDelete section.
; Opening the installed app and starting a recording remain explicit user actions.
; Uninstall removes installed program files, never the separate session directory.
