import hashlib
from datetime import timedelta
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jose import JWTError
from pydantic import EmailStr, NameEmail, SecretStr

from src.api.auth.auth import (
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_SIGNUP,
    create_token,
    decode_token,
)
from src.api.auth.schema import PendingSignup
from src.config import settings
from src.db.models.users import User

VALID_HOURS = 14
TOKEN_TTL = timedelta(hours=VALID_HOURS)

mail_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=SecretStr(settings.MAIL_PASSWORD),
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True,
    TEMPLATE_FOLDER=Path(__file__).parent / "email-templates" / "build",
)

fm = FastMail(mail_config)


async def send_confirmation_email(token: str, username: str, email: EmailStr) -> None:
    message = MessageSchema(
        subject=f"{settings.PROJECT_NAME} - email confirmation for user {username}",
        recipients=[NameEmail(name=username, email=email)],
        template_body={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "valid_hours": VALID_HOURS,
            "link": f"{settings.FRONTEND_URL}/confirm-email/{token}",
        },
        subtype=MessageType.html,
    )
    await fm.send_message(message, template_name="signup_confirmation.html")


async def send_reset_password_email(token: str, username: str, email: EmailStr) -> None:
    message = MessageSchema(
        subject=f"{settings.PROJECT_NAME} - password recovery for user {username}",
        recipients=[NameEmail(name=username, email=email)],
        template_body={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "valid_hours": VALID_HOURS,
            "link": f"{settings.FRONTEND_URL}/reset-password/{token}",
        },
        subtype=MessageType.html,
    )
    await fm.send_message(message, template_name="reset_password.html")


def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def generate_password_reset_token(user: User) -> str:
    return create_token(
        subject=str(user.id),
        token_type=TOKEN_TYPE_PASSWORD_RESET,
        expires_delta=TOKEN_TTL,
        extra={"fp": password_fingerprint(user.password_hash)},
    )


def read_password_reset_token(token: str) -> tuple[int, str]:
    try:
        payload = decode_token(token, TOKEN_TYPE_PASSWORD_RESET)
        return int(payload["sub"]), str(payload["fp"])
    except (JWTError, KeyError, ValueError):
        raise ValueError("Invalid or expired token") from None


def generate_signup_confirmation_token(pending: PendingSignup) -> str:
    return create_token(
        subject=pending.email,
        token_type=TOKEN_TYPE_SIGNUP,
        expires_delta=TOKEN_TTL,
        extra={
            "username": pending.username,
            "password_hash": pending.password_hash,
        },
    )


def read_signup_confirmation_token(token: str) -> PendingSignup:
    try:
        payload = decode_token(token, TOKEN_TYPE_SIGNUP)
        return PendingSignup(
            email=payload["sub"],
            username=payload["username"],
            password_hash=payload["password_hash"],
        )
    except (JWTError, KeyError, ValueError):
        raise ValueError("Invalid or expired token") from None