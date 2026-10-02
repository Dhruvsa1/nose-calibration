# Optional per-user installation: no elevation, startup entry, service, or background recording.
# Every file is checked against package-files.json before anything is copied. That check proves
# the extracted folder matches its own manifest; it does not prove who built the package.
# Compare the ZIP's SHA-256 with the organizer's published value for that (see START-HERE.txt).
# -InstallBase and -ShortcutFolder exist for offline tests; participants need no arguments.
param([string]$InstallBase, [string]$ShortcutFolder, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$maxEntries = 1500
$maxFileBytes = 150MB
$maxTotalBytes = 700MB

function Fail([string]$message) { throw [InvalidOperationException]::new($message) }

function Test-Under([string]$path, [string]$root) {
    $p = [IO.Path]::GetFullPath($path).TrimEnd('\') + '\'
    $r = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
    return $p.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)
}

function Test-Reparse([IO.FileSystemInfo]$item) {
    return ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
}

# Lists files under $root without following junctions or symbolic links.
function Get-PackageTree([string]$root) {
    $files = New-Object 'System.Collections.Generic.List[string]'
    $pending = New-Object 'System.Collections.Generic.Stack[IO.DirectoryInfo]'
    $pending.Push([IO.DirectoryInfo]::new($root))
    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        foreach ($item in $dir.EnumerateFileSystemInfos()) {
            $relative = $item.FullName.Substring($root.Length).TrimStart('\').Replace('\', '/')
            if (Test-Reparse $item) { Fail "Link or reparse point found in the extracted folder: $relative" }
            if ($item -is [IO.DirectoryInfo]) { $pending.Push($item) }
            else {
                $files.Add($relative)
                if ($files.Count -gt $maxEntries + 1) { Fail 'The extracted folder holds too many files.' }
            }
        }
    }
    return ,$files
}

function Read-PackageManifest([string]$root) {
    $path = Join-Path $root 'package-files.json'
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { Fail 'package-files.json is missing. Extract the entire ZIP before running Install.ps1.' }
    if ((Get-Item -LiteralPath $path).Length -gt 1MB) { Fail 'package-files.json is unexpectedly large.' }
    $raw = [IO.File]::ReadAllBytes($path)
    $parsed = [Text.Encoding]::UTF8.GetString($raw).TrimStart([char]0xFEFF) | ConvertFrom-Json
    $entries = @($parsed)
    if ($entries.Count -lt 1 -or $entries.Count -gt $maxEntries) { Fail 'package-files.json has an unexpected number of entries.' }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $total = [long]0
    foreach ($entry in $entries) {
        $names = @($entry.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
        if (($names -join ',') -cne 'bytes,path,sha256') { Fail 'package-files.json has an unexpected entry format.' }
        $rel = $entry.path
        if ($rel -isnot [string] -or $rel.Length -lt 1 -or $rel.Length -gt 200 -or $rel -notmatch '^[A-Za-z0-9_+-][A-Za-z0-9._+-]*(/[A-Za-z0-9_+-][A-Za-z0-9._+-]*)*$' -or $rel -match '(^|/)\.\.?(/|$)') {
            Fail "Unsafe path in package-files.json: $rel"
        }
        if ($rel -ieq 'package-files.json') { Fail 'package-files.json lists itself.' }
        if (!$seen.Add($rel)) { Fail "Duplicate path in package-files.json: $rel" }
        if ($entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '^[0-9a-f]{64}$') { Fail "Invalid digest for $rel" }
        if (($entry.bytes -isnot [int] -and $entry.bytes -isnot [long]) -or $entry.bytes -lt 0 -or $entry.bytes -gt $maxFileBytes) { Fail "Invalid size for $rel" }
        $total += $entry.bytes
    }
    if ($total -gt $maxTotalBytes) { Fail 'Package is larger than expected.' }
    if (!$seen.Contains('NoseCalibration.exe')) { Fail 'package-files.json does not list NoseCalibration.exe.' }
    return [pscustomobject]@{ Entries = $entries; Raw = $raw }
}

function Get-Sha256Hex([byte[]]$bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
}

# Streams one file, hashing the bytes as they are read; with $destination it also writes them,
# so the copy is exactly the content that was checked.
function Copy-Checked([string]$source, [string]$destination, $entry) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $in = $null; $out = $null
    try {
        $in = [IO.FileStream]::new($source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($in.Length -ne $entry.bytes) { Fail "File size differs from package-files.json: $($entry.path)" }
        if ($destination) { $out = [IO.FileStream]::new($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None) }
        $buffer = New-Object byte[] 1048576
        $read = [long]0
        while (($n = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $read += $n
            if ($read -gt $entry.bytes) { Fail "File grew while being read: $($entry.path)" }
            [void]$sha.TransformBlock($buffer, 0, $n, $null, 0)
            if ($out) { $out.Write($buffer, 0, $n) }
        }
        [void]$sha.TransformFinalBlock($buffer, 0, 0)
        $digest = ([BitConverter]::ToString($sha.Hash)).Replace('-', '').ToLowerInvariant()
        if ($read -ne $entry.bytes -or $digest -cne $entry.sha256) { Fail "File content differs from package-files.json: $($entry.path)" }
    } finally {
        if ($out) { $out.Dispose() }
        if ($in) { $in.Dispose() }
        $sha.Dispose()
    }
}

function Show-Identity([string]$root) {
    $path = Join-Path $root 'package-source.json'
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { return 'version unknown' }
    try {
        $s = [IO.File]::ReadAllText($path) | ConvertFrom-Json
        $text = "$($s.informationalVersion) ($($s.channel))"
        if ($s.channel -eq 'preview') { $text += ' - development preview, not an approved study release' }
        return $text
    } catch { return 'version unknown' }
}

$exitCode = 1
$destination = $null
$shortcutPath = $null
$previousShortcut = $null
$shortcutWritten = $false
try {
    $sourceRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    if (!(Test-Path -LiteralPath (Join-Path $sourceRoot 'NoseCalibration.exe') -PathType Leaf)) { Fail 'Extract the entire ZIP before running Install.ps1.' }
    if (!$InstallBase) {
        if (!$env:LOCALAPPDATA) { Fail 'LOCALAPPDATA is not set for this account.' }
        $InstallBase = Join-Path $env:LOCALAPPDATA 'Programs\NoseCalibration'
    }
    $InstallBase = [IO.Path]::GetFullPath($InstallBase).TrimEnd('\')
    if (!$ShortcutFolder) { $ShortcutFolder = [Environment]::GetFolderPath('Programs') }
    if (!$ShortcutFolder) { Fail 'The Start menu folder for this account could not be found.' }
    $ShortcutFolder = [IO.Path]::GetFullPath($ShortcutFolder).TrimEnd('\')

    # Recordings stay where the collector keeps them; the installer never writes there.
    $recordingRoots = @()
    if ($env:LOCALAPPDATA) { $recordingRoots += Join-Path $env:LOCALAPPDATA 'NoseCalibration' }
    $knownLocal = [Environment]::GetFolderPath('LocalApplicationData')
    if ($knownLocal) { $recordingRoots += Join-Path $knownLocal 'NoseCalibration' }
    foreach ($target in @($InstallBase, $ShortcutFolder)) {
        foreach ($recordings in $recordingRoots) {
            if ((Test-Under $target $recordings) -or (Test-Under $recordings $target)) { Fail "Refusing to write in or above the recordings folder: $target" }
        }
        if ((Test-Under $target $sourceRoot) -or (Test-Under $sourceRoot $target)) { Fail "Refusing to install into or above the extracted package folder: $target" }
    }

    Write-Host 'Checking every file against package-files.json...'
    $manifest = Read-PackageManifest $sourceRoot
    $present = Get-PackageTree $sourceRoot
    $listed = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $manifest.Entries) { [void]$listed.Add($entry.path) }
    foreach ($rel in $present) {
        if ($rel -ieq 'package-files.json') { continue }
        if (!$listed.Contains($rel)) { Fail "File not listed in package-files.json: $rel. Extract a fresh copy of the ZIP into an empty folder." }
    }
    foreach ($entry in $manifest.Entries) {
        $file = Join-Path $sourceRoot $entry.path.Replace('/', '\')
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) { Fail "Missing package file: $($entry.path). Extract the entire ZIP." }
        Copy-Checked $file $null $entry
    }

    if (Test-Path -LiteralPath $InstallBase) {
        if (Test-Reparse (Get-Item -LiteralPath $InstallBase -Force)) { Fail "Install folder is a link or reparse point: $InstallBase" }
    } else { [void][IO.Directory]::CreateDirectory($InstallBase) }
    $name = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $candidate = Join-Path $InstallBase $name
    if (Test-Path -LiteralPath $candidate) { Fail 'Install folder name collision; run the installer again.' }
    [void][IO.Directory]::CreateDirectory($candidate)
    $destination = $candidate

    Write-Host "Copying $(@($manifest.Entries).Count) checked files..."
    foreach ($entry in $manifest.Entries) {
        $target = Join-Path $destination $entry.path.Replace('/', '\')
        $parent = Split-Path $target -Parent
        if (!(Test-Path -LiteralPath $parent)) { [void][IO.Directory]::CreateDirectory($parent) }
        Copy-Checked (Join-Path $sourceRoot $entry.path.Replace('/', '\')) $target $entry
    }
    [IO.File]::WriteAllBytes((Join-Path $destination 'package-files.json'), $manifest.Raw)

    if (!(Test-Path -LiteralPath $ShortcutFolder -PathType Container)) { Fail "Start menu folder not found: $ShortcutFolder" }
    $shortcutPath = Join-Path $ShortcutFolder 'Nose Calibration.lnk'
    if (Test-Path -LiteralPath $shortcutPath) {
        $existing = Get-Item -LiteralPath $shortcutPath -Force
        if ($existing -isnot [IO.FileInfo] -or (Test-Reparse $existing)) { Fail "Existing shortcut is not a regular file: $shortcutPath" }
        $previousShortcut = [IO.File]::ReadAllBytes($shortcutPath)
    }
    # Build the shortcut beside the new install, then copy it into Start in one step.
    $staged = Join-Path $destination ('shortcut-' + [guid]::NewGuid().ToString('N') + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($staged)
    $shortcut.TargetPath = Join-Path $destination 'NoseCalibration.exe'
    $shortcut.WorkingDirectory = $destination
    $shortcut.Description = 'Nose Calibration: consent-based local practice recording'
    $shortcut.Save()
    $shortcutWritten = $true
    [IO.File]::Copy($staged, $shortcutPath, $true)
    [IO.File]::Delete($staged)

    Write-Host ''
    Write-Host "Installed Nose Calibration $(Show-Identity $sourceRoot)" -ForegroundColor Green
    Write-Host "  Folder:   $destination"
    Write-Host "  Shortcut: $shortcutPath"
    Write-Host 'Open Nose Calibration from Start. Recording stays off until you consent and start a session.'
    Write-Host 'Files matched package-files.json. That shows the folder is complete and unmodified relative to'
    Write-Host 'its own list; it does not show who built it. Compare the ZIP checksum as described in START-HERE.txt.'
    Write-Host 'Earlier installs, if any, were left in place. To uninstall: delete the Start shortcut and the'
    Write-Host "folders under $InstallBase. Your recordings remain in LocalAppData\NoseCalibration."
    $exitCode = 0
} catch {
    $reason = $_.Exception.Message
    if ($destination -and (Test-Under $destination $InstallBase) -and (Test-Path -LiteralPath $destination)) {
        try { Remove-Item -LiteralPath $destination -Recurse -Force } catch { $reason += " (Could not remove the partial folder $destination; delete it manually.)" }
    }
    if ($shortcutWritten -and $shortcutPath) {
        try {
            if ($null -ne $previousShortcut) { [IO.File]::WriteAllBytes($shortcutPath, $previousShortcut) }
            elseif ((Test-Path -LiteralPath $shortcutPath) -and $destination) {
                $current = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath).TargetPath
                if ($current -and (Test-Under $current $destination)) { Remove-Item -LiteralPath $shortcutPath -Force }
            }
        } catch { $reason += ' (Could not restore the previous Start shortcut.)' }
    }
    Write-Host ''
    Write-Host 'Nose Calibration was NOT installed.' -ForegroundColor Red
    Write-Host "Reason: $reason"
    Write-Host 'Nothing in your recordings folder was changed, and any earlier install and Start shortcut were kept.'
    Write-Host 'You can still run NoseCalibration.exe directly from the extracted folder.'
}
if (!$NoPause -and [Environment]::UserInteractive -and $Host.Name -eq 'ConsoleHost') {
    try { [void](Read-Host 'Press Enter to close this window') } catch { }
}
exit $exitCode
