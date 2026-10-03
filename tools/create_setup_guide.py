"""Build the participant guide from verified synthetic application screenshots."""
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'Nose-Calibration-Setup.pdf'
# Synthetic Results screen (mock bridge, no real code or recording); cropped inside the PDF only.
SHARE_SHOT = ROOT / 'docs' / 'images' / 'invitation-sharing.png'
W, H = 612, 792
PAGES = 4
c = canvas.Canvas(str(OUT), pagesize=(W, H))
c.setTitle('Nose Calibration - Participant setup guide')
c.setAuthor('Nose Calibration')
body = ParagraphStyle('body', fontName='Helvetica', fontSize=11, leading=16, textColor=HexColor('#23312d'))
small = ParagraphStyle('small', parent=body, fontSize=9.5, leading=13.5)
head = ParagraphStyle('head', parent=body, fontName='Helvetica-Bold', fontSize=12.5, leading=16, textColor=HexColor('#13251c'))

def text(value, y, style=body, indent=0):
    p = Paragraph(value, style)
    _, height = p.wrap(W-88-indent, H)
    p.drawOn(c, 44+indent, y-height)
    return y-height-11

def callout(value, y, fill='#fdf3df', edge='#c98a1b'):
    p = Paragraph(value, small)
    _, height = p.wrap(W-88-24, H)
    c.setFillColor(HexColor(fill)); c.rect(44, y-height-16, W-88, height+16, fill=1, stroke=0)
    c.setFillColor(HexColor(edge)); c.rect(44, y-height-16, 4, height+16, fill=1, stroke=0)
    p.drawOn(c, 60, y-height-8)
    return y-height-28

def page(n, title, subtitle):
    c.setFillColor(HexColor('#087f49')); c.rect(0, H-12, W, 12, fill=1, stroke=0)
    c.setFillColor(HexColor('#52665d')); c.setFont('Helvetica-Bold', 10)
    c.drawString(44, H-43, 'NOSE CALIBRATION / PARTICIPANT GUIDE')
    logo = Image.open(ROOT / 'web/branding/wordmark-light.png')
    logo = logo.crop(logo.getbbox())
    lh = 18; lw = lh*logo.width/logo.height
    c.drawImage(ImageReader(logo), W-44-lw, H-48, lw, lh, mask='auto')
    c.setFillColor(HexColor('#13251c')); c.setFont('Helvetica-Bold', 25)
    c.drawString(44, H-79, title)
    c.setFont('Helvetica', 9); c.setFillColor(HexColor('#52665d'))
    c.drawString(44, 28, 'Development preview - not an approved study release')
    c.drawRightString(W-44, 28, f'{n} / {PAGES}')
    return text(subtitle, H-97)

def done(y):
    # Fail the build rather than let text run into the footer.
    assert y > 44, f'page content overflows the footer (y={y:.0f})'
    c.showPage()

def screenshot(name, top, height):
    image = ImageReader(str(ROOT / 'docs/images' / name))
    iw, ih = image.getSize(); width = height*iw/ih
    c.drawImage(image, (W-width)/2, top-height, width, height)
    return top-height

def detail(path, top, box, width=W-88):
    # Draw one region (left, top, right, bottom, in source pixels) of a screenshot, scaled to width.
    left, src_top, right, src_bottom = box
    region = Image.open(path).convert('RGB').crop(box)
    height = width*region.height/region.width
    x = (W-width)/2
    c.drawImage(ImageReader(region), x, top-height, width, height)
    c.setStrokeColor(HexColor('#b9c6bf')); c.setLineWidth(0.6); c.rect(x, top-height, width, height, fill=0, stroke=1)
    return top-height

# Page 1: get, check, install and open.
y = page(1, 'Get it. Check it. Install it.', 'Windows 10/11, 64-bit. No administrator access, PowerShell, coding tools or GitHub account needed.')
y = callout('<b>Development preview.</b> There is no public download or approved release yet. Use only a preview setup file the study organizer gave you directly. If a download, check or step is unavailable or fails, stop and contact the organizer.', y-2)
y = text('<b>1. Get the setup file</b> from the organizer, for example <b>NoseCalibration-Setup-0.1.0-preview-win-x64.exe</b>. No ZIP extraction is needed.', y)
y = text('<b>2. Check it before running it.</b> Its SHA-256 must match the value the organizer published through a <b>separate channel</b>, such as the study announcement. If it differs or you cannot check it, do not run it; contact the organizer.', y)
y = text('Any SHA-256 tool works; PowerShell\'s <font face="Courier">Get-FileHash</font> is one built-in option. A .sha256 file next to the download only detects damage, not who built it.', y+4, small, 18)
y = text('<b>3. Install.</b> Double-click the setup file and follow the wizard to <b>Finish</b>. It installs for your Windows account only. If Setup says Nose Calibration is running, close the app first. Setup does not open the app or start recording.', y)
y = callout('<b>Unsigned preview.</b> Windows may show a security warning. If you are unsure, stop and contact the organizer. Never disable security software or change security settings to get past a warning.', y, '#fbe9e6', '#b8432f')
y = text('<b>4. Open Nose Calibration from the Start menu.</b> Read the notice, check consent, then choose <b>Start session</b>. Recording stays off until then.', y)
y = screenshot('overview.png', y-2, 215)
done(text('Choose <b>Solve</b> to open a question. The top bar always shows <b>Stop recording</b>.', y-8, small))

