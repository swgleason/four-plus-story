from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.supabase import get_supabase_client


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
