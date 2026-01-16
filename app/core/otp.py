import hashlib
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_otp() -> str:
    return str(random.randint(100000, 999999))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def send_otp(mobile_number: str, otp: str) -> bool:
    """
    Send OTP to user's mobile number via SMS/WhatsApp.

    TODO: Implement this with your SMS/WhatsApp provider:
    - Twilio for SMS
    - WhatsApp Business API
    - Any other SMS gateway

    For now, this is a placeholder that logs the OTP.
    """
    logger.info("Sending OTP to %s: %s", mobile_number, otp)
    logger.info("Message: Your OTP is %s. Valid for 5 minutes.", otp)

    # TODO: Replace with actual SMS/WhatsApp API call
    # Example with Twilio:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # message = client.messages.create(
    #     body=f"Your OTP is {otp}. Valid for 5 minutes.",
    #     from_='+1234567890',
    #     to=mobile_number
    # )

    return True
