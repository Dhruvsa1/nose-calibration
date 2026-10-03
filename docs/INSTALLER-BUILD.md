# Conventional Windows installer

The installer is a development addition. It does not replace the live-upload,
clean-machine, signing, or participant-release gates in README.md.

Build a reviewed Collector ZIP first, using `tools/package.ps1`. Obtain Inno
Setup from its official download page and verify the publisher signature before
running the compiler installer. Inno Setup is a build dependency only; participants
do not need it. The 7.1.0 x64 compiler supports portable installation.

Prepare the pinned Microsoft WebView2 bootstrapper once (see below), then run
with Python on the build machine:

```text
python tools/webview2_bootstrapper.py fetch
python tools/build_installer.py <package.zip> --expected-sha256 <verified ZIP hash> --compiler <absolute path to ISCC.exe>
```

`--check-only` verifies the inputs without compiling. The build copies the input
into a bounded temporary snapshot, verifies the complete package and its pinned
public identifiers, requires the PDF, and compiles only that snapshot. It also
copies the bootstrapper (`--webview2-bootstrapper`, default
`vendor/webview2/MicrosoftEdgeWebview2Setup.exe`) into the same private
snapshot and verifies it against the pin before compiling. Output is
placed in a new folder under `work/`, alongside a SHA-256 file and source-package
provenance. A hash does not authenticate the publisher. The output remains
unsigned unless a separate verified signing step is added.

The installer installs for the current user, adds a Start menu shortcut and a
standard uninstall entry. It requests no administrator elevation, starts no app
or recording, and installs no service or login startup task. If Microsoft Edge
WebView2 Runtime is missing, it first runs Microsoft's bundled bootstrapper as
described below. Recordings live
outside the program directory and are not removed by uninstall. Installation
and uninstall still need runtime verification, including preservation of existing
recordings and behavior when Collector is open.

## Microsoft Edge WebView2 Runtime prerequisite

The ZIP bundles .NET and the WebView2 SDK/loader, not the Edge-based WebView2
Runtime itself. Setup therefore handles the runtime, following Microsoft's
documented Evergreen deployment workflow (sources retrieved October 2, 2026):

- Distribution and detection rules:
  https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
  (page updated 2026-10-02).
- Official bootstrapper download page:
  https://developer.microsoft.com/en-us/microsoft-edge/webview2/
- Bootstrapper link `https://go.microsoft.com/fwlink/p/?LinkId=2124703`, as used
  in Microsoft's own deployment sample:
  https://github.com/MicrosoftEdge/WebView2Samples/blob/main/SampleApps/WV2DeploymentWiXCustomActionSample/Product.wxs

In `PrepareToInstall`, after the running-app and setup mutex checks and before any
file is installed, Setup checks the `pv` value under
`HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`
and the same client key under `HKCU\Software\Microsoft`. A version above 0.0.0.0
in either means the runtime is present and nothing else happens. Otherwise
Setup asks the user, extracts the bundled bootstrapper to its private temporary
folder, re-hashes it through a deny-write handle held until the bootstrapper
exits, and runs `MicrosoftEdgeWebview2Setup.exe /silent /install` with Setup's own
unelevated credentials. Per Microsoft, a non-elevated run installs per-user; a
per-machine Edge updater, where present, replaces it with a per-machine install.
Setup requests no elevation. It continues only when the same registry check then
detects the runtime. Declining, an integrity failure, a launch failure, a reported
restart, or a runtime that is still undetected stops Setup before Nose Calibration is installed.
Microsoft's installer is never killed, and nothing removes an existing runtime.
Microsoft does not document the bootstrapper's exit codes, so detection, not the
exit code, decides success.

Prompts and exit codes:

- Interactive runs ask before the runtime is installed. While Microsoft's
  installer runs, the wizard Cancel button is disabled and Cancel clicks are
  ignored. After 10 minutes a Retry/Cancel box lets the user keep waiting or
  stop. If Microsoft's installer reports a restart and the
  runtime is still undetected, Setup shows the restart message and Inno's own
  "restart now?" choice, then exits 8 without installing Nose Calibration.
- `/SILENT` or `/VERYSILENT` without `/SUPPRESSMSGBOXES` still shows the consent
  and 10-minute boxes, which wait for an answer.
