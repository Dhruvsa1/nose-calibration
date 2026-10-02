param([switch]$Preview, [switch]$CheckSourceOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$channel = if ($Preview) { 'preview' } else { 'release' }

# Source identity: releases come only from a committed, clean tree. Previews may be dirty, and say so.
function Invoke-Git([string[]]$arguments) {
    $result = & git -C $projectRoot @arguments 2>$null
    if ($LASTEXITCODE -ne 0) { throw "git $($arguments -join ' ') failed; packaging needs the project's Git checkout." }
    return $result
}
if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required to record the source revision.' }
$revision = [string](Invoke-Git @('rev-parse', '--verify', 'HEAD^{commit}'))
if ($revision -cnotmatch '^[0-9a-f]{40}$') { throw 'Could not resolve the source revision.' }
$changes = @(Invoke-Git @('-c', 'core.quotepath=false', 'status', '--porcelain=v1', '--untracked-files=all') | Where-Object { $_ })
$inputs = @('collector/NoseCalibration.csproj', 'collector/nose.ico', 'public-key.pem', 'oauth-client.json', 'docs/security-pins.json',
    'docs/PACKAGE-README.txt', 'docs/Nose-Calibration-Setup.pdf', 'tools/Install.ps1', 'tools/verify_package.py')
$untrackedInputs = @($inputs | Where-Object { (Test-Path -LiteralPath (Join-Path $projectRoot $_)) -and !(Invoke-Git @('ls-files', '--', $_)) })
if (!$Preview) {
    if ($changes.Count) { throw "Release packages require a clean committed tree; $($changes.Count) uncommitted change(s). Commit or use -Preview." }
    if ($untrackedInputs.Count) { throw "Release inputs must be committed: $($untrackedInputs -join ', ')" }
    if ((Get-Content -LiteralPath (Join-Path $projectRoot 'docs/PACKAGE-README.txt') -Raw) -match '(?i)development preview') {
        throw 'docs/PACKAGE-README.txt still describes a development preview. Update it after the release checks pass, or use -Preview.'
    }
}
[xml]$project = Get-Content -LiteralPath (Join-Path $projectRoot 'collector/NoseCalibration.csproj') -Raw
$version = [string]$project.Project.PropertyGroup.VersionPrefix
if ($version -cnotmatch '^\d+\.\d+\.\d+$') { throw 'collector/NoseCalibration.csproj needs a VersionPrefix such as 0.1.0.' }
$dirty = $changes.Count -gt 0
$sourceId = $revision + $(if ($dirty) { '.dirty' } else { '' })
$informational = $version + $(if ($Preview) { '-preview' } else { '' }) + '+' + $sourceId
$shown = @($changes | Select-Object -First 50 | ForEach-Object { $p = $_.Substring([Math]::Min(3, $_.Length)); if ($p.Length -gt 200) { $p.Substring(0, 200) } else { $p } })
$source = [ordered]@{
    schema = 1
    product = 'NoseCalibration'
    channel = $channel
    version = $version
    informationalVersion = $informational
    sourceRevision = $revision
    sourceTreeClean = !$dirty
    uncommittedPathCount = $changes.Count
    uncommittedPaths = $shown
    uncommittedPathsTruncated = $changes.Count -gt $shown.Count
    runtimeIdentifier = 'win-x64'
    selfContained = $true
    targetFramework = [string]$project.Project.PropertyGroup.TargetFramework
    bundledRuntimeVersion = $null
    sdkVersion = $null
    builtAtUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
if ($CheckSourceOnly) { $source | ConvertTo-Json -Depth 4; return }

$pin = Get-Content -LiteralPath (Join-Path $projectRoot 'docs/security-pins.json') -Raw | ConvertFrom-Json
$publicKey = Get-Content -LiteralPath (Join-Path $projectRoot 'public-key.pem') -Raw
if (!$publicKey.StartsWith('-----BEGIN PUBLIC KEY-----') -or $publicKey.Contains('PRIVATE')) {
    throw 'Expected a public-only recipient key.'
}
$der = [Convert]::FromBase64String(($publicKey -replace '-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s',''))
$sha = [Security.Cryptography.SHA256]::Create()
try { $keyDigest = ([BitConverter]::ToString($sha.ComputeHash($der))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
if ($keyDigest -ne $pin.recipientSpkiSha256) { throw 'Recipient public key differs from reviewed pin.' }
if (!$Preview -and !(Test-Path -LiteralPath (Join-Path $projectRoot 'oauth-client.json'))) { throw 'Dedicated GitHub App registration is required.' }
if (Test-Path -LiteralPath (Join-Path $projectRoot 'oauth-client.json')) {
    $client = Get-Content -LiteralPath (Join-Path $projectRoot 'oauth-client.json') -Raw | ConvertFrom-Json
    if ($client.clientId -cne $pin.githubAppClientId -or $client.appId -ne $pin.githubAppId -or $client.slug -cne $pin.githubAppSlug -or @($client.PSObject.Properties).Count -ne 3) { throw 'GitHub App registration differs from reviewed pins.' }
}
$guide = Join-Path $projectRoot 'docs/Nose-Calibration-Setup.pdf'
if (!$Preview -and !(Test-Path -LiteralPath $guide)) { throw 'Participant setup PDF is required for a release package.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$output = Join-Path $projectRoot "work/packages/$stamp/NoseCalibration"
New-Item -ItemType Directory -Path $output -Force | Out-Null
$source.sdkVersion = [string](& dotnet --version)
dotnet publish (Join-Path $projectRoot 'collector/NoseCalibration.csproj') -c Release -r win-x64 --self-contained true -o $output `
    "-p:VersionSuffix=$(if ($Preview) { 'preview' } else { '' })" "-p:SourceRevisionId=$sourceId"
if ($LASTEXITCODE -ne 0) { throw 'Publish failed.' }
$runtime = Get-Content -LiteralPath (Join-Path $output 'NoseCalibration.runtimeconfig.json') -Raw | ConvertFrom-Json
$source.bundledRuntimeVersion = [string](@($runtime.runtimeOptions.includedFrameworks | Where-Object { $_.name -eq 'Microsoft.NETCore.App' })[0].version)
if ($pin.minimumBundledRuntime -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid minimum runtime pin.' }
$minimumRuntime = [version]$pin.minimumBundledRuntime
foreach ($frameworkName in @('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App')) {
    $versions = @($runtime.runtimeOptions.includedFrameworks | Where-Object { $_.name -eq $frameworkName })
    if ($versions.Count -ne 1 -or $versions[0].version -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw "Missing or invalid bundled runtime: $frameworkName" }
    $runtimeVersion = [version]$versions[0].version
    if ($runtimeVersion.Major -ne $minimumRuntime.Major -or $runtimeVersion.Minor -ne $minimumRuntime.Minor -or $runtimeVersion -lt $minimumRuntime) {
        throw "Bundled $frameworkName $runtimeVersion does not meet reviewed runtime pin $minimumRuntime. Use the reviewed SDK before packaging."
    }
}
$stamped = (Get-Item -LiteralPath (Join-Path $output 'NoseCalibration.dll')).VersionInfo.ProductVersion
if ($stamped -cne $informational) { throw "Built product version '$stamped' does not match '$informational'." }
Copy-Item -LiteralPath (Join-Path $projectRoot 'tools/Install.ps1') -Destination $output
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/PACKAGE-README.txt') -Destination (Join-Path $output 'START-HERE.txt')
if (Test-Path -LiteralPath $guide) { Copy-Item -LiteralPath $guide -Destination $output }
$source | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'package-source.json') -Encoding utf8
# Publish includes only explicit application content, never the source workspace or session data.
$forbidden = Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object {
    $_.Name -match '(?i)(^\.env|private\.pem$|\.dpapi$|\.nose$|\.zip$|\.py[cw]?$|^hosts\.yml$|^auth\.json$|^events\.jsonl$|^answers\.json$|^manifest\.json$|^upload-state\.json$|^summary\.json$|^receipt\.json$|^enrollment.*\.json$|^intake.*\.json$|^click-\d+\.jpg$)'
}
if ($forbidden) { throw 'Private or recording files found in package; distribution aborted.' }
$manifest = Get-ChildItem -LiteralPath $output -Recurse -File | ForEach-Object {
    [ordered]@{ path = $_.FullName.Substring($output.TrimEnd('\').Length + 1).Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); bytes = $_.Length }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'package-files.json') -Encoding utf8
$label = if ($Preview) { "$version-preview-$($revision.Substring(0, 12))$(if ($dirty) { '-dirty' })" } else { "$version-$($revision.Substring(0, 12))" }
$zipName = "NoseCalibration-win-x64-$label-$stamp.zip"
$zipPath = Join-Path (Split-Path $output -Parent) $zipName
Compress-Archive -LiteralPath $output -DestinationPath $zipPath -CompressionLevel Optimal
python (Join-Path $PSScriptRoot 'verify_package.py') $zipPath
if ($LASTEXITCODE -ne 0) { throw 'Independent package verification failed; do not distribute.' }
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
# sha256sum-compatible sidecar. Shipping it beside the ZIP only catches accidental corruption.
[IO.File]::WriteAllText("$zipPath.sha256", "$zipHash  $zipName`n", [Text.UTF8Encoding]::new($false))
Write-Output "Package: $zipPath"
Write-Output "SHA-256: $zipHash  (also in $zipName.sha256)"
Write-Output "Source:  $informational"
Write-Output 'Publish this SHA-256 through a channel separate from the ZIP download (for example the study'
Write-Output 'announcement), so participants can compare it with Get-FileHash before extracting. The checksum'
Write-Output 'file and package-files.json travel with the ZIP and prove nothing about who built it.'
if ($Preview) { Write-Output 'PREVIEW ONLY: packaging does not establish release approval or upload verification.' }
if ($dirty) { Write-Output "Built from uncommitted changes ($($changes.Count)); recorded in package-source.json." }
