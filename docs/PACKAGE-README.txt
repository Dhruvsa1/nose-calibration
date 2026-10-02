NOSE CALIBRATION — WINDOWS x64

Before extracting, check the download. In PowerShell run:
   Get-FileHash -Algorithm SHA256 <path to the downloaded ZIP>
Compare the Hash with the SHA-256 the organizer published for this package,
through a channel separate from the download (for example the study
announcement). If they differ, or no published value exists, do not open the
package; contact the organizer. A .sha256 file downloaded next to the ZIP, and
package-files.json inside it, only detect damage: anyone who changed the package
could change them too. package-source.json names the version and source revision.

1. Extract the entire ZIP into a new, empty folder you own.
2. Open NoseCalibration.exe. Keep all files together.
3. Read the recording notice, check consent, and choose Start session.
4. Work through the practice questions normally. Answer accuracy is optional for human calibration.
5. Choose Submit Test when finished, or Stop recording at any time.
6. Optional sharing setup, once: create a private personal repository named
   nose-calibration-submissions. Install the Nose Calibration GitHub App using
   Only select repositories, choosing only that repository. In its Settings >
   Collaborators, invite Dhruvsa1 once. The organizer must accept.
   The setup buttons on Results open the GitHub pages; finish each step there.
7. For each recording: choose Sign in to GitHub, enter the one-time code at
   github.com/login/device, and authorize Nose Calibration. Check the account shown.
   Review the sharing notice, check its consent box, then choose Encrypt and share.
   Use only the code shown by your collector, never a code someone sends you.
   Signing in alone does not upload a recording. Wait for a completion receipt.
   If organizer access is pending, wait for acceptance and share again to verify.

Microsoft Edge WebView2 Runtime is required; it is commonly already installed.
If the app reports it missing, obtain it from Microsoft's official WebView2 download page.
No Python, developer tools, GitHub CLI, or .NET installation is required.

This package is not code-signed. Windows may warn before opening it. If you are
unsure, stop and contact the organizer. Do not disable security software.

Optional: Install.ps1 copies the extracted app into your per-user Programs folder
and creates a Start menu shortcut. It does not need administrator access and adds
no startup entry. To use it, right-click Install.ps1 and choose Run with PowerShell;
the window shows the result and waits for Enter. It first checks every file
against package-files.json and stops, changing nothing, if a file is missing,
altered or extra. Each run installs into a new folder; earlier installs are kept.
You can run the app directly without this script. If Windows does not run the
script, skip it. Do not change PowerShell execution policy or disable security
software to install it.

Recording is limited to the focused practice interface. It includes pointer,
click, keyboard and scroll events, answers, and throttled page screenshots.
No recording occurs before you explicitly start. Closing the app stops recording.
Your local recordings are in %LOCALAPPDATA%/NoseCalibration/sessions.
Use Earlier recordings on the start screen to open a saved session and retry
sharing. Opening an earlier recording does not restart recording.
An exported ZIP contains readable private recording data: share it deliberately.

GitHub sharing writes encrypted recordings to your selected private inbox.
The app does not create repositories, install itself or invite anyone.
The GitHub App requires Contents read/write and Metadata read-only for that one
repository. Never choose All repositories. Other collaborators block sharing.
Personal GitHub repositories grant collaborators write access: the organizer can
decrypt submitted recordings and read, change or delete inbox files, including
future shared sessions, until you remove them. This is standing access.
Device sign-in does not use GitHub CLI or other saved GitHub logins.
The access token is kept only in app memory, for at most eight hours, and is not
saved. Sign out or closing the app clears it locally without revoking GitHub
authorization. Refresh tokens are discarded. To revoke, open GitHub Settings >
Applications > Authorized GitHub Apps and revoke Nose Calibration. Manage or
uninstall the repository installation under Installed GitHub Apps. Remove the
organizer separately in repository settings. These actions do not erase copies
already received. Numeric aggregate metrics may receive optional Codex advisory
review; raw code, key presses and screenshots are not automatically sent to a model.
Failed/interrupted sharing may leave encrypted files in your private repository.

See Nose-Calibration-Setup.pdf for the illustrated participant guide when included.
Development preview packages may omit the PDF and are not approved study releases.
Live GitHub upload and end-to-end participant validation remain untested.
