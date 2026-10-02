$ErrorActionPreference = 'Stop'
# Optional per-user installation: no elevation, startup entry, service, or background recording.
$sourceRoot = $PSScriptRoot
if (!(Test-Path -LiteralPath (Join-Path $sourceRoot 'NoseCalibration.exe'))) { throw 'Extract the entire ZIP before running Install.ps1.' }
$installRoot = Join-Path $env:LOCALAPPDATA ('Programs/NoseCalibration/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Get-ChildItem -LiteralPath $sourceRoot | Copy-Item -Destination $installRoot -Recurse
$shell = New-Object -ComObject WScript.Shell
$startMenu = [Environment]::GetFolderPath('Programs')
$shortcut = $shell.CreateShortcut((Join-Path $startMenu 'Nose Calibration.lnk'))
$shortcut.TargetPath = Join-Path $installRoot 'NoseCalibration.exe'
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = 'Nose Calibration: consent-based local practice recording'
$shortcut.Save()
Write-Output "Installed at $installRoot"
Write-Output 'Open Nose Calibration from Start. Recording stays off until you consent and start a session.'
Write-Output 'To uninstall: remove the Start shortcut and this installation folder. Your recordings remain in LocalAppData/NoseCalibration.'
