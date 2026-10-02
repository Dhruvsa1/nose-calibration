NOSE CALIBRATION — WINDOWS x64

1. Extract the entire ZIP into a folder you own.
2. Open NoseCalibration.exe. Keep all files together.
3. Read the recording notice, check consent, and choose Start session.
4. Work through the practice questions normally. Answer accuracy is optional for human calibration.
5. Choose Submit Test when finished, or Stop recording at any time.
6. To share: choose Sign in to GitHub, enter the one-time code at
   github.com/login/device, and authorize Nose Calibration. Check the account shown.
   Review the sharing notice, check its consent box, then choose Encrypt and share.
   Signing in alone does not upload a recording. Wait for a completion receipt.

Microsoft Edge WebView2 Runtime is required; it is commonly already installed.
If the app reports it missing, obtain it from Microsoft's official WebView2 download page.
No Python, developer tools, GitHub CLI, or .NET installation is required.

Optional: Install.ps1 copies the extracted app into your per-user Programs folder
and creates a Start menu shortcut. It does not need administrator access.
You can run the app directly without this script. Do not change machine-wide
PowerShell execution policy or disable security software to install it.

Recording is limited to the focused practice interface. It includes pointer,
click, keyboard and scroll events, answers, and throttled page screenshots.
No recording occurs before you explicitly start. Closing the app stops recording.
Your local recordings are in %LOCALAPPDATA%/NoseCalibration/sessions.
Use Earlier recordings on the start screen to open a saved session and retry
sharing. Opening an earlier recording does not restart recording.
An exported ZIP contains readable private recording data: share it deliberately.

GitHub sharing creates an encrypted recording in a dedicated private repository
in your GitHub account, then invites Dhruvsa1 as collaborator. Personal GitHub
repositories grant collaborators write access to that dedicated repository.
The organizer can decrypt submitted recordings. Nose Calibration has a dedicated
OAuth device sign-in; it does not use GitHub CLI or other saved GitHub logins.
The broad repo scope allows reading and writing repositories your account can
reach, including private ones, beyond this single submission repository.
The access token is kept only in app memory, for at most eight hours, and is not
saved. Sign out or closing the app clears it locally without revoking GitHub
authorization. To revoke, open GitHub Settings > Applications > Authorized OAuth
Apps and revoke Nose Calibration. Remove the collaborator in repository settings.
Failed/interrupted sharing may leave encrypted files in your private repository.

See Nose-Calibration-Setup.pdf for the illustrated participant guide when included.
Development preview packages may omit the PDF and are not approved study releases.
Live GitHub upload and end-to-end participant validation remain untested.
