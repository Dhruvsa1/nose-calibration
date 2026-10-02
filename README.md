# Nose Calibration

Windows practice-assessment collector, currently a development preview. The collector is a .NET 8 WinForms host with a local WebView2 interface. The web interface contains multiple choice, fill-in-the-blank, dropdown, and two JavaScript coding questions.

## Preview

Build `collector/NoseCalibration.csproj` in Release mode. Microsoft Edge WebView2 Runtime is required. The current preview is `dist/NoseCalibration.exe`; keep the complete `dist` folder together. Earlier builds under `work/preview` are obsolete.

Recording begins only after consent and **Start session**. **Stop recording** or **Submit Test** ends recording. Only the focused assessment page is recorded: pointer, click, keyboard, scrolling, selection and answer metadata; final answers; and click-triggered page screenshots (750 ms throttle, 120-image cap). Other applications and browser tabs are outside the collector's capture scope.

Local sessions are stored under `%LOCALAPPDATA%/NoseCalibration/sessions`. `--verification` marks a developer test session separately so the ingestion validator rejects it as participant data.

## Current verification

- Windows Release build: no warnings or errors.
- Selected-repository migration: 85 offline authentication scenarios, 72 upload scenarios, and 40 synthetic intake-message checks pass. Archive preflight rejects embedded ZIP64 directory overrides; the private validator also accepts a synthetic .NET archive at the collector's 120-screenshot limit.
- The rebuilt preview package passed manifest/hash and public-registration checks, included the four-page PDF, and opened successfully with recording disabled before consent. This is a local startup check, not a clean-machine installation or live upload test.
- Browser walkthrough: all five answers correct, score 5/5, no JavaScript errors; this used a mocked native bridge and is not a Codex input-profile evaluation.
- Native walkthrough: start/stop, question navigation, syntax rendering, a correct coding solution, page screenshot capture and recording files verified. The native smoke test is marked `verification`.
- Claude Code Opus 5.5, high effort, authored the visual HTML/CSS and UI enhancements. Two Opus sessions inspected all 30 manually filtered tutorial UI frames. Reference captures and review evidence remain local under ignored `work/`.
- Large-file transport: a 2 MB synthetic encrypted payload was uploaded to a private test repository using GitHub's numeric repository routes. Object-media contents metadata and raw-blob SHA-256 verification passed. This used the administrator's existing managed GitHub CLI login; it does not verify the collector's device sign-in or collaborator invitation flow. Contents metadata requests explicitly use `application/vnd.github.object+json` for files over 1 MB.

## Release work still required

The upload implementation is not approved for distribution. Offline tests cover selected-repository GitHub App device sign-in, immutable repository identity, encrypted retry recovery, collaborator permission verification, cancellation and saved-session validation. Live authorization/upload with this App, clean-machine installation and final security review remain required. The registered App is pinned to App ID `5167786`, client ID `Iv23li4JwAA8Kc5EWiCM` and slug `nose-calibration`. Its only repository permissions are **Contents: read and write** and **Metadata: read-only**. The collector requires an installation selecting exactly the participant's private personal repository `nose-calibration-submissions`.

Access tokens stay in memory for at most eight hours; refresh tokens are discarded. The collector does not read GitHub CLI credentials. `oauth-client.json` contains public registration identifiers, not a secret. Registration and installation on the organizer's single selected private inbox succeeded without generating an App private key or client secret. The Collector's live device authorization and upload are separate release checks and remain pending.

## Optional sharing: first time

On Results, the setup buttons open fixed GitHub pages. Finish each step on GitHub; the collector does not create repositories, install the App or invite people automatically.

1. **Create repository:** in your personal account, create `nose-calibration-submissions` and choose **Private**. Reuse this one repository for later recordings.
2. **Install app:** install **Nose Calibration**, choose **Only select repositories**, and select only `nose-calibration-submissions`. Do not choose **All repositories**. Check that the permissions are Contents read/write and Metadata read-only.
3. **Open my repositories:** open that repository, then **Settings > Collaborators > Add people**, and invite **Dhruvsa1** once. The organizer must accept. Add no other collaborators; they block sharing.

For each recording, just:

