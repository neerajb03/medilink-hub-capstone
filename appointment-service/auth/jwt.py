from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os

from aws_utils import get_jwt_secret
SECRET = get_jwt_secret()
ALGORITHM = "HS256"
bearer = HTTPBearer()


def create_token(user_id: str, role: str) -> str:
    return jwt.encode({"user_id": user_id, "role": role}, SECRET, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=[ALGORITHM])
        return {"user_id": payload["user_id"], "role": payload["role"]}
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
