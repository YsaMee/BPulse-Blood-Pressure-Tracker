# email_sender.py — Resend Email Delivery
import os
import re
import base64
from html import escape
from dotenv import load_dotenv
from export_utils import safe_filename, is_valid_email

load_dotenv()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
DEFAULT_FROM = "BPulse <onboarding@resend.dev>"
EMAIL_FROM = os.environ.get("EMAIL_FROM", DEFAULT_FROM)


def send_pdf_email(to_email, person_name, pdf_buffer, summary_text=""):
    if not RESEND_API_KEY:
        return False, "Email service not configured (missing RESEND_API_KEY in .env)."

    to_email = (to_email or "").strip()
    if not is_valid_email(to_email):
        return False, "Please provide a valid email address."

    try:
        import resend
        resend.api_key = RESEND_API_KEY
    except ImportError:
        return False, "The 'resend' Python library is not installed."

    pdf_buffer.seek(0)
    pdf_bytes = pdf_buffer.read()
    if not pdf_bytes:
        return False, "The report PDF was empty."

    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    display_name = re.sub(r"[\r\n]+", " ", person_name or "Patient").strip()
    html_name = escape(display_name)
    summary_html = f'<p style="color:#40474f;">{escape(summary_text)}</p>' if summary_text else ""

    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;">
      <h2 style="color:#00507d;">BPulse — Blood Pressure Report</h2>
      <p>The blood pressure report for <strong>{html_name}</strong> is attached as a PDF.</p>
      {summary_html}
      <p style="font-size:12px;color:#707881;">
        Informational only — does not replace medical advice.
      </p>
    </div>
    """

    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": f"BPulse Report — {display_name}",
            "html": html,
            "attachments": [{
                "filename": f"BPulse_{safe_filename(display_name)}.pdf",
                "content": encoded,
            }],
        })
        return True, f"Report sent to {to_email}."
    except Exception as e:
        return False, f"Email delivery failed: {e}"