- With `/SUPPRESSMSGBOXES`, the consent box is answered Yes automatically, so
  Microsoft's installer downloads the runtime without a question. The 10-minute
  box is answered Cancel.
- A silent run never requests a restart, even without `/NORESTART`. A reported
  restart exits 7 with the same "restart Windows, then run this setup again"
  message. Without that guard, Inno would restart a `/VERYSILENT` run without
  asking. Every other stop also exits 7.

Pin and verification policy, recorded in `docs/webview2-bootstrapper.json`:

- `tools/webview2_bootstrapper.py fetch` downloads only from the fixed official
  link and follows HTTPS redirects only to allowlisted `*.microsoft.com` hosts.
  It accepts the file only if its size, SHA-256 and file version match the pin
  and its embedded Authenticode signature is Valid. The signer must be Microsoft
  Corporation, with the pinned certificate thumbprint and issuer, the
  code-signing usage, and a chain to an allowed Microsoft root. The file goes
  to ignored `vendor/webview2/`. The check is static: the file is never run on
  the build machine.
- Microsoft updates this bootstrapper in place behind the same link. A
  different file is rejected; nothing falls back to "latest". To refresh, run
  `python tools/webview2_bootstrapper.py inspect <file>` on a copy downloaded
  from the official link. Review its signer and source, then update every
  pin field together in a reviewed commit.
- The build re-verifies a private snapshot, passes its path and pinned hash to
  ISCC, and the `[Files]` `Hash:` parameter makes the compiler reject any other
  bytes. Build provenance records the bootstrapper facts,
  `executedDuringBuild: false` and `missingRuntimeInstallTested: false`.

Pinned on October 2, 2026 (2026-10-03 01:19 UTC): `MicrosoftEdgeWebview2Setup.exe`,
2,002,128 bytes, SHA-256
`48a7b31419a8eb4fffdc7b6a02f6b4dfda60687fc897116be15370e10c2b66a7`, file version
1.3.273.21 ("Microsoft Edge Update Setup"). Its Authenticode status was Valid, signed by
CN=Microsoft Corporation (thumbprint `4028CAD637509D4744B17EC5B42AED8D7A31E6AF`).
The chain runs Microsoft Code Signing PCA 2024 →
Microsoft Root Certificate Authority 2011 (`8F43288AD272F3103B6FB1428485EA3014C0BCFE`),
with a Microsoft Time-Stamp Service countersignature. The redirect target was
`msedge.sf.dl.delivery.mp.microsoft.com` (Last-Modified October 1, 2026).

The signer certificate is valid until April 15, 2027. The build checks its chain
at the current time, so `fetch` and `build_installer.py` fail closed from that
date, even though the timestamp keeps Windows' Authenticode status Valid.
Refresh the pin before then (see above). Already built installers are unaffected.

Not yet verified: the missing-runtime path has only been compile-checked and
reviewed as source. It has not run on a machine without the runtime, so the
consent, progress, disabled Cancel, 10-minute Retry/Cancel, restart and silent
paths are untested. Complete the checklist below before relying on it.
Windows 11 includes the runtime.

### Missing-runtime acceptance checklist (status: NOT RUN)

Every item is NOT RUN. Use a setup EXE built by `build_installer.py` from
reviewed source with the pinned bootstrapper. Record the exit code and keep the
`/LOG` file for each item.

1. Environment: a disposable Windows 10 x64 VM snapshot, signed in as a
   standard (non-admin) user. Before each item, confirm the runtime is absent:
   `reg query` for the `pv` value must fail under both client keys named above
   (HKLM `WOW6432Node` and HKCU).
2. Decline the consent prompt: stop message, exit 7.
3. Network off, accept: progress page, then a stop message with a hex code,
   exit 7.
4. Wait and timeout: while Microsoft's installer runs, the wizard Cancel button
   is greyed out and clicking it or the window Close button does nothing; it is
   enabled again afterwards. With a throttled link, after 10 minutes Retry keeps
   waiting and Cancel stops (exit 7) while Microsoft's installer keeps running.
5. Detection: network on, accept. No UAC prompt; record which key now holds
   `pv`; Setup continues and installs Nose Calibration.
6. No app copy on every stop (items 2-4, 7 and 8): no
   `%LOCALAPPDATA%\Programs\NoseCalibration\releases` folder, no Start menu
   entry and no uninstall entry.
