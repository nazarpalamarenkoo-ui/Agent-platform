import pytest

from src.api.routers import admin
from src.db.enums.user_role import UserRole
from src.dependencies import get_user_service
from src.schemas.user import AdminUserRead
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

pytestmark = pytest.mark.unit

ROUTER = admin.router
SERVICE_DEPENDENCY = get_user_service
SERVICE_SPEC = UserService

ERRORS = [
    (NotFoundError("not found"), 404),
    (ForbiddenError("forbidden"), 403),
    (ConflictError("conflict"), 409),
    (ValueError("bad"), 400),
]


class TestListAdmins:
    async def test_super_admin_gets_list(self, client, service, as_super_admin, fake):
        service.list_admins.return_value = [fake(AdminUserRead, id=1), fake(AdminUserRead, id=2)]

        response = await client.get("/admin/admins")

        assert response.status_code == 200
        assert [u["id"] for u in response.json()] == [1, 2]

    @pytest.mark.parametrize("role_fixture", ["actor", "as_admin"])
    async def test_non_super_admin_is_forbidden(self, client, service, request, role_fixture):
        request.getfixturevalue(role_fixture)

        response = await client.get("/admin/admins")

        assert response.status_code == 403
        service.list_admins.assert_not_awaited()


class TestSetUserRole:
    async def test_super_admin_sets_role(self, client, service, as_super_admin, fake):
        service.set_role.return_value = fake(AdminUserRead, id=5, role=UserRole.ADMIN)

        response = await client.put("/admin/users/5/role", json={"role": "admin"})

        assert response.status_code == 200
        service.set_role.assert_awaited_once_with(as_super_admin, 5, UserRole.ADMIN)

    async def test_cannot_assign_super_admin_role(self, client, service, as_super_admin):
        response = await client.put("/admin/users/5/role", json={"role": "super_admin"})

        assert response.status_code == 422
        service.set_role.assert_not_awaited()

    async def test_admin_is_forbidden(self, client, service, as_admin):
        response = await client.put("/admin/users/5/role", json={"role": "user"})

        assert response.status_code == 403
        service.set_role.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, as_super_admin, error, code):
        service.set_role.side_effect = error

        response = await client.put("/admin/users/5/role", json={"role": "user"})

        assert response.status_code == code
        assert response.json()["detail"] == str(error)


class TestListUsers:
    async def test_admin_uses_default_pagination(self, client, service, as_admin, fake):
        service.list_users.return_value = [fake(AdminUserRead, id=1)]

        response = await client.get("/admin/users")

        assert response.status_code == 200
        service.list_users.assert_awaited_once_with(limit=50, offset=0)

    async def test_passes_custom_pagination(self, client, service, as_admin):
        service.list_users.return_value = []

        await client.get("/admin/users", params={"limit": 10, "offset": 20})

        service.list_users.assert_awaited_once_with(limit=10, offset=20)

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, as_admin, params):
        response = await client.get("/admin/users", params=params)

        assert response.status_code == 422
        service.list_users.assert_not_awaited()

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.get("/admin/users")

        assert response.status_code == 403
        service.list_users.assert_not_awaited()


class TestGetUser:
    async def test_returns_user(self, client, service, as_admin, fake):
        service.get_user_for.return_value = fake(AdminUserRead, id=9)

        response = await client.get("/admin/users/9")

        assert response.status_code == 200
        assert response.json()["id"] == 9
        service.get_user_for.assert_awaited_once_with(as_admin, 9)

    @pytest.mark.parametrize("error,code", [(NotFoundError("nf"), 404), (ForbiddenError("fb"), 403)])
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.get_user_for.side_effect = error

        response = await client.get("/admin/users/9")

        assert response.status_code == code

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.get("/admin/users/9")

        assert response.status_code == 403
        service.get_user_for.assert_not_awaited()


class TestTokenLimit:
    async def test_sets_limit(self, client, service, as_admin, fake):
        service.set_token_limit.return_value = fake(AdminUserRead, id=3)

        response = await client.put("/admin/users/3/token-limit", json={"token_limit": 500})

        assert response.status_code == 200
        service.set_token_limit.assert_awaited_once_with(as_admin, 3, 500)

    async def test_zero_limit_is_allowed(self, client, service, as_admin, fake):
        service.set_token_limit.return_value = fake(AdminUserRead, id=3)

        response = await client.put("/admin/users/3/token-limit", json={"token_limit": 0})

        assert response.status_code == 200

    @pytest.mark.parametrize("payload", [{}, {"token_limit": -1}, {"token_limit": "abc"}])
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.put("/admin/users/3/token-limit", json=payload)

        assert response.status_code == 422
        service.set_token_limit.assert_not_awaited()

    @pytest.mark.parametrize("error,code", [(NotFoundError("nf"), 404), (ForbiddenError("fb"), 403)])
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.set_token_limit.side_effect = error

        response = await client.put("/admin/users/3/token-limit", json={"token_limit": 5})

        assert response.status_code == code


class TestResetUsage:
    async def test_resets_usage(self, client, service, as_admin, fake):
        service.reset_usage.return_value = fake(AdminUserRead, id=3)

        response = await client.post("/admin/users/3/reset-usage")

        assert response.status_code == 200
        service.reset_usage.assert_awaited_once_with(as_admin, 3)

    @pytest.mark.parametrize("error,code", [(NotFoundError("nf"), 404), (ForbiddenError("fb"), 403)])
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.reset_usage.side_effect = error

        response = await client.post("/admin/users/3/reset-usage")

        assert response.status_code == code

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.post("/admin/users/3/reset-usage")

        assert response.status_code == 403
        service.reset_usage.assert_not_awaited()