# Conventional Windows installer

The installer is a development addition. It does not replace the live-upload,
clean-machine, signing, or participant-release gates in README.md.

Build a reviewed Collector ZIP first, using `tools/package.ps1`. Obtain Inno
Setup from its official download page and verify the publisher signature before
running the compiler installer. Inno Setup is a build dependency only; participants
do not need it. The 7.1.0 x64 compiler supports portable installation.

Run with Python on the build machine:

```text
python tools/build_installer.py <package.zip> --expected-sha256 <verified ZIP hash> --compiler <absolute path to ISCC.exe>
```

`--check-only` verifies the input without compiling. The build copies the input
into a bounded temporary snapshot, verifies the complete package and its pinned
public identifiers, requires the PDF, and compiles only that snapshot. Output is
placed in a new folder under `work/`, alongside a SHA-256 file and source-package
provenance. A hash does not authenticate the publisher. The output remains
unsigned unless a separate verified signing step is added.

The installer installs for the current user, adds a Start menu shortcut and a
standard uninstall entry. It requests no administrator elevation, starts no app
or recording, and installs no service or login startup task. Recordings live
outside the program directory and are not removed by uninstall. Installation
and uninstall still need runtime verification, including preservation of existing
recordings and behavior when Collector is open.

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