7. Silent, fresh snapshot: `/VERYSILENT /SUPPRESSMSGBOXES /LOG` without
   `/NORESTART` installs the runtime without a question and exits 0. If a
   restart-required result can be provoked, there is no reboot, exit 7, and the
   log shows the restart message. `/SILENT` without `/SUPPRESSMSGBOXES` still
   shows the consent box.
8. Interactive restart (if provokable): restart message and Inno's restart
   choice, exit 8, no app files.
9. Runtime present: rerun Setup after item 5, and once on Windows 11 or another
   machine with the runtime. No prompt appears and installation or upgrade
   proceeds as before. With Collector open, the running-app rejection still
   occurs before any runtime prompt.
10. Recovery and recording off: after a stopped attempt, rerunning Setup on the
    same VM succeeds. After installation Setup starts neither the app nor a
    recording; opening the app from Start shows consent unchecked and Start
    disabled. Uninstall leaves the runtime and existing recordings in place. Setup itself remains unsigned; Microsoft's
signature covers only the bundled bootstrapper.

Do not publish the installer until its package contents, installation, launch,
uninstall and applicable release gates have been verified. The download page
must not advertise an installer as available before a real release exists.

## Local preview evidence — October 2, 2026

Inno Setup 7.1.0 x64 was obtained from the official linked GitHub release; Windows
reported a valid Authenticode signature from Pyrsys B.V. It was installed in
portable mode under ignored build work. Compilation succeeded against public
source package revision `735ff453c425d272c64c571de4486946d4bb6af4`.

Installer SHA-256:
`de7e022fe89a293e11d8945b26b95f4ee86f0f086ae75b0714beb304e7dedbec`.
The installer is unsigned; the compiler vendor signature does not sign our output.

A silent local installation returned exit 0. All 484 installed payload entries
(excluding the intentionally omitted optional PowerShell installer) matched the
source manifest. The Start shortcut resolved to the installed Collector executable
and the standard uninstaller was present. This does not yet verify interactive
wizard behavior, installed-app startup, uninstall preservation, a clean machine,
or live upload. Nothing was published.

Review then identified two upgrade gaps in that first preview. The current source
now uses a separate `releases/<verified payload hash prefix>` program directory
for each payload, preventing obsolete files from entering a new version. It also
uses the `Local\NoseCalibration.Collector.Running` mutex, held by the updated
Collector process and checked by Setup/Uninstall. A separate setup mutex serializes
installers. Older already-running previews do not have this guard and must be
closed manually. Collector builds with zero warnings/errors after the change.
The first installer/hash above predates these fixes; it is not the release candidate.
Rebuilding and runtime verification of these fixes remain required.

The corrected preview subsequently compiled from package SHA-256
`7972cc7cc0cb93e63099a5e799cc9f8f9875e83f97c1c9163b504b54452b77d6`.
Corrected installer SHA-256:
`5388c309c666da6eb5960760d8c731b88c98eacd6421cf5fedf98118cfab1e03`.
With the application's named mutex held by a synthetic test process, the silent
installer exited 1 before creating its versioned installation directory. This
verifies the installer's running-app rejection, not a complete upgrade/uninstall
walkthrough or the Collector-side lifetime guard.

Subsequent local runtime checks: corrected installer installed successfully into
its hash-versioned directory and all 484 payload hashes matched. The installed
Collector opened with consent unchecked/Start disabled and held the expected
mutex. Uninstall was rejected while that real app was open. After closing the
idle app, uninstall returned 0 and removed its executable; SHA-256 comparison
confirmed all 100 existing recording files were unchanged. These are local
silent-mode checks, not interactive-wizard or clean-machine validation.

## Current prerequisite preview: runtime-present verification

The preview built from the reviewed October 2 source has setup SHA-256
570c62938d93721c1c419fe8be8a34ed890098db9c40a84fe51a3783c053e5f1.
One silent per-user upgrade exited 0 in approximately 11 seconds. Setup detected
WebView2 154.0.4258.48 and skipped its bootstrapper; no restart occurred.
All 484 expected payload entries matched size and hash; both previous installed
releases were preserved. Registration and the Start menu target release
938e74155d1fdc2c7553b743. A native launch rendered the welcome page with consent
unchecked and Start disabled, then closed without recording. This updates only
the runtime-present upgrade evidence. The missing-runtime checklist above remains
NOT RUN; clean-machine and live-upload verification are still outstanding.
