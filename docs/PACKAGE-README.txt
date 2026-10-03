NOSE CALIBRATION — WINDOWS x64 — DEVELOPMENT PREVIEW

There is no public download and no approved release yet. Use only a preview
setup file the study organizer gave you directly. Invitation sharing is not yet
enabled or verified; these steps describe how it will work once the organizer
enables it. If anything fails or is unavailable, stop and contact the organizer.

GET AND CHECK THE SETUP FILE
1. Use only the Windows setup file the organizer gave you directly, for example
   NoseCalibration-Setup-0.1.0-preview-win-x64.exe.
2. Before running it, make sure its SHA-256 matches the value the organizer
   published separately (for example in the study announcement, not the
   download page). Any SHA-256 tool works; one built-in option is PowerShell's
   Get-FileHash. If they differ, or you cannot check, do not run it; contact
   the organizer. A .sha256 file next to the setup file only detects damage:
   anyone who changed the download could change it too.

INSTALL AND OPEN
No administrator access, ZIP extraction, PowerShell, Python, .NET, developer
tools or GitHub needed.
3. Double-click the setup file and follow the wizard. It installs for your
   Windows account only and adds a Start menu entry. If Setup says Nose
   Calibration is running, close the app first. Choose Finish; Setup does not
   open the app or start recording.
   Most computers already have Microsoft Edge WebView2 Runtime, which the app
   needs. If yours does not, Setup asks before installing it from Microsoft;
   this needs an internet connection but no administrator access. Cancel is
   unavailable while Microsoft's installer runs; after 10 minutes you can
   keep waiting or stop. If that step fails or you decline, Setup stops
   without installing Nose Calibration; follow its message (for example,
   restart Windows) and run the setup file again.
4. Open Nose Calibration from the Start menu.

PRACTICE
5. Read the recording notice, check consent, and choose Start session.
6. Work through the practice questions normally. Accuracy is optional.
7. Choose Submit Test when finished, or Stop recording at any time.
   Closing the app also stops recording.

SHARE WITH AN INVITATION CODE (optional, once the organizer enables it)
8. On Results, paste the invitation code the organizer gave you and choose
   Connect. Keep the code private. A code works for at most 7 days and up to
   3 recordings. The connection is kept in app memory only; Disconnect or
   closing the app clears it. Connecting uploads nothing and is not consent.
9. Read the sharing notice, check its separate consent box, then choose
   Encrypt and share. The recording is encrypted on this computer with the
   organizer's public key; the organizer decrypts it on their own computer.
   Only completed human recordings can be shared. Stopped, timed-out, test
   and Codex runs cannot; the app makes the final check.
   - Stored: the study service holds an encrypted copy.
   - Received by organizer: the organizer downloaded it. This confirms
     delivery only; it does not mean the recording was checked or validated.
   If sharing fails, it may still have left an encrypted copy on the service.
   Do not treat it as received. Contact the organizer, and retry the same
   recording from Earlier recordings only when they advise.

WHAT IS RECORDED
Only the focused practice interface: pointer, click, keyboard and scroll
events, answers, and throttled screenshots taken on clicks. Nothing is recorded
before you start or after you stop. Recordings stay on this computer unless you
share them, in %LOCALAPPDATA%/NoseCalibration/sessions. Earlier recordings on
the start screen reopens a saved session without restarting recording. An
exported ZIP contains readable private recording data: share it deliberately.
Numeric aggregate metrics may receive optional Codex advisory review; raw code,
key presses and screenshots are not automatically sent to an AI model.
No setup can guarantee zero risk or anonymity.

WINDOWS NOTES
Microsoft Edge WebView2 Runtime is required. The setup file includes
Microsoft's signed WebView2 installer and runs it only when the runtime is
missing; uninstalling Nose Calibration never removes the runtime. If the app
still reports it missing, run the setup file again or contact the organizer.
With the ZIP package, get it from Microsoft's official WebView2 page.
The setup file and app are not code-signed. Windows may show a security
warning. If you are unsure, stop and contact the organizer. Do not disable
security software or change security settings to get past a warning.
To remove the app, use Windows Settings > Apps > Installed apps. Uninstalling
removes the program, not your recordings. Close the app before installing a
newer preview or uninstalling.

APPENDIX: EARLIER GITHUB SHARING (only if the organizer asks)
GitHub is not needed for invitation sharing. Use this route only for earlier
recordings or when the organizer specifically asks. Under Results, open
Earlier GitHub sharing.
- Once: create a private personal repository named exactly
  nose-calibration-submissions. Install the Nose Calibration GitHub App with
  Only select repositories, choosing only that repository (never All
  repositories); it requests Contents read/write and Metadata read-only. In
  the repository's Settings > Collaborators, invite Dhruvsa1 once; the
  organizer must accept. Other collaborators block sharing. The app creates,
  installs and invites nothing itself.
- Each recording: choose Sign in to GitHub, enter only the code your collector
  shows at github.com/login/device, and check the account shown. Signing in
  uploads nothing. Check the separate consent box, then Encrypt and share.
  Stored is not a final receipt while organizer access is pending: wait for
  acceptance, then share again to verify.
- Access: the organizer keeps standing write access to that repository and
  can read, change or delete its files, including future shares, until you
  remove them. The token stays in app memory for at most eight hours and is
  not saved. Sign out or closing clears it locally but does not revoke
  GitHub authorization: revoke under GitHub Settings > Applications >
  Authorized GitHub Apps. None of these erase copies already received.

APPENDIX: ZIP PACKAGE (only if the organizer gives you a ZIP instead)
Check the ZIP's SHA-256 against the organizer's separate value as above.
Extract the entire ZIP into a new, empty folder you own and open
NoseCalibration.exe there. This route adds no Start menu entry.

See Nose-Calibration-Setup.pdf for the illustrated guide when included.
Development preview packages may omit the PDF and are not approved releases.
Live invitation upload, live GitHub upload, clean-machine installation and
Setup's automatic WebView2 installation remain unverified.
