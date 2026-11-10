import logging

import resend

from app.core.config import EMAIL_FROM, RESEND_API_KEY

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY


def send_email(
    recipient: str,
    subject: str,
    html_content: str,
) -> bool:
    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [recipient],
            "subject": subject,
            "html": html_content,
        })
    except Exception:
        logger.exception("Falha ao enviar e-mail via Resend")
        return False

    return True