from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional
import re


class ShortenRequest(BaseModel):
    url: HttpUrl
    alias: Optional[str] = Field(
        None,
        min_length=3,
        max_length=30,
        description="Optional custom alias (alphanumeric + hyphens only)",
    )
    ttl_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Auto-expire after N days (omit for no expiry)",
    )

    @field_validator("alias")
    @classmethod
    def alias_format(cls, v):
        if v and not re.fullmatch(r"[a-zA-Z0-9\-]+", v):
            raise ValueError("Alias must contain only letters, digits, and hyphens")
        return v


class ShortenResponse(BaseModel):
    short_url: str
    code: str
    original_url: str
    expires_in_days: Optional[int]


class DailyCount(BaseModel):
    date: str          # "2025-07-14"
    clicks: int


class AnalyticsResponse(BaseModel):
    code: str
    original_url: str
    total_clicks: int
    unique_clicks: int
    today_clicks: int
    daily: list[DailyCount]
    top_referrers: dict[str, int]
    devices: dict[str, int]
    browsers: dict[str, int]
