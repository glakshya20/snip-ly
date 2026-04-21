"""
snip.ly — URL Shortener Microservice
FastAPI + Redis | Click analytics, geo-tracking, referrer breakdown
"""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import time

from .models import ShortenRequest, ShortenResponse, AnalyticsResponse
from .shortener import generate_code, validate_url
from .store import RedisStore
from .analytics import record_click, get_analytics

app = FastAPI(
    title="snip.ly",
    description="URL Shortener Microservice with click analytics",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = RedisStore()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


# ── Shorten ───────────────────────────────────────────────────────────────────

@app.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten(body: ShortenRequest, request: Request):
    """
    Create a short URL.
    - Validates the destination URL
    - Optionally accepts a custom alias (e.g. `my-launch`)
    - Returns short_url, code, and expiry metadata
    """
    validate_url(body.url)

    code = body.alias or generate_code()

    # Prevent alias collision
    if body.alias and await store.get(body.alias):
        raise HTTPException(409, f"Alias '{body.alias}' is already taken")

    await store.save(code, str(body.url), ttl_days=body.ttl_days)

    base = str(request.base_url).rstrip("/")
    return ShortenResponse(
        short_url=f"{base}/{code}",
        code=code,
        original_url=str(body.url),
        expires_in_days=body.ttl_days,
    )


# ── Redirect ──────────────────────────────────────────────────────────────────

@app.get("/{code}")
async def redirect(code: str, request: Request, response: Response):
    """
    Resolve a short code → redirect to destination.
    Records: timestamp, IP, user-agent, referrer.
    """
    original_url = await store.get(code)
    if not original_url:
        raise HTTPException(404, f"Short URL '{code}' not found or expired")

    await record_click(store, code, request)

    # 302 so analytics keep counting (browser won't cache permanently)
    return RedirectResponse(url=original_url, status_code=302)


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics/{code}", response_model=AnalyticsResponse)
async def analytics(code: str, days: int = 7):
    """
    Return click analytics for a short code.
    Includes: total clicks, unique IPs, daily breakdown, top referrers, device types.
    """
    if not await store.get(code):
        raise HTTPException(404, f"Short URL '{code}' not found")

    return await get_analytics(store, code, days=days)


@app.delete("/shorten/{code}", status_code=204)
async def delete_link(code: str):
    """Delete a short link and all its analytics data."""
    if not await store.get(code):
        raise HTTPException(404, f"Short URL '{code}' not found")
    await store.delete(code)
