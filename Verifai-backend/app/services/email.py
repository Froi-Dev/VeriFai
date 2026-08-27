import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

from app.core.config import settings

logger = logging.getLogger(__name__)


def password_reset_delivery_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_address)


def send_password_reset_email(email: str, token: str) -> None:
    """Deliver a one-time reset token without ever writing it to application logs."""
    if not password_reset_delivery_is_configured():
        logger.error("Password reset email delivery is not configured")
        return

    query = urlencode({"token": token})
    reset_url = f"{settings.frontend_reset_url}?{query}"
    message = EmailMessage()
    message["Subject"] = "Reset your VeriFai password"
    message["From"] = settings.smtp_from_address
    message["To"] = email
    message.set_content(
        "A password reset was requested for your VeriFai account.\n\n"
        f"Open this link within {settings.password_reset_expire_minutes} minutes:\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls(context=context)
            if settings.smtp_username and settings.smtp_password:
                client.login(
                    settings.smtp_username, settings.smtp_password.get_secret_value()
                )
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Password reset email delivery failed")
