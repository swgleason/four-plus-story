from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.supabase import ensure_storage_bucket, get_supabase_client


@pytest.mark.asyncio
async def test_get_supabase_client_rejects_template_service_role_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_service_role_key="your_supabase_service_role_key_here",
    )
    monkeypatch.setattr("app.core.supabase.get_settings", lambda: settings)
    app = SimpleNamespace(state=SimpleNamespace())
    request = Request({"type": "http", "app": app})

    with pytest.raises(HTTPException) as error:
        await get_supabase_client(request)

    assert error.value.status_code == 503
    assert "SUPABASE_SERVICE_ROLE_KEY" in error.value.detail


@pytest.mark.asyncio
async def test_ensure_storage_bucket_creates_missing_bucket_as_private() -> None:
    class FakeStorage:
        def __init__(self) -> None:
            self.buckets: list[SimpleNamespace] = []
            self.created: list[tuple[str, dict[str, bool]]] = []

        async def list_buckets(self) -> list[SimpleNamespace]:
            return self.buckets

        async def create_bucket(
            self, bucket_name: str, options: dict[str, bool]
        ) -> None:
            self.created.append((bucket_name, options))

    storage = FakeStorage()
    await ensure_storage_bucket(SimpleNamespace(storage=storage), "raw-documents")

    assert storage.created == [("raw-documents", {"public": False})]


@pytest.mark.asyncio
async def test_ensure_storage_bucket_does_not_recreate_existing_bucket() -> None:
    class FakeStorage:
        async def list_buckets(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="raw-documents")]

        async def create_bucket(
            self, _bucket_name: str, _options: dict[str, bool]
        ) -> None:
            raise AssertionError("existing bucket should not be recreated")

    await ensure_storage_bucket(SimpleNamespace(storage=FakeStorage()), "raw-documents")
