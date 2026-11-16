import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
import jwt

SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("JWT_SECRET은 새로 만든 32자 이상 값이어야 합니다.")

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + digest.hex()

def verify_password(password, saved):
    salt, expected = saved.split(":")
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), expected)

def create_token(user_id):
    return jwt.encode({"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=30)}, SECRET, algorithm="HS256")

def decode_user_id(token):
    payload = jwt.decode(token, SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    user_id = int(payload["sub"])
    if user_id <= 0:
        raise ValueError("Invalid subject")
    return user_id

