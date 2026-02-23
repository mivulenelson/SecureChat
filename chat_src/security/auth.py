import random
import time

_OTP_STORE = {}  # phone -> (otp, exp)

def normalize_phone(phone: str) -> str:
    return (phone or "").strip().replace(" ", "")

def generate_otp(phone: str, ttl_seconds: int = 120) -> str:
    phone = normalize_phone(phone)
    otp = f"{random.randint(0, 999999):06d}"
    _OTP_STORE[phone] = (otp, time.time() + ttl_seconds)
    return otp

def verify_otp(phone: str, otp: str) -> bool:
    phone = normalize_phone(phone)
    item = _OTP_STORE.get(phone)
    if not item:
        return False
    real, exp = item
    if time.time() > exp:
        return False
    return otp.strip() == real