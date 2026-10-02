# Nose Calibration

Windows practice-assessment collector, currently a development preview. The collector is a .NET 8 WinForms host with a local WebView2 interface. The web interface contains multiple choice, fill-in-the-blank, dropdown, and two JavaScript coding questions.

## Preview

Build `collector/NoseCalibration.csproj` in Release mode. Microsoft Edge WebView2 Runtime is required. The current preview is `dist/NoseCalibration.exe`; keep the complete `dist` folder together. Earlier builds under `work/preview` are obsolete.

Recording begins only after consent and **Start session**. **Stop recording** or **Submit Test** ends recording. Only the focused assessment page is recorded: pointer, click, keyboard, scrolling, selection and answer metadata; final answers; and click-triggered page screenshots (750 ms throttle, 120-image cap). Other applications and browser tabs are outside the collector's capture scope.

Local sessions are stored under `%LOCALAPPDATA%/NoseCalibration/sessions`. `--verification` marks a developer test session separately so the ingestion validator rejects it as participant data.

## Current verification

- Windows Release build: no warnings or errors.
- Browser walkthrough: all five answers correct, score 5/5, no JavaScript errors; this used a mocked native bridge and is not a Codex input-profile evaluation.
- Native walkthrough: start/stop, question navigation, syntax rendering, a correct coding solution, page screenshot capture and recording files verified. The native smoke test is marked `verification`.
- Claude Code Opus 5.5, high effort, authored the visual HTML/CSS and UI enhancements. Two Opus sessions inspected all 30 manually filtered tutorial UI frames. Reference captures and review evidence remain local under ignored `work/`.
- Large-file transport: a 2 MB synthetic encrypted payload was uploaded to a private test repository using GitHub's numeric repository routes. Object-media contents metadata and raw-blob SHA-256 verification passed. This used the administrator's existing managed GitHub CLI login; it does not verify the collector's device sign-in or collaborator invitation flow. Contents metadata requests explicitly use `application/vnd.github.object+json` for files over 1 MB.

## Release work still required

The upload implementation is not approved for distribution. Offline tests cover dedicated device sign-in, immutable repository identity, encrypted retry recovery, collaborator permission verification, cancellation and saved-session validation. Live authorization/upload, clean-machine installation and final security review remain required. The collector uses its own registered Nose Calibration OAuth application, keeps access tokens only in memory for at most eight hours, and never reads GitHub CLI credentials. `oauth-client.json` contains only the public application identifier, not a secret.

## Packaging and participant guide

The application project explicitly includes its six web files, four brand images, public recipient key and public OAuth client identifier. It ships no GitHub CLI, researcher credentials, Codex integration or recipient private key. `tools/prepare-dependencies.ps1` currently supplies the separate private administrator's pinned GitHub CLI dependency; it is not required by participants.

`tools/package.ps1 -Preview` creates a self-contained Windows x64 ZIP in a new timestamped `work/packages` folder. It checks the public key and OAuth application pins, rejects known private/session filenames, includes the optional per-user `Install.ps1`, and emits a file digest manifest. Participants can simply extract and run the EXE. The installer copies to a new per-user directory and adds a Start shortcut, without elevation or automatic startup. It has not yet received a clean-machine installation walkthrough.

Run `python tools/verify_package.py <zip>` to independently inspect archive paths, manifest coverage and hashes, required files, public key/client pins and private-key markers without executing the package. Old previews containing a bundled authentication CLI are rejected. This is integrity verification, not a general malware scan or an upload test.

The illustrated three-page `docs/Nose-Calibration-Setup.pdf` is a visually checked draft marked development preview. It covers starting/stopping, practice tasks, optional GitHub sharing, permissions and troubleshooting. Its generator is `tools/create_setup_guide.py`; screenshot assets under `docs/images` show synthetic test content. Update the preview/release wording only after the pending release checks pass.

Sharing is intended to create an encrypted submission in a participant-owned **private** GitHub repository. Personal-account collaborators receive write access to that dedicated repository; this must be disclosed. No researcher credential, private recipient key, or Codex OAuth token belongs in this source tree or distribution. The collector has no Codex integration. Private admin ingestion and profile tooling remain in the private Nose project.

The empirical typing profile is integrated into private Nose's local practice mode and the separate private web Admin host. The Admin host has build and pure-policy test coverage; a live five-question Codex run, fresh recorded comparison, richer mouse/scroll behavior and correction modeling remain pending.

## Branding

The owner-supplied Nose logo is used in the welcome page, assessment header and Windows application icon. `web/branding` contains wordmark and symbol-only versions for light and dark surfaces. The interface renders the transparent artwork with CSS inversion on dark backgrounds. Claude Code Opus 5.5 at high effort authored the visual changes. Layout audits cover compact, portrait and large viewports, editor state through live resizing, and keyboard navigation. The Windows host enforces a DPI-aware 720×560 CSS-pixel minimum client area, capped for smaller screens. The current system-DPI-aware mode can be blurred by Windows when moved between monitors with different scaling; mixed-monitor DPI switching has not been validated. Escape moves from the code editor to Run code without changing the answer; Tab continues to indent.

Do not remove consent, recording scope, focus checks, stop controls, size limits, CSP restrictions, or any existing question/grading functionality when refining the interface.
