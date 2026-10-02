param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pin = Get-Content -LiteralPath (Join-Path $projectRoot 'docs/security-pins.json') -Raw | ConvertFrom-Json
$publicKey = Get-Content -LiteralPath (Join-Path $projectRoot 'public-key.pem') -Raw
if (!$publicKey.StartsWith('-----BEGIN PUBLIC KEY-----') -or $publicKey.Contains('PRIVATE')) {
    throw 'Expected a public-only recipient key.'
}
$der = [Convert]::FromBase64String(($publicKey -replace '-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s',''))
$sha = [Security.Cryptography.SHA256]::Create()
try { $keyDigest = ([BitConverter]::ToString($sha.ComputeHash($der))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
if ($keyDigest -ne $pin.recipientSpkiSha256) { throw 'Recipient public key differs from reviewed pin.' }
if (!$Preview -and !(Test-Path -LiteralPath (Join-Path $projectRoot 'oauth-client.json'))) { throw 'Dedicated GitHub OAuth client registration is required.' }
if (Test-Path -LiteralPath (Join-Path $projectRoot 'oauth-client.json')) {
    $client = Get-Content -LiteralPath (Join-Path $projectRoot 'oauth-client.json') -Raw | ConvertFrom-Json
    if ($client.clientId -cne $pin.oauthClientId -or @($client.PSObject.Properties).Count -ne 1) { throw 'OAuth application identifier differs from reviewed pin.' }
}
$guide = Join-Path $projectRoot 'docs/Nose-Calibration-Setup.pdf'
if (!$Preview -and !(Test-Path -LiteralPath $guide)) { throw 'Participant setup PDF is required for a release package.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$output = Join-Path $projectRoot "work/packages/$stamp/NoseCalibration"
New-Item -ItemType Directory -Path $output -Force | Out-Null
dotnet publish (Join-Path $projectRoot 'collector/NoseCalibration.csproj') -c Release -r win-x64 --self-contained true -o $output
if ($LASTEXITCODE -ne 0) { throw 'Publish failed.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'tools/Install.ps1') -Destination $output
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/PACKAGE-README.txt') -Destination (Join-Path $output 'START-HERE.txt')
if (Test-Path -LiteralPath $guide) { Copy-Item -LiteralPath $guide -Destination $output }
# Publish includes only explicit application content, never the source workspace or session data.
$forbidden = Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object {
    $_.Name -match '(?i)(^\.env|private\.pem$|\.dpapi$|\.nose$|^hosts\.yml$|^auth\.json$|^events\.jsonl$|^answers\.json$|^manifest\.json$|^upload-state\.json$|^summary\.json$|^receipt\.json$|^click-\d+\.jpg$)'
}
if ($forbidden) { throw 'Private or recording files found in package; distribution aborted.' }
$manifest = Get-ChildItem -LiteralPath $output -Recurse -File | ForEach-Object {
    [ordered]@{ path = $_.FullName.Substring($output.TrimEnd('\').Length + 1).Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); bytes = $_.Length }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'package-files.json') -Encoding utf8
$zipPath = Join-Path (Split-Path $output -Parent) "NoseCalibration-win-x64-$stamp.zip"
Compress-Archive -LiteralPath $output -DestinationPath $zipPath -CompressionLevel Optimal
python (Join-Path $PSScriptRoot 'verify_package.py') $zipPath
if ($LASTEXITCODE -ne 0) { throw 'Independent package verification failed; do not distribute.' }
Get-FileHash -LiteralPath $zipPath -Algorithm SHA256 | Format-List
Write-Output "Package: $zipPath"
if ($Preview) { Write-Output 'PREVIEW ONLY: packaging does not establish release approval or upload verification.' }
