"""
api/auth.py — JWT authentication: login, logout, token verification.

Uses bcrypt for password hashing and python-jose for JWT tokens.
"""

from datetime import datetime, timedelta
from typing import Optional
import time

from fastapi import APIRouter, HTTPException, Response, Cookie, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import (
    DASHBOARD_USERNAME,
    DASHBOARD_PASSWORD,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    MAX_FAILED_LOGINS,
    LOGIN_LOCKOUT_SECS,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Simple in-memory brute-force protection ──────────────────────────────────
_failed_attempts: dict[str, list] = {}  # ip -> list of timestamps

# ─── Models ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def create_token(data: dict, expires_in_hours: int = JWT_EXPIRE_HOURS) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=expires_in_hours)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None

def is_locked_out(ip: str) -> bool:
    now = time.time()
    attempts = _failed_attempts.get(ip, [])
    # Remove attempts older than lockout window
    recent = [t for t in attempts if now - t < LOGIN_LOCKOUT_SECS]
    _failed_attempts[ip] = recent
    return len(recent) >= MAX_FAILED_LOGINS

def record_failed(ip: str):
    _failed_attempts.setdefault(ip, []).append(time.time())

def clear_failed(ip: str):
    _failed_attempts.pop(ip, None)

# ─── Routes ───────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"

    if is_locked_out(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {LOGIN_LOCKOUT_SECS // 60} minutes."
        )

    # Validate credentials
    valid_user = body.username == DASHBOARD_USERNAME
    valid_pass = body.password == DASHBOARD_PASSWORD  # plain-text compare (see note)
    # NOTE: For production, store a bcrypt hash of the password and compare:
    #   valid_pass = pwd_context.verify(body.password, HASHED_PASSWORD)

    if not (valid_user and valid_pass):
        record_failed(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_failed(ip)
    token = create_token({"sub": body.username})

    # Set cookie for browser navigation + return token for API calls
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
    )
    return TokenResponse(access_token=token)

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}

@router.get("/me")
async def me(access_token: Optional[str] = Cookie(default=None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    return {"username": payload.get("sub"), "authenticated": True}

# ─── Dependency for protected routes ──────────────────────────────────────────
async def require_auth(
    request: Request,
    access_token: Optional[str] = Cookie(default=None)
) -> dict:
    """FastAPI dependency — use in protected endpoints."""
    # Also accept Bearer token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.split(" ", 1)[1]

    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    return payload
