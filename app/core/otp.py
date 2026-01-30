import hashlib
import logging
import secrets
import httpx

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _format_phone(mobile_number: str) -> str:
    """Ensure phone number has 91 prefix for WhatsApp."""
    phone = mobile_number.strip().replace("+", "").replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone
    return phone


def send_otp(mobile_number: str, otp: str) -> bool:
    """Send OTP to user via WhatsApp using MessagingHub API."""
    phone = _format_phone(mobile_number)

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "testing",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": otp}
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": 0,
                    "parameters": [
                        {"type": "text", "text": otp}
                    ]
                }
            ]
        }
    }

    try:
        response = httpx.post(
            settings.WHATSAPP_API_URL,
            json=payload,
            headers={
                "X-API-KEY": settings.WHATSAPP_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        logger.info("WhatsApp OTP response [%s]: %s", response.status_code, response.text)

        if response.status_code in (200, 201):
            logger.info("OTP sent to %s via WhatsApp", phone)
            return True
        else:
            logger.warning("WhatsApp OTP failed [%s]: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.error("WhatsApp OTP error: %s", str(e))
        return False


def send_thank_you(mobile_number: str) -> bool:
    """Send thank you message after OTP verification via WhatsApp."""
    phone = _format_phone(mobile_number)

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "thank_you_7",
            "language": {"code": "en"},
        }
    }

    try:
        response = httpx.post(
            settings.WHATSAPP_API_URL,
            json=payload,
            headers={
                "X-API-KEY": settings.WHATSAPP_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        logger.info("WhatsApp thank_you response [%s]: %s", response.status_code, response.text)

        if response.status_code in (200, 201):
            logger.info("Thank you message sent to %s", phone)
            return True
        else:
            logger.warning("WhatsApp thank_you failed [%s]: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.error("WhatsApp thank_you error: %s", str(e))
        return False
