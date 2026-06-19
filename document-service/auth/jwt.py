from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os

bearer = HTTPBearer()
ALGORITHM = "RS256"


def _load_public_key() -> str:
    env_key = os.getenv("JWT_PUBLIC_KEY")
    if env_key:
        return env_key.replace("\\n", "\n")
    key_path = os.getenv("JWT_PUBLIC_KEY_PATH", "keys/public.pem")
    with open(key_path, "r") as f:
        return f.read()


PUBLIC_KEY = _load_public_key()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = jwt.decode(credentials.credentials, PUBLIC_KEY, algorithms=[ALGORITHM])
        return {
            "user_id": payload["user_id"],
            "role": payload["role"],
            "token": credentials.credentials,
        }
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid token",
                    "details": "Token validation failed",
                }
            },
        )
