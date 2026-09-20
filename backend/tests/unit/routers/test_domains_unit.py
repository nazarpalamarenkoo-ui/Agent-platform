from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import domains
from src.dependencies import get_domain_service
from src.services.domain_service import DomainService

pytestmark = pytest.mark.unit

ROUTER = domains.router
SERVICE_DEPENDENCY = get_domain_service
SERVICE_SPEC = DomainService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)

VALID_PAYLOAD = {
    "slug": "backend-api-design",
    "name": "Backend API Design",
    "description": "Designing backend APIs",
    "parent_domain_id": None,
}


def make_domain(domain_id=1, **overrides):
    data = {
        "id": domain_id,
        "slug": f"domain-{domain_id}",
        "name": f"Domain {domain_id}",
        "description": "Test domain",
        "parent_domain_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


async def test_create_root_domain_returns_201(client, service):
    service.create_domain.return_value = make_domain(3, slug="backend-api-design")

    response = await client.post("/domains", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 3
    assert body["slug"] == "backend-api-design"
    service.create_domain.assert_awaited_once_with(
        "backend-api-design", "Backend API Design", "Designing backend APIs", None
    )


async def test_create_child_domain_passes_parent_id(client, service):
    service.create_domain.return_value = make_domain(4, parent_domain_id=3)

    response = await client.post("/domains", json={**VALID_PAYLOAD, "parent_domain_id": 3})

    assert response.status_code == 201
    service.create_domain.assert_awaited_once_with(
        "backend-api-design", "Backend API Design", "Designing backend APIs", 3
    )


async def test_create_domain_value_error_returns_400(client, service):
    service.create_domain.side_effect = ValueError("Domain with slug backend-api-design already exists")

    response = await client.post("/domains", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Domain with slug backend-api-design already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "slug": ["x"]},
        {**VALID_PAYLOAD, "parent_domain_id": "abc"},
    ],
)
async def test_create_domain_rejects_invalid_payload(client, service, payload):
    response = await client.post("/domains", json=payload)

    assert response.status_code == 422
    service.create_domain.assert_not_awaited()


async def test_get_all_domains_uses_default_pagination(client, service):
    service.get_all_domains.return_value = [make_domain(1), make_domain(2)]

    response = await client.get("/domains")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_all_domains.assert_awaited_once_with(limit=100, offset=0)


async def test_get_all_domains_passes_custom_pagination(client, service):
    service.get_all_domains.return_value = []

    response = await client.get("/domains", params={"limit": 5, "offset": 10})

    assert response.status_code == 200
    service.get_all_domains.assert_awaited_once_with(limit=5, offset=10)


async def test_get_root_domains_is_not_shadowed_by_domain_id_route(client, service):
    service.get_root_domains.return_value = [make_domain(1)]

    response = await client.get("/domains/roots")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]
    service.get_root_domains.assert_awaited_once_with()
    service.get_domain.assert_not_awaited()


async def test_get_domain_returns_domain(client, service):
    service.get_domain.return_value = make_domain(9)

    response = await client.get("/domains/9")

    assert response.status_code == 200
    assert response.json()["id"] == 9
    service.get_domain.assert_awaited_once_with(9)


async def test_get_domain_not_found_returns_404(client, service):
    service.get_domain.side_effect = ValueError("Domain 9 not found")

    response = await client.get("/domains/9")

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain 9 not found"


async def test_get_domain_invalid_id_returns_422(client, service):
    response = await client.get("/domains/abc")

    assert response.status_code == 422
    service.get_domain.assert_not_awaited()
