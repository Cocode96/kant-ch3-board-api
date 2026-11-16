import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
import jwt

MAX_PASSWORD_LENGTH = 128
SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("JWT_SECRET은 새로 만든 32자 이상 값이어야 합니다.")

def hash_password(password):
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Password is too long")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + digest.hex()

def verify_password(password, saved):
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        salt, expected = saved.split(":")
        salt_bytes = bytes.fromhex(salt)
        if len(salt_bytes) != 16 or len(expected) != 128:
            return False
        bytes.fromhex(expected)
        digest = hashlib.scrypt(password.encode(), salt=salt_bytes, n=2**14, r=8, p=1)
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)

def create_token(user_id):
    return jwt.encode({"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=30)}, SECRET, algorithm="HS256")

def decode_user_id(token):
    payload = jwt.decode(token, SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    user_id = int(payload["sub"])
    if user_id <= 0:
        raise ValueError("Invalid subject")
    return user_id