# Page 2: practice and recording scope.
y = page(2, 'Take the practice test.', 'Work naturally. For human calibration, your interaction patterns matter more than your score.')
y = text('<b>5. Answer the questions.</b> There are multiple-choice, fill-in-the-blank and dropdown questions, plus two JavaScript coding tasks. Read, scroll, type and correct your answers as you normally would.', y-6)
y = text('<b>6. Try your code.</b> Use <b>Run Code</b> to see results. <b>Save &amp; Proceed</b> moves on; switching questions keeps answers. You can leave a question unanswered.', y)
y = screenshot('editor.png', y-2, 320)
y = text('<b>7. Finish or stop.</b> Choose <b>Submit Test</b> to grade answers and stop recording, or <b>Stop recording</b> at any time. Closing the app also stops it.', y-10)
y = text('<b>What is recorded?</b> Only the focused practice interface: pointer movement and clicks, key presses, scrolling, selections, your answers and throttled screenshots taken on clicks. Nothing before Start or after Stop. Do not type passwords or personal information into answers.', y, small)
done(text('<b>Local by default.</b> Recordings stay on this computer unless you share them. <b>Earlier recordings</b> on the start screen reopens a saved session without restarting recording. <b>Export session file</b> creates a readable private ZIP: share it deliberately. Uninstalling the app from <b>Settings &gt; Apps</b> removes the program, not your recordings.', y, small))

# Page 3: invitation sharing.
y = page(3, 'Share with an invitation code.', 'Optional, for each finished recording. No GitHub account is needed.')
y = callout('<b>Not enabled yet.</b> Live invitation upload is not yet enabled or verified. These steps describe the flow once the organizer enables it; the organizer will tell you if and when to use it. Use only a code the organizer gave you. If Connect or sharing is unavailable or fails, contact the organizer.', y-2)
y = text('<b>1. Connect.</b> On Results, paste your code and choose <b>Connect</b>. Keep it private. A code works for at most 7 days and up to 3 recordings. The connection stays in app memory only; <b>Disconnect</b> or closing the app clears it. <b>Connecting uploads nothing and is not consent.</b>', y)
y = detail(SHARE_SHOT, y+2, (241, 703, 1193, 905))
y = text('<b>2. Consent, then Encrypt and share.</b> Read the notice, check the separate consent box and choose <b>Encrypt and share</b>. The recording is encrypted on this computer with the organizer\'s public key; the organizer decrypts it on their own computer.', y-10)
y = detail(SHARE_SHOT, y+2, (241, 913, 1193, 1128))
y = text('<b>Stored</b> means the study service holds an encrypted copy. <b>Received by organizer</b> means the organizer downloaded it: it confirms delivery only, not that the recording was checked or validated.', y-10, small)
y = text('<b>If sharing fails,</b> an encrypted copy may still have reached the service; do not treat it as received. Contact the organizer and retry the same recording from <b>Earlier recordings</b> only when they advise.', y, small)
done(text('Only completed human recordings can be shared; stopped, timed-out, test and Codex runs cannot, and the app makes the final check. Numeric aggregate metrics may receive optional Codex advisory review. Raw code, key presses and screenshots are not automatically sent to an AI model. No setup can guarantee zero risk or anonymity.', y, small))

# Page 4: optional legacy GitHub route.
y = page(4, 'Appendix: earlier GitHub sharing.', 'Optional. Use only for earlier recordings, or if the organizer asks you to use GitHub.')
y = text('Invitation sharing does not need GitHub. If asked to use GitHub, open <b>Earlier GitHub sharing</b> under Results. Its buttons open GitHub pages; the app creates, installs and invites nothing itself.', y-6, small)
y = text('Set up once', y, head)
y = text('<b>1.</b> In your personal account, create <b>nose-calibration-submissions</b> and choose <b>Private</b>.', y, small, 10)
y = text('<b>2.</b> Install the <b>Nose Calibration</b> GitHub App. Choose <b>Only select repositories</b> and select only that repository; never All repositories. It requests <b>Contents: read and write</b> and <b>Metadata: read-only</b>.', y, small, 10)
y = text('<b>3.</b> In that repository, open <b>Settings &gt; Collaborators</b> and invite <b>Dhruvsa1</b> once; the organizer must accept. Add no other collaborators: they block sharing.', y, small, 10)
y = text('Each recording', y-4, head)
y = text('<b>Sign in to GitHub</b> and enter only the code your collector shows at <b>github.com/login/device</b>; never a code someone sends you. Check the account shown. Signing in uploads nothing. Then check the separate consent box and choose <b>Encrypt and share</b>.', y, small, 10)
y = text('<b>Stored is not a final receipt</b> while organizer access is pending. Wait for the organizer to accept, then share again to verify.', y, small, 10)
y = text('Access and sign-out', y-4, head)
y = text('The organizer keeps <b>standing write access</b> to that repository: they can decrypt shared recordings and read, change or delete its files, including future shares, until you remove them.', y, small, 10)
y = text('The sign-in token stays in app memory for at most eight hours and is never saved. <b>Sign out</b> or closing the app clears it locally but does not revoke it: revoke under GitHub <b>Settings &gt; Applications &gt; Authorized GitHub Apps</b>, and manage repository access under <b>Installed GitHub Apps</b>. Remove Dhruvsa1 separately. None of this erases copies already received.', y, small, 10)
y = text('Need help?', y-4, head)
done(text('Contact the organizer if any step is unavailable or fails. Never post invitation codes, sign-in codes or recordings publicly. Live invitation upload, live GitHub upload and clean-machine installation are not yet verified in this preview.', y, small, 10))
c.save()
print(OUT)
