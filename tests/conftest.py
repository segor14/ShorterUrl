import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import Base
from src.settings import settings
from sqlalchemy import text

from httpx import AsyncClient, ASGITransport
from src.app import app
from src.db.db import get_db

# Используем базу данных из настроек или переопределяем для тестов
TEST_DATABASE_URL = settings.database_url


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as conn:
        # Установка расширения pgcrypto, как требовалось в задаче
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

        await session.rollback()


@pytest.fixture
async def client(session) -> AsyncGenerator[AsyncClient, None]:
    def _get_test_db():
        yield session

    app.dependency_overrides[get_db] = _get_test_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()