1. Choose **Sign in to GitHub** if needed. Enter only the code displayed by this collector at `github.com/login/device`, authorize Nose Calibration and check the displayed account. Never enter a code someone sends you.
2. Read the sharing notice, consent, then choose **Encrypt and share**. Wait for the result. If encrypted data is stored but organizer access is not confirmed, wait for acceptance and share again to verify; the app cannot see pending invitations and issues no final receipt until access is verified.

The organizer has standing **write access** to this inbox, including future shared sessions, until you remove them in repository settings. They can decrypt submitted recordings. Numeric session metrics may receive optional Codex advisory review; raw code, key presses and screenshots are not automatically sent to a model. **Sign out** clears the local token; it does not revoke the GitHub grant. To revoke it, use GitHub **Settings > Applications > Authorized GitHub Apps**; manage or uninstall the repository installation under **Installed GitHub Apps**. Removing the organizer, revoking the App grant and uninstalling the App are separate controls and do not erase copies already received.

## Packaging and participant guide

The application project explicitly includes its six web files, four brand images, public recipient key and public GitHub App identifiers. It ships no GitHub CLI, researcher credentials, Codex integration or recipient private key. `tools/prepare-dependencies.ps1` currently supplies the separate private administrator's pinned GitHub CLI dependency; it is not required by participants.

`tools/package.ps1 -Preview` creates a self-contained Windows x64 ZIP in a new timestamped `work/packages` folder. It checks the public key and GitHub App pins, rejects known private/session filenames, includes the optional per-user `Install.ps1`, and emits a file digest manifest. Participants can simply extract and run the EXE. The installer copies to a new per-user directory and adds a Start shortcut, without elevation or automatic startup. It has not yet received a clean-machine installation walkthrough.

Run `python tools/verify_package.py <zip>` to independently inspect archive paths, manifest coverage and hashes, required files, public key/client pins and private-key markers without executing the package. Old previews containing a bundled authentication CLI are rejected. This is integrity verification, not a general malware scan or an upload test.

The illustrated four-page `docs/Nose-Calibration-Setup.pdf` is a visually checked development-preview draft updated for the selected-repository GitHub App flow. It separates one-time setup from the two steps for each recording, with readable details from the approved synthetic sharing-panel screenshot. It covers starting/stopping, practice tasks, optional GitHub sharing, permissions and troubleshooting. Its generator is `tools/create_setup_guide.py`; screenshot assets under `docs/images` show synthetic test content. Update the preview/release wording only after the pending release checks pass.

Sharing stores each encrypted submission under `submissions/{sessionId}/submission.nose` in the participant-owned **private** inbox repository. Personal-account collaborators receive write access to that dedicated repository; this must be disclosed. No researcher credential, private recipient key, or Codex OAuth token belongs in this source tree or distribution. The collector has no Codex integration. Private admin ingestion and profile tooling remain in the private Nose project.

The empirical typing profile is integrated into private Nose's local practice mode and the separate private web Admin host. The Admin host has build and pure-policy test coverage. A complete native Codex run scored 5/5 with all five grades passing. A matched human comparison is saved privately; it does not establish general behavior or correctness. The revised input profile and another end-to-end accuracy evaluation remain pending.

## Branding

The owner-supplied Nose logo is used in the welcome page, assessment header and Windows application icon. `web/branding` contains wordmark and symbol-only versions for light and dark surfaces. The interface renders the transparent artwork with CSS inversion on dark backgrounds. Claude Code Opus 5.5 at high effort authored the visual changes. Layout audits cover compact, portrait and large viewports, editor state through live resizing, and keyboard navigation. The Windows host enforces a DPI-aware 720Ã—560 CSS-pixel minimum client area, capped for smaller screens. The current system-DPI-aware mode can be blurred by Windows when moved between monitors with different scaling; mixed-monitor DPI switching has not been validated. Escape moves from the code editor to Run code without changing the answer; Tab continues to indent.

The latest browser regression preserved a multiline code answer while resizing through 1440Ã—900, 720Ã—560, 900Ã—1200, 1920Ã—1080 and 800Ã—640, with no horizontal page overflow. This uses a mocked native bridge and does not start real recording. The host-stop regression also verifies answer persistence, session binding, idempotent finalization and that input capture remains stopped.

Do not remove consent, recording scope, focus checks, stop controls, size limits, CSP restrictions, or any existing question/grading functionality when refining the interface.
