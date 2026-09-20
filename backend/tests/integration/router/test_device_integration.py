from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from jose import jwt

from src.api.routers import device
from src.config import settings
from src.db.enums.device_code_status import DeviceStatus
from src.db.models.device_code import DeviceCode
from src.dependencies import get_device_auth_service
from src.repositories.device_code_repo import DeviceCodeRepository
from src.services.device_auth_service import DeviceAuthService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    service = DeviceAuthService(DeviceCodeRepository(db_session))
    application = build_app(device.router)
    application.dependency_overrides[get_device_auth_service] = lambda: service
    return application


@pytest_asyncio.fixture
async def expired_device_code(db_session, sample_user):
    device_code = DeviceCode(
        device_code="EXPIRED-0001",
        user_id=sample_user.id,
        status=DeviceStatus.PENDING,
        scope="read",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        interval=5,
    )
    db_session.add(device_code)
    await db_session.commit()
    await db_session.refresh(device_code)
    return device_code


def decode(token):
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])


async def test_initiate_flow_returns_device_code(client, sample_user):
    response = await client.post("/device/initiate", json={"user_id": sample_user.id, "scope": "read write"})

    assert response.status_code == 200
    assert response.json()["device_code"]


async def test_initiate_flow_generates_unique_codes(client, sample_user):
    payload = {"user_id": sample_user.id, "scope": "read"}

    first = await client.post("/device/initiate", json=payload)
    second = await client.post("/device/initiate", json=payload)

    assert first.json()["device_code"] != second.json()["device_code"]


async def test_verify_pending_code_returns_valid_token(client, sample_user, sample_device_code):
    response = await client.post("/device/verify", json={"device_code": sample_device_code.device_code})

    assert response.status_code == 200
    claims = decode(response.json()["access_token"])
    assert claims["sub"] == str(sample_user.id)
    assert claims["scope"] == "read write"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


async def test_verify_marks_code_as_approved(client, db_session, sample_device_code):
    await client.post("/device/verify", json={"device_code": sample_device_code.device_code})

    await db_session.refresh(sample_device_code)
    assert sample_device_code.status == DeviceStatus.APPROVED


async def test_full_flow_from_initiate_to_token(client, sample_user):
    initiated = await client.post("/device/initiate", json={"user_id": sample_user.id, "scope": "read"})

    response = await client.post("/device/verify", json={"device_code": initiated.json()["device_code"]})

    assert response.status_code == 200
    claims = decode(response.json()["access_token"])
    assert claims["sub"] == str(sample_user.id)
    assert claims["scope"] == "read"


async def test_verify_same_code_twice_returns_400_on_second_attempt(client, sample_device_code):
    payload = {"device_code": sample_device_code.device_code}

    first = await client.post("/device/verify", json=payload)
    second = await client.post("/device/verify", json=payload)

    assert first.status_code == 200
    assert second.status_code == 400


async def test_verify_unknown_code_returns_400(client):
    response = await client.post("/device/verify", json={"device_code": "UNKNOWN-0000"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired device code"


async def test_verify_already_approved_code_returns_400(client, approved_device_code):
    response = await client.post("/device/verify", json={"device_code": approved_device_code.device_code})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired device code"


async def test_verify_expired_code_returns_400(client, expired_device_code):
    response = await client.post("/device/verify", json={"device_code": expired_device_code.device_code})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired device code"
