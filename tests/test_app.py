"""
pytest test suite for snip.ly
Run: pytest tests/ -v --tb=short
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from app.main import app
from app.shortener import generate_code, validate_url
from app.analytics import parse_device, parse_browser, parse_referrer


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestShortener:
    def test_code_length(self):
        assert len(generate_code()) == 6

    def test_code_unique(self):
        codes = {generate_code() for _ in range(1000)}
        assert len(codes) == 1000  # no collisions in 1k sample

    def test_validate_ok(self):
        validate_url("https://github.com/foo")  # should not raise

    def test_validate_localhost_blocked(self):
        with pytest.raises(ValueError, match="localhost"):
            validate_url("http://localhost:8080/admin")

    def test_validate_non_http(self):
        with pytest.raises(ValueError):
            validate_url("ftp://files.example.com/data")


class TestParsers:
    def test_mobile_ua(self):
        assert parse_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)") == "mobile"

    def test_desktop_ua(self):
        assert parse_device("Mozilla/5.0 (Windows NT 10.0; Win64; x64)") == "desktop"

    def test_chrome_browser(self):
        assert parse_browser("Mozilla/5.0 Chrome/120 Safari/537") == "Chrome"

    def test_firefox_browser(self):
        assert parse_browser("Mozilla/5.0 Gecko/20100101 Firefox/120") == "Firefox"

    def test_direct_referrer(self):
        assert parse_referrer("") == "Direct"

    def test_github_referrer(self):
        assert parse_referrer("https://github.com/glakshya20") == "GitHub"

    def test_linkedin_referrer(self):
        assert parse_referrer("https://www.linkedin.com/feed") == "LinkedIn"


# ── Integration tests (async) ─────────────────────────────────────────────────

@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.get.return_value = None       # default: not found
    store.incr_unique.return_value = True
    store.get_unique_count.return_value = 0
    store.get_clicks.return_value = []
    return store


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_shorten_and_redirect(mock_store):
    with patch("app.main.store", mock_store):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Shorten
            r = await ac.post("/shorten", json={"url": "https://github.com/glakshya20"})
            assert r.status_code == 201
            body = r.json()
            assert "short_url" in body
            code = body["code"]

            # Redirect (mock store returns the URL now)
            mock_store.get.return_value = "https://github.com/glakshya20"
            r = await ac.get(f"/{code}", follow_redirects=False)
            assert r.status_code == 302
            assert r.headers["location"] == "https://github.com/glakshya20"


@pytest.mark.asyncio
async def test_alias_collision(mock_store):
    mock_store.get.return_value = "https://existing.com"
    with patch("app.main.store", mock_store):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/shorten", json={"url": "https://new.com", "alias": "taken"})
            assert r.status_code == 409


@pytest.mark.asyncio
async def test_404_on_unknown_code(mock_store):
    mock_store.get.return_value = None
    with patch("app.main.store", mock_store):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/doesnotexist")
            assert r.status_code == 404
