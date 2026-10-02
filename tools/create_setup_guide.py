"""Build the participant guide from verified application screenshots."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'Nose-Calibration-Setup.pdf'
W, H = 612, 792
c = canvas.Canvas(str(OUT), pagesize=(W, H))
c.setTitle('Nose Calibration - Participant setup guide')
c.setAuthor('Nose Calibration')
body = ParagraphStyle('body', fontName='Helvetica', fontSize=11, leading=16, textColor=HexColor('#23312d'))
small = ParagraphStyle('small', parent=body, fontSize=9, leading=13)

def text(value, y, style=body):
    p = Paragraph(value, style)
    _, height = p.wrap(W-88, H)
    p.drawOn(c, 44, y-height)
    return y-height-13

def page(n, title, subtitle):
    c.setFillColor(HexColor('#087f49')); c.rect(0, H-12, W, 12, fill=1, stroke=0)
    c.setFillColor(HexColor('#52665d')); c.setFont('Helvetica-Bold', 10)
    c.drawString(44, H-43, 'NOSE CALIBRATION / PARTICIPANT GUIDE')
    c.setFillColor(HexColor('#13251c')); c.setFont('Helvetica-Bold', 25)
    c.drawString(44, H-79, title)
    text(subtitle, H-97)
    c.setFont('Helvetica', 9); c.setFillColor(HexColor('#52665d'))
    c.drawString(44, 28, 'Development preview - October 2026')
    c.drawRightString(W-44, 28, f'{n} / 3')

def screenshot(name, top, height):
    image = ImageReader(str(ROOT / 'docs/images' / name))
    iw, ih = image.getSize(); width = height*iw/ih
    c.drawImage(image, (W-width)/2, top-height, width, height)

page(1, 'Open it. Start when ready.', 'Windows 10/11, 64-bit. No coding setup is needed to run the collector.')
y = text('<b>1. Extract the download.</b> Right-click the ZIP and choose <b>Extract All</b>. Open the extracted NoseCalibration folder. Keep its files together.', 642)
y = text('<b>2. Open NoseCalibration.exe.</b> You do not need Python, .NET, or developer tools. The optional Install.ps1 creates a Start menu shortcut; running the EXE directly is enough.', y)
y = text('<b>3. Read the notice and start.</b> Check the consent box, then choose <b>Start session</b>. Recording is off until you do this. Maximize the window for more room.', y)
screenshot('overview.png', 426, 287)
text('The question overview. Choose <b>Solve</b> to open a question. The top bar shows when recording is active and includes <b>Stop recording</b>.', 121, small)
c.showPage()

page(2, 'Take the practice test.', 'Work naturally. For human calibration, your interaction patterns matter more than your score.')
y = text('<b>4. Answer the questions.</b> There are multiple-choice, fill-in-the-blank and dropdown questions, plus two JavaScript coding tasks. Read, scroll, type and correct your answers as you normally would.', 642)
y = text('<b>5. Try your code.</b> Use <b>Run Code</b> to see results. <b>Save &amp; Proceed</b> moves on; switching questions retains answers. You can leave a question unanswered.', y)
screenshot('editor.png', 492, 291)
y = text('<b>6. Finish or stop.</b> Choose <b>Submit Test</b> to grade answers and stop recording. You can instead choose <b>Stop recording</b> at any time. Closing the app also stops it. Results are saved locally.', 178)
text('<b>What is recorded?</b> Only interactions in the focused practice interface: mouse movement/clicks, keyboard events, scrolling, selections, final answers and click-triggered page screenshots. Screenshots are throttled and capped. Do not type passwords or personal information into the practice answers.', y, small)
c.showPage()

page(3, 'Share only when you choose.', 'GitHub sign-in is required for optional encrypted sharing. You remain in control of the submission repository.')
y = text('<b>7. Sign in.</b> On Results, choose <b>Sign in to GitHub</b>. Enter the app\'s one-time code at <b>github.com/login/device</b> and authorize <b>Nose Calibration</b>. Check the displayed account. This dedicated sign-in does not use GitHub CLI or other saved GitHub logins. Signing in alone uploads nothing.', 642, small)
y = text('<b>8. Review, consent, share.</b> Read the sharing notice, check its consent box, then choose <b>Encrypt and share</b>. Keep the app open until a <b>Submitted successfully</b> receipt appears. An interrupted upload may leave encrypted files in your private repository.', y, small)
y = text('<b>What GitHub access means</b><br/>The OAuth app requests broad <b>repo</b> permission: read and write access to repositories your account can reach, including private ones. It creates a dedicated private repository containing the encrypted recording and invites <b>Dhruvsa1</b> with <b>write access</b> to that repository. The organizer can decrypt your recording. You can remove the collaborator in repository settings.', y, small)
y = text('<b>Sign out and revoke access</b><br/>The token stays in app memory for at most eight hours and is not saved. <b>Sign out</b> or closing the app clears it locally; this does not revoke GitHub authorization. To revoke access, go to GitHub <b>Settings &gt; Applications &gt; Authorized OAuth Apps</b> and revoke <b>Nose Calibration</b>.', y, small)
y = text('<b>Keep it local, or return later</b><br/>Skip sharing to keep your recording here. <b>Export session file</b> saves readable recording data in a ZIP; share it only deliberately. Use <b>Earlier recordings</b> on the start screen to open a saved session and retry sharing. It does not restart recording. Sessions are stored in:<br/><font face="Courier" size="9">%LOCALAPPDATA%/NoseCalibration/sessions</font>', y, small)
y = text('<b>If something does not work</b><br/>Missing WebView2: install Microsoft Edge WebView2 Runtime from Microsoft\'s official page:<br/><link href="https://developer.microsoft.com/microsoft-edge/webview2/">developer.microsoft.com/microsoft-edge/webview2/</link><br/>Sign-in or upload fails: your session remains local. Keep the error message and contact the organizer. Never post recordings, tokens or authorization codes in public issues.<br/>This preview is unsigned. If Windows warns, verify the download with the organizer; do not disable security software.', y, small)
text('<b>Development preview:</b> local practice recording has been tested. Live GitHub upload and end-to-end participant validation remain untested; this guide is not release approval.', y, small)
c.save()
print(OUT)
