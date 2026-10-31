import inspect
from typing import Callable, Generic, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession

R = TypeVar("R")


class PerCallRepository(Generic[R]):

    def __init__(self, repo_cls: type[R], session_factory: Callable[[], AsyncSession]):
        self._repo_cls = repo_cls
        self._session_factory = session_factory

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        method = getattr(self._repo_cls, name, None)
        if method is None or not inspect.iscoroutinefunction(method):
            raise AttributeError(
                f"{self._repo_cls.__name__}.{name} is not an async method; "
                f"PerCallRepository exposes only async methods"
            )

        async def call(*args, **kwargs):
            async with self._session_factory() as session:
                repo = self._repo_cls(session)
                result = await getattr(repo, name)(*args, **kwargs)
                await session.commit()
                return result

        call.__name__ = name
        return call


def per_call(repo_cls: type[R], session_factory: Callable[[], AsyncSession]) -> R:
    return cast(R, PerCallRepository(repo_cls, session_factory))