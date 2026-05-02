"""Passkey (WebAuthn) registration + login, refresh rotation, logout.

Phase 1 policy:
* Registration is gated to existing user records (the OWNER row created by
  the seed script). Self-signup is disabled until invitations land in Phase 5.
* Each begin/finish pair is bound by a challenge_id stored in Redis with a
  short TTL. The cryptographic challenge itself lives inside the cached blob,
  not in the response, so a stolen challenge_id alone is useless.
* Refresh tokens rotate on every use; if a revoked token is replayed, ALL of
  that user's refresh tokens are revoked (compromise heuristic).
"""

import base64
import json
import secrets
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis_asyncio
from fastapi import APIRouter, Body, Cookie, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.api.deps import client_ip, get_current_user, user_agent
from app.config import get_settings
from app.core.audit import write_audit
from app.core.errors import AuthError, ConflictError, NotFoundError
from app.core.rate_limit import AUTH_LIMIT, limiter
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.db.models import Passkey, RefreshToken, User
from app.db.session import get_session
from app.schemas.auth import (
    LogoutResponse,
    PasskeyLoginBeginRequest,
    PasskeyLoginBeginResponse,
    PasskeyLoginFinishRequest,
    PasskeyRegisterBeginRequest,
    PasskeyRegisterBeginResponse,
    PasskeyRegisterFinishRequest,
    PasskeyRegisterFinishResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
_CHALLENGE_TTL_SECONDS = 300  # 5 min
_REFRESH_COOKIE_NAME = "aurum_refresh"


def _redis() -> redis_asyncio.Redis:
    return redis_asyncio.from_url(_settings.REDIS_URL)


def _challenge_key(challenge_id: str, kind: str) -> str:
    return f"webauthn:{kind}:{challenge_id}"


async def _store_challenge(kind: str, payload: dict) -> str:
    challenge_id = secrets.token_urlsafe(24)
    client = _redis()
    try:
        await client.set(
            _challenge_key(challenge_id, kind),
            json.dumps(payload),
            ex=_CHALLENGE_TTL_SECONDS,
        )
    finally:
        await client.aclose()
    return challenge_id


async def _consume_challenge(kind: str, challenge_id: str) -> dict | None:
    client = _redis()
    try:
        key = _challenge_key(challenge_id, kind)
        raw = await client.get(key)
        if raw is None:
            return None
        await client.delete(key)  # one-shot
    finally:
        await client.aclose()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def _set_refresh_cookie(response: Response, raw_token: str, max_age: int) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        path="/auth",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE_NAME, path="/auth")


async def _issue_tokens(
    session: AsyncSession,
    *,
    user: User,
    request: Request,
    response: Response,
) -> TokenResponse:
    access, expires_at = create_access_token(user_id=user.id, role=user.role.value)
    raw_refresh, digest, refresh_expires = generate_refresh_token()

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=refresh_expires,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
        )
    )

    _set_refresh_cookie(
        response,
        raw_refresh,
        max_age=_settings.JWT_REFRESH_TTL_SECONDS,
    )

    return TokenResponse(access_token=access, expires_at=expires_at)


# ============================================================
# Registration
# ============================================================


