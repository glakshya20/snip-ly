"""
Click analytics engine.
- record_click(): parse UA, referrer, IP → push to Redis
- get_analytics(): aggregate daily counts, referrers, device/browser split
"""

import hashlib
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Request

from .store import RedisStore
from .models import AnalyticsResponse, DailyCount


# ── UA parsing (no heavy deps — lightweight regex) ───────────────────────────

def parse_device(ua: str) -> str:
    ua = ua.lower()
    if any(t in ua for t in ("iphone", "android", "mobile")):
        return "mobile"
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    return "desktop"


def parse_browser(ua: str) -> str:
    ua = ua.lower()
    if "edg/" in ua:
        return "Edge"
    if "chrome" in ua and "safari" in ua:
        return "Chrome"
    if "firefox" in ua:
        return "Firefox"
    if "safari" in ua:
        return "Safari"
    if "curl" in ua or "python" in ua or "go-http" in ua:
        return "Bot/CLI"
    return "Other"


def parse_referrer(ref: str) -> str:
    if not ref:
        return "Direct"
    for name, fragment in [
        ("GitHub",    "github.com"),
        ("LinkedIn",  "linkedin.com"),
        ("Twitter",   "twitter.com"),
        ("Reddit",    "reddit.com"),
        ("Hacker News","news.ycombinator"),
        ("Google",    "google."),
        ("Facebook",  "facebook.com"),
    ]:
        if fragment in ref:
            return name
    return "Other"


# ── Recording ─────────────────────────────────────────────────────────────────

async def record_click(store: RedisStore, code: str, request: Request):
    ua = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "")
    ip = request.client.host if request.client else "0.0.0.0"
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]

    event = {
        "ts":       int(time.time()),
        "date":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "device":   parse_device(ua),
        "browser":  parse_browser(ua),
        "referrer": parse_referrer(referrer),
        "ip_hash":  ip_hash,
    }
    await store.push_click(code, event)
    await store.incr_unique(code, ip_hash)


# ── Aggregation ───────────────────────────────────────────────────────────────

async def get_analytics(
    store: RedisStore, code: str, days: int = 7
) -> AnalyticsResponse:
    original_url = await store.get(code)
    clicks = await store.get_clicks(code)
    unique = await store.get_unique_count(code)

    # Date window
    today = datetime.now(timezone.utc).date()
    window = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)}

    daily: dict[str, int] = defaultdict(int)
    referrers: dict[str, int] = defaultdict(int)
    devices: dict[str, int] = defaultdict(int)
    browsers: dict[str, int] = defaultdict(int)
    today_count = 0

    for ev in clicks:
        referrers[ev["referrer"]] += 1
        devices[ev["device"]] += 1
        browsers[ev["browser"]] += 1
        if ev["date"] in window:
            daily[ev["date"]] += 1
        if ev["date"] == today.strftime("%Y-%m-%d"):
            today_count += 1

    # Fill empty days with 0
    daily_series = [
        DailyCount(
            date=(today - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"),
            clicks=daily.get((today - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"), 0),
        )
        for i in range(days)
    ]

    return AnalyticsResponse(
        code=code,
        original_url=original_url,
        total_clicks=len(clicks),
        unique_clicks=unique,
        today_clicks=today_count,
        daily=daily_series,
        top_referrers=dict(sorted(referrers.items(), key=lambda x: -x[1])[:10]),
        devices=dict(devices),
        browsers=dict(browsers),
    )
