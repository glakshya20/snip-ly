# snip.ly — URL Shortener Microservice
Deployed @ https://snip-ly-production-d807.up.railway.app/docs
> **Shorten URLs. Track every click. Ship in minutes.**

A production-grade URL shortener built as a single FastAPI microservice backed by Redis.
Handles **10k+ req/sec** on a single node (benchmarked with `wrk`). Includes a React analytics dashboard.

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
  POST /shorten  ──────▶│                                         │
                        │          FastAPI (uvicorn)              │
  GET  /{code}   ──────▶│          4 async workers                │──── 302 Redirect
                        │                                         │
  GET  /analytics/{code}│  ┌─────────────┐  ┌─────────────────┐  │
                        │  │  Shortener  │  │    Analytics    │  │
                        │  │  generate   │  │  record_click() │  │
                        │  │  validate   │  │  get_analytics()│  │
                        │  └──────┬──────┘  └────────┬────────┘  │
                        │         │                  │           │
                        └─────────┼──────────────────┼───────────┘
                                  │                  │
                        ┌─────────▼──────────────────▼───────────┐
                        │              Redis 7                    │
                        │                                         │
                        │  snip:{code}:url   → "https://..."      │
                        │  snip:{code}:clicks → [event, ...]      │
                        │  snip:{code}:hll   → HyperLogLog (IPs)  │
                        └─────────────────────────────────────────┘
```

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Storage | Redis | Sub-ms reads, native TTL, HyperLogLog for unique IPs |
| Redirect code | `302` | Prevents browser caching → every click is counted |
| Unique IPs | HyperLogLog | O(1) memory, ~0.8% error rate vs exact sets |
| Code generation | Base62, 6 chars | 56B combinations, collision probability negligible |
| Workers | 4 async uvicorn | Non-blocking I/O; Redis calls never block the event loop |

---

## Quick Start

```bash
# 1. Clone and start
git clone https://github.com/glakshya20/snip-ly
cd snip-ly
docker-compose up --build

# 2. Shorten a URL
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/glakshya20", "alias": "my-github"}'

# 3. Visit the short link (will redirect)
curl -L http://localhost:8000/my-github

# 4. View analytics
curl http://localhost:8000/analytics/my-github
```

### API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/shorten` | Create a short URL |
| `GET` | `/{code}` | Redirect (records click) |
| `GET` | `/analytics/{code}?days=7` | Click analytics |
| `DELETE` | `/shorten/{code}` | Delete a link |
| `GET` | `/health` | Health check |

**POST `/shorten` body:**
```json
{
  "url": "https://your-long-url.com",
  "alias": "my-link",        // optional custom code
  "ttl_days": 30             // optional expiry
}
```

**GET `/analytics/{code}` response:**
```json
{
  "code": "my-github",
  "total_clicks": 342,
  "unique_clicks": 211,
  "today_clicks": 28,
  "daily": [
    { "date": "2025-07-08", "clicks": 22 },
    ...
  ],
  "top_referrers": { "GitHub": 48, "LinkedIn": 31 },
  "devices": { "desktop": 280, "mobile": 62 },
  "browsers": { "Chrome": 190, "Firefox": 80 }
}
```

---

## Benchmarks

Tested on a single MacBook Pro M2 (8 core) with `wrk -t8 -c100 -d30s`:

| Endpoint | Throughput | P99 Latency |
|----------|-----------|-------------|
| `GET /{code}` (redirect) | **12,400 req/sec** | 4.2ms |
| `POST /shorten` | **8,100 req/sec** | 6.8ms |
| `GET /analytics/{code}` | **6,200 req/sec** | 9.1ms |

Redis HyperLogLog keeps unique-IP tracking at **O(1) memory** regardless of click volume.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Tech Stack

- **FastAPI** — async REST framework
- **Redis 7** — URL store + click events + HyperLogLog
- **uvicorn** — ASGI server (4 workers)
- **Docker + docker-compose** — one-command deployment
- **React + Chart.js** — analytics frontend

---

## Roadmap

- [ ] Rate limiting per IP (Redis sliding window)
- [ ] QR code generation endpoint
- [ ] Geo-analytics (MaxMind GeoIP2)
- [ ] Webhook on N-th click milestone
- [ ] Prometheus `/metrics` endpoint
