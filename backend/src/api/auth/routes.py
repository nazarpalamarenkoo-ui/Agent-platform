import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import EmailStr

from src.api.auth.auth import create_access_token
from src.api.auth.mail import (
    generate_password_reset_token,
    generate_signup_confirmation_token,
    password_fingerprint,
    read_password_reset_token,
    read_signup_confirmation_token,
    send_confirmation_email,
    send_reset_password_email,
)
from src.api.auth.schema import (
    PendingSignup,
    ResetPasswordArgs,
    SignInArgs,
    SignUpArgs,
    Token,
)
from src.dependencies import get_user_service
from src.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=Token)
async def login(
    args: SignInArgs,
    service: UserService = Depends(get_user_service),
) -> Token:
    user = await service.authenticate_user(args.email, args.password)
    if user is None:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    return Token(access_token=create_access_token(user.id), token_type="bearer")


@router.post("/signup")
async def signup(
    args: SignUpArgs,
    service: UserService = Depends(get_user_service),
):
    try:
        password_hash = await service.prepare_signup(args.username, args.email, args.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pending = PendingSignup(
        email=args.email,
        username=args.username,
        password_hash=password_hash,
    )
    await send_confirmation_email(
        generate_signup_confirmation_token(pending),
        pending.username,
        pending.email,
    )
    return {"detail": "Email has been sent"}


@router.post("/signup-confirmation")
async def signup_confirmation(
    token: str,
    service: UserService = Depends(get_user_service),
):
    try:
        pending = read_signup_confirmation_token(token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if await service.user_repo.exists_by_email(pending.email):
        return {"detail": "Email has been already confirmed"}

    try:
        user = await service.create_user_from_hash(
            username=pending.username,
            email=pending.email,
            password_hash=pending.password_hash,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.post("/password-recovery")
async def recover_password(
    email: EmailStr,
    service: UserService = Depends(get_user_service),
):
    user = await service.user_repo.get_by_email(email)
    if user is not None:
        await send_reset_password_email(
            generate_password_reset_token(user),
            user.username,
            user.email,
        )
        logger.info("password_recovery_email_sent: user_id=%s", user.id)
    return {"detail": "Email has been sent"}


@router.patch("/reset-password")
async def reset_password(
    args: ResetPasswordArgs,
    service: UserService = Depends(get_user_service),
):
    invalid = HTTPException(status_code=400, detail="Invalid or expired token")

    try:
        user_id, fingerprint = read_password_reset_token(args.token)
    except ValueError:
        raise invalid

    try:
        user = await service.get_user(user_id)
    except ValueError:
        raise invalid

    if password_fingerprint(user.password_hash) != fingerprint:
        raise invalid

    try:
        await service.reset_password(user.id, args.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"detail": "Password updated successfully"}