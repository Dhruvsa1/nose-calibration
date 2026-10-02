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
    c.drawRightString(W-44, 28, f'{n} / 4')

def screenshot(name, top, height):
    image = ImageReader(str(ROOT / 'docs/images' / name))
    iw, ih = image.getSize(); width = height*iw/ih
    c.drawImage(image, (W-width)/2, top-height, width, height)

page(1, 'Open it. Start when ready.', 'Windows 10/11, 64-bit. No coding setup is needed to run the collector.')
y = text('<b>Check the ZIP before opening.</b> In PowerShell, replace the quoted path below with your downloaded ZIP:<br/><font face="Courier" size="9">Get-FileHash -Algorithm SHA256 "C:/path/to/download.zip"</font><br/>Compare the Hash with the organizer\'s SHA-256 published through a <b>separate channel</b>, such as the study announcement. If it differs or no value is published, stop and contact the organizer. The accompanying .sha256 file and package manifests do not prove who built the download.', 650, small)
y = text('<b>1. Extract the entire ZIP.</b> Choose <b>Extract All</b> into a new, empty folder you own. Keep all files together.', y)
y = text('<b>2. Open NoseCalibration.exe.</b> No Python, .NET installation or developer tools are needed.', y)
y = text('<b>Optional Start shortcut:</b> right-click <b>Install.ps1</b> and choose <b>Run with PowerShell</b>. Keep the window open until it reports <b>Installed Nose Calibration</b> or <b>Nose Calibration was NOT installed</b>; read the result, then press Enter to close. It checks files against package-files.json before copying. No administrator access is needed. If the script will not run, skip it and run the EXE directly; do not change execution policy.', y, small)
y = text('<b>3. Read the notice and start.</b> Check consent, then choose <b>Start session</b>. Recording stays off until then.', y)
screenshot('overview.png', y-2, 260)
text('Choose <b>Solve</b> to open a question. The top bar includes <b>Stop recording</b>.<br/><b>Unsigned preview:</b> if Windows warns or you are unsure, stop and contact the organizer. Do not disable security software.', y-277, small)
c.showPage()

page(2, 'Take the practice test.', 'Work naturally. For human calibration, your interaction patterns matter more than your score.')
y = text('<b>4. Answer the questions.</b> There are multiple-choice, fill-in-the-blank and dropdown questions, plus two JavaScript coding tasks. Read, scroll, type and correct your answers as you normally would.', 642)
y = text('<b>5. Try your code.</b> Use <b>Run Code</b> to see results. <b>Save &amp; Proceed</b> moves on; switching questions retains answers. You can leave a question unanswered.', y)
screenshot('editor.png', 492, 291)
y = text('<b>6. Finish or stop.</b> Choose <b>Submit Test</b> to grade answers and stop recording. You can instead choose <b>Stop recording</b> at any time. Closing the app also stops it. Results are saved locally.', 178)
text('<b>What is recorded?</b> Only interactions in the focused practice interface: mouse movement/clicks, keyboard events, scrolling, selections, final answers and click-triggered page screenshots. Screenshots are throttled and capped. Do not type passwords or personal information into the practice answers.', y, small)
c.showPage()

def setup_detail(top, source_top, source_bottom):
    # Clip the approved synthetic screenshot inside the PDF, without altering it.
    image = ImageReader(str(ROOT / 'docs/images/github-setup.png'))
    iw, ih = image.getSize(); scale = (W-88)/iw
    height = (source_bottom-source_top)*scale
    c.saveState()
    clip = c.beginPath(); clip.rect(44, top-height, W-88, height)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(image, 44, top-(ih-source_top)*scale, W-88, ih*scale)
    c.restoreState()

page(3, 'Set up sharing once.', 'Optional GitHub sharing uses one private repository. Finish these steps on GitHub.')
y = text('On Results, the three setup buttons open GitHub pages. They do not create a repository, install the app or invite anyone for you.', 642)
y = text('<b>1. Create repository.</b> In your personal account, create <b>nose-calibration-submissions</b> and choose <b>Private</b>. Reuse it for later recordings.', y)
y = text('<b>2. Install app.</b> Install <b>Nose Calibration</b>. Choose <b>Only select repositories</b> and select only <b>nose-calibration-submissions</b>. Never choose All repositories. Check for <b>Contents: read and write</b> and <b>Metadata: read-only</b>.', y)
y = text('<b>3. Open my repositories.</b> Open that repository, then <b>Settings &gt; Collaborators &gt; Add people</b>. Invite <b>Dhruvsa1</b> once; the organizer must accept. Add no other collaborators: they block sharing.', y)
setup_detail(y-4, 356, 708)
y -= 232
text('<b>Standing access:</b> the organizer can decrypt shared recordings and keeps write access to this inbox, including future shared sessions, until you remove them. They can read, change or delete repository files. This narrows access; it does not make sharing risk-free.', y, small)
c.showPage()

page(4, 'Each recording: two steps.', 'Already set up GitHub? Sign in if needed, then consent and share.')
y = text('<b>1. Sign in to GitHub.</b> Enter only the code shown by this collector at <b>github.com/login/device</b>, authorize Nose Calibration and check the displayed account. Never enter a code someone sends you. Signing in alone uploads nothing.', 642)
y = text('<b>2. Consent, then Encrypt and share.</b> Read the notice and wait for the result. Numeric metrics may receive Codex advisory review; raw code, key presses and screenshots are not automatically sent to a model.', y)
setup_detail(y-3, 720, 1170)
y -= 285
y = text('<b>Stored is not yet a receipt.</b> Encrypted data may be uploaded while organizer access is unconfirmed. The app cannot see pending invitations. Wait for acceptance, then share again to verify. A final receipt requires verified organizer access.', y, small)
y = text('<b>Sign out or revoke.</b> The token stays in memory for at most eight hours; refresh tokens are discarded. Sign out or closing clears it locally, but does not revoke the grant. Use GitHub <b>Settings &gt; Applications &gt; Authorized GitHub Apps</b> to revoke Nose Calibration; use <b>Installed GitHub Apps</b> to manage its repository access. Remove Dhruvsa1 separately in repository settings. These actions do not erase copies already received.', y, small)
y = text('<b>Return later.</b> Skip sharing to keep the recording local. <b>Earlier recordings</b> opens a saved session for retry without restarting capture. <b>Export session file</b> creates a readable ZIP: share it deliberately.', y, small)
text('<b>Development preview:</b> selected-repository live authorization/upload and clean-machine installation remain unverified. If setup fails, contact the organizer; never post codes, tokens or recordings publicly. This preview is unsigned: verify unexpected Windows warnings with the organizer.', y, small)
c.save()
print(OUT)
