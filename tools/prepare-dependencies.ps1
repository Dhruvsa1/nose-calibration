$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pin = Get-Content -LiteralPath (Join-Path $projectRoot 'docs/github-cli-version.json') -Raw | ConvertFrom-Json
if ($pin.url -notmatch '^https://github\.com/cli/cli/releases/download/v[0-9.]+/gh_[0-9.]+_windows_amd64\.zip$') { throw 'Unexpected dependency URL.' }
$scratch = Join-Path $projectRoot ('work/dependencies/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$archive = Join-Path $scratch 'gh.zip'
Invoke-WebRequest -Uri $pin.url -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $pin.archiveSha256) { throw 'Dependency archive checksum mismatch.' }
$expanded = Join-Path $scratch 'expanded'
Expand-Archive -LiteralPath $archive -DestinationPath $expanded
$cliPath = Join-Path $expanded 'bin/gh.exe'
if ((Get-FileHash -LiteralPath $cliPath -Algorithm SHA256).Hash -ne $pin.exeSha256) { throw 'Dependency executable checksum mismatch.' }
$destination = Join-Path $projectRoot 'vendor/gh'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Get-ChildItem -LiteralPath $expanded | Copy-Item -Destination $destination -Recurse -Force
Write-Output 'Pinned GitHub CLI prepared, including its bundled license files.'
