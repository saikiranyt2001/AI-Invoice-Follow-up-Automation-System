from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.support import get_active_company, issue_auth_tokens
from app.config import get_settings
from app.database import get_db
from app.models import Company, CompanyMembership, RefreshToken, RevokedAccessToken, User, UserRole
from app.schemas import LogoutRequest, MfaEnableRequest, MfaSetupOut, TokenOut, TokenRefreshRequest, UserCreate, UserLogin, UserOut
from app.security import (
    bearer_scheme,
    decode_access_token,
    generate_mfa_secret,
    get_current_user,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _default_company_name(user: User) -> str:
    return f"{user.username} Company"


@router.post("/signup", response_model=TokenOut)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where((User.email == payload.email) | (User.username == payload.username)))
    if existing:
        raise HTTPException(status_code=400, detail="User with this email or username already exists")
    admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)) or 0
    should_be_admin = admin_count == 0
    user = User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        role=UserRole.ADMIN if should_be_admin else UserRole.TEAM,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    default_company = Company(owner_user_id=user.id, name=_default_company_name(user))
    db.add(default_company)
    db.flush()
    db.add(CompanyMembership(company_id=default_company.id, user_id=user.id))
    user.active_company_id = default_company.id
    db.commit()
    db.refresh(user)
    return issue_auth_tokens(db, user, get_settings().auth_refresh_token_days)


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if bool(user.mfa_enabled):
        if not payload.otp_code or not user.mfa_secret or not verify_totp(user.mfa_secret, payload.otp_code):
            raise HTTPException(status_code=401, detail="MFA code required or invalid")
    return issue_auth_tokens(db, user, get_settings().auth_refresh_token_days)


@router.post("/refresh", response_model=TokenOut)
def refresh_access_token(payload: TokenRefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if not row or bool(row.revoked) or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    row.revoked = 1
    db.commit()
    return issue_auth_tokens(db, user, get_settings().auth_refresh_token_days)


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if credentials and credentials.scheme.lower() == "bearer":
        decoded = decode_access_token(credentials.credentials)
        jti = str(decoded.get("jti") or "")
        exp_raw = decoded.get("exp")
        if jti and exp_raw:
            expires_at = datetime.fromtimestamp(int(exp_raw), tz=timezone.utc).replace(tzinfo=None)
            existing = db.scalar(select(RevokedAccessToken).where(RevokedAccessToken.jti == jti))
            if not existing:
                db.add(RevokedAccessToken(jti=jti, expires_at=expires_at))
                db.commit()
    if payload.refresh_token:
        token_hash = hash_refresh_token(payload.refresh_token)
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if row and not bool(row.revoked):
            row.revoked = 1
            db.commit()
    return {"ok": True}


@router.post("/logout-all")
def logout_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tokens = db.scalars(select(RefreshToken).where(RefreshToken.user_id == current_user.id, RefreshToken.revoked == 0)).all()
    for row in tokens:
        row.revoked = 1
    db.commit()
    return {"ok": True, "revoked_refresh_tokens": len(tokens)}


@router.post("/mfa/setup", response_model=MfaSetupOut)
def setup_mfa(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    secret = generate_mfa_secret()
    current_user.mfa_secret = secret
    current_user.mfa_enabled = 0
    db.commit()
    db.refresh(current_user)
    uri = f"otpauth://totp/InvoiceAutomation:{current_user.email}?secret={secret}&issuer=InvoiceAutomation"
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable")
def enable_mfa(payload: MfaEnableRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is not initialized")
    if not verify_totp(current_user.mfa_secret, payload.otp_code):
        raise HTTPException(status_code=400, detail="Invalid OTP code")
    current_user.mfa_enabled = 1
    db.commit()
    return {"ok": True, "mfa_enabled": True}


@router.post("/mfa/disable")
def disable_mfa(payload: MfaEnableRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.mfa_secret or not bool(current_user.mfa_enabled):
        return {"ok": True, "mfa_enabled": False}
    if not verify_totp(current_user.mfa_secret, payload.otp_code):
        raise HTTPException(status_code=400, detail="Invalid OTP code")
    current_user.mfa_enabled = 0
    current_user.mfa_secret = None
    db.commit()
    return {"ok": True, "mfa_enabled": False}


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_active_company(db, current_user)
    return current_user