@router.post(
    "/passkey/register/begin",
    response_model=PasskeyRegisterBeginResponse,
)
@limiter.limit(AUTH_LIMIT)
async def passkey_register_begin(
    request: Request,
    response: Response,
    body: PasskeyRegisterBeginRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> PasskeyRegisterBeginResponse:
    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()

    if user is None:
        await write_audit(
            session,
            action="auth.register.begin",
            status="failure",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "unknown_email"},
        )
        # Generic error to avoid email enumeration
        raise NotFoundError("registration not permitted for this email")

    existing_creds = (
        await session.execute(
            select(Passkey.credential_id).where(Passkey.user_id == user.id)
        )
    ).scalars().all()

    options = generate_registration_options(
        rp_id=_settings.RP_ID,
        rp_name=_settings.RP_NAME,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid) for cid in existing_creds
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )

    challenge_id = await _store_challenge(
        "register",
        {
            "user_id": str(user.id),
            "challenge_b64": base64.b64encode(options.challenge).decode("ascii"),
            "nickname": body.nickname,
        },
    )

    await write_audit(
        session,
        action="auth.register.begin",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    return PasskeyRegisterBeginResponse(
        challenge_id=challenge_id,
        publicKey=json.loads(options_to_json(options)),
    )


@router.post(
    "/passkey/register/finish",
    response_model=PasskeyRegisterFinishResponse,
)
@limiter.limit(AUTH_LIMIT)
async def passkey_register_finish(
    request: Request,
    response: Response,
    body: PasskeyRegisterFinishRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> PasskeyRegisterFinishResponse:
    cached = await _consume_challenge("register", body.challenge_id)
    if cached is None:
        await write_audit(
            session,
            action="auth.register.finish",
            status="failure",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "challenge_expired_or_unknown"},
        )
        raise AuthError("challenge expired or unknown")

    user_id = uuid.UUID(cached["user_id"])
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("user vanished mid-registration")

    expected_challenge = base64.b64decode(cached["challenge_b64"])

    try:
        verification = verify_registration_response(
            credential=body.credential,
            expected_challenge=expected_challenge,
            expected_origin=_settings.PUBLIC_ORIGIN,
            expected_rp_id=_settings.RP_ID,
            require_user_verification=False,
        )
    except Exception as exc:
        await write_audit(
            session,
            action="auth.register.finish",
            status="failure",
            user_id=user_id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "verification_failed", "detail": str(exc)[:200]},
        )
        raise AuthError("registration verification failed") from exc

    # Reject if this credential is already registered (defense in depth —
    # exclude_credentials should have prevented the prompt, but verify anyway).
    dup = (
        await session.execute(
            select(Passkey).where(Passkey.credential_id == verification.credential_id)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ConflictError("credential already registered")

    nickname = body.nickname or cached.get("nickname")
    transports = body.credential.get("response", {}).get("transports") or None

    passkey = Passkey(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        transports=transports,
        nickname=nickname,
    )
    session.add(passkey)
    await session.flush()

    await write_audit(
        session,
        action="auth.register.finish",
        status="success",
        user_id=user.id,
        resource=f"passkey:{passkey.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    return PasskeyRegisterFinishResponse(passkey_id=str(passkey.id))


# ============================================================
# Login
# ============================================================


@router.post("/passkey/login/begin", response_model=PasskeyLoginBeginResponse)
@limiter.limit(AUTH_LIMIT)
async def passkey_login_begin(
    request: Request,
    response: Response,
    body: PasskeyLoginBeginRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> PasskeyLoginBeginResponse:
    allow_creds: list[PublicKeyCredentialDescriptor] = []
    user_hint: User | None = None

    if body.email:
        user_hint = (
            await session.execute(
                select(User).where(User.email == body.email.lower())
            )
        ).scalar_one_or_none()
        if user_hint is not None:
            cred_ids = (
                await session.execute(
                    select(Passkey.credential_id).where(
                        Passkey.user_id == user_hint.id
                    )
                )
            ).scalars().all()
            allow_creds = [
                PublicKeyCredentialDescriptor(id=cid) for cid in cred_ids
            ]

    options = generate_authentication_options(
        rp_id=_settings.RP_ID,
        allow_credentials=allow_creds,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    challenge_id = await _store_challenge(
        "login",
        {
            "challenge_b64": base64.b64encode(options.challenge).decode("ascii"),
            "user_hint_id": str(user_hint.id) if user_hint else None,
        },
    )

    await write_audit(
        session,
        action="auth.login.begin",
        status="success",
        user_id=user_hint.id if user_hint else None,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    return PasskeyLoginBeginResponse(
        challenge_id=challenge_id,
        publicKey=json.loads(options_to_json(options)),
    )


@router.post("/passkey/login/finish", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
async def passkey_login_finish(
    request: Request,
    response: Response,
    body: PasskeyLoginFinishRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    cached = await _consume_challenge("login", body.challenge_id)
    if cached is None:
        await write_audit(
            session,
            action="auth.login.finish",
            status="failure",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "challenge_expired_or_unknown"},
        )
        raise AuthError("challenge expired or unknown")

    expected_challenge = base64.b64decode(cached["challenge_b64"])

    raw_id = body.credential.get("rawId") or body.credential.get("id")
    if not raw_id:
        raise AuthError("credential missing id")
    try:
        cred_id_bytes = base64.urlsafe_b64decode(raw_id + "==")
    except Exception as exc:
        raise AuthError("malformed credential id") from exc

    passkey = (
        await session.execute(
            select(Passkey).where(Passkey.credential_id == cred_id_bytes)
        )
    ).scalar_one_or_none()
    if passkey is None:
        await write_audit(
            session,
            action="auth.login.finish",
            status="failure",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "unknown_credential"},
        )
        raise AuthError("unknown credential")

    user = await session.get(User, passkey.user_id)
    if user is None or not user.is_active:
        await write_audit(
            session,
            action="auth.login.finish",
            status="failure",
            user_id=passkey.user_id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "user_inactive"},
        )
        raise AuthError("user inactive")

    try:
        verification = verify_authentication_response(
            credential=body.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_settings.RP_ID,
            expected_origin=_settings.PUBLIC_ORIGIN,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        await write_audit(
            session,
            action="auth.login.finish",
            status="failure",
            user_id=user.id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "assertion_failed", "detail": str(exc)[:200]},
        )
        raise AuthError("assertion verification failed") from exc

    passkey.sign_count = verification.new_sign_count
    passkey.last_used_at = datetime.now(timezone.utc)

    tokens = await _issue_tokens(session, user=user, request=request, response=response)

    await write_audit(
        session,
        action="auth.login.success",
        status="success",
        user_id=user.id,
        resource=f"passkey:{passkey.id}",
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    return tokens


# ============================================================
# Refresh + logout
# ============================================================


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
async def refresh(
    request: Request,
    response: Response,
    aurum_refresh: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    if not aurum_refresh:
        raise AuthError("missing refresh token")

    digest = hash_refresh_token(aurum_refresh)
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == digest)
        )
    ).scalar_one_or_none()

    if row is None:
        await write_audit(
            session,
            action="auth.refresh",
            status="failure",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "unknown_token"},
        )
        raise AuthError("unknown refresh token")

    now = datetime.now(timezone.utc)

    # Reuse detection: revoked token replayed → revoke ALL of this user's tokens.
    if row.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await write_audit(
            session,
            action="auth.refresh.reuse_detected",
            status="failure",
            user_id=row.user_id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"all_tokens_revoked": True},
        )
        _clear_refresh_cookie(response)
        raise AuthError("refresh token reuse detected; all sessions revoked")

    if row.expires_at <= now:
        row.revoked_at = now
        await write_audit(
            session,
            action="auth.refresh",
            status="failure",
            user_id=row.user_id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"reason": "expired"},
        )
        _clear_refresh_cookie(response)
        raise AuthError("refresh token expired")

    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthError("user inactive")

    # Rotate: revoke old, issue new.
    row.revoked_at = now
    row.last_used_at = now

    tokens = await _issue_tokens(session, user=user, request=request, response=response)

    await write_audit(
        session,
        action="auth.refresh",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    return tokens


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit(AUTH_LIMIT)
async def logout(
    request: Request,
    response: Response,
    aurum_refresh: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> LogoutResponse:
    revoked = False
    user_id: uuid.UUID | None = None

    if aurum_refresh:
        digest = hash_refresh_token(aurum_refresh)
        row = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == digest)
            )
        ).scalar_one_or_none()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            revoked = True
            user_id = row.user_id

    _clear_refresh_cookie(response)

    await write_audit(
        session,
        action="auth.logout",
        status="success" if revoked else "no_op",
        user_id=user_id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )

    response.status_code = status.HTTP_200_OK
    return LogoutResponse(revoked=revoked)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_LIMIT)
async def logout_all(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke every refresh token for the current user, including the current session.

    Audit metadata records the count revoked so we can detect "panic-button"
    sign-outs in the trail without storing the tokens themselves.
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    _clear_refresh_cookie(response)
    await write_audit(
        session,
        action="auth.logout_all",
        status="success",
        user_id=user.id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        metadata={"revoked_count": result.rowcount or 0},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
