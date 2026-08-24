# GeoMap Backend

GeoMap is a location-aware travel and discovery backend. It helps people find
places near them, learn the details of a place, ask real questions about it,
plan trips with an AI assistant, and keep a personal history of everything they
do — all behind one clean API.

Think of it as the engine room for a travel app: search where to go, unlock a
place you're curious about, chat with an AI about it, check the weather before
you leave, log your visit afterwards, and compare spots side by side when you
can't decide.

## What it does

- **Place discovery** — free-text search, nearby search, and typeahead
  autocomplete, powered by the Google Places API (with Redis caching so repeat
  searches are instant).
- **Place details & unlock** — rich details (hours, rating, amenities, contact,
  reviews) are gated behind a small credit spend per place.
- **AI Q&A about a place** — ask "What time does it close?" or "Is it
  wheelchair accessible?" and get a grounded answer from the place's own data.
  Backed by OpenAI embeddings + a Pinecone vector index (RAG), with streaming
  over WebSocket.
- **AI travel assistant** — a general trip-planning chat (itineraries,
  comparisons, destination ideas) that keeps conversation history across
  sessions.
- **Weather & air quality** — forecasts from Open-Meteo for the user's saved
  location.
- **Routes & directions** — Google Routes API for travel between places.
- **Personal layer** — saved places, visit logs with ratings and stats, and a
  full GPS location history.
- **Comparison** — compare up to 10 places side by side, with optional AI
  recommendations.
- **Payments & credits** — buy credits with Razorpay (fixed packages or custom
  amounts). AI chat and place unlocks spend credits.
- **Auth** — email + OTP signup, short-lived JWT access tokens (30 min),
  password reset, all rate-limited.

## Tech stack

| Layer      | Technology                                              |
| ---------- | ------------------------------------------------------- |
| API        | FastAPI (Python 3.11), uvicorn                          |
| Database   | PostgreSQL 16 (SQLAlchemy 2 + Alembic migrations)       |
| Cache      | Redis 7 (search/details caching, OTPs, token blacklist) |
| Search     | Google Places API (Text Search, Nearby, Autocomplete)   |
| Routes     | Google Routes API                                       |
| Weather    | Open-Meteo (forecast + air quality)                     |
| AI         | OpenAI (embeddings + chat), Pinecone (vector search)    |
| Payments   | Razorpay (orders, verify, webhooks)                     |
| Email      | SMTP (Mailpit in local dev to catch emails)             |
| Rate limit | slowapi (per-IP and per-route)                          |

## Project layout

```
app/
  api/v1/        # All HTTP routes and WebSocket endpoint
  core/          # Config, security (JWT), rate limiter, Redis, WS manager
  database/      # Engine, session, declarative base
  dependencies/  # FastAPI dependency providers (auth, services)
  exceptions/    # Custom error types
  integrations/  # Clients for external services (Google, OpenAI, Pinecone...)
  models/        # SQLAlchemy ORM models
  repositories/  # Data-access layer (one per model)
  schemas/       # Pydantic request/response models
  services/      # Business logic (auth, discovery, AI chat, payments...)
  utils/         # Place category mapping and helpers
  validators/    # Input validation helpers
tests/           # Pytest suite
alembic/         # Database migration scripts
```

The layering is strict: routes → services → repositories → models. Integrations
(Google, OpenAI, etc.) live in `integrations/` and are injected into services
via FastAPI dependencies, which keeps external calls testable.

## Quick start (Docker)

### 1. Configure environment variables

Copy the sample env file and fill in the values:

```bash
cp .env.example .env          # local development (uvicorn)
cp .env.example .env.docker   # used inside Docker containers
```

Minimum required keys:

| Variable                | What it's for                         |
| ----------------------- | ------------------------------------- |
| `DATABASE_URL`          | PostgreSQL connection string          |
| `SECRET_KEY`            | JWT signing secret (min 32 chars)     |
| `GOOGLE_PLACES_API_KEY` | Google Places API key                 |
| `OPENAI_API_KEY`        | OpenAI key (embeddings + chat)        |
| `PINECONE_API_KEY`      | Pinecone key (knowledge index)        |

Optional: `REDIS_HOST` / `REDIS_PORT` (defaults to `localhost` / `6379`),
`SMTP_*` for real email, `RAZORPAY_*` for payments, and `TRUSTED_PROXY_IPS`
if you run behind a proxy. The sample env file ships `SMTP_*` / `RAZORPAY_*`
keys with placeholder values — fill them in with your own credentials.

### 2. Build and start the services

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps
ngrok http 8000
```

This brings up PostgreSQL, Redis, Redis Insight (web UI on port 5540),
Mailpit (email catcher, web UI on port 8025), the API, and runs migrations.

### 3. Apply database migrations

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

### 4. Open the app

- API + interactive docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/
- Redis Insight: http://localhost:5540
- Mailpit (catch OTP emails locally): http://localhost:8025

### Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

You'll need PostgreSQL and Redis running locally (or point `DATABASE_URL` and
`REDIS_HOST` at an external instance) and apply migrations with
`alembic upgrade head`.

## How the credits economy works

Users start with credits and spend them on AI features:

| Action                      | Cost             |
| --------------------------- | ---------------- |
| AI travel chat message      | 5 credits        |
| Unlock a place              | 10 credits       |
| Questions about an unlock   | free (15 per unlock) |

Buy more credits with Razorpay:

| Package  | Price   | Credits |
| -------- | ------- | ------- |
| Starter  | ₹150    | 50      |
| Popular  | ₹300    | 110     |
| Pro      | ₹500    | 190     |
| Ultimate | ₹1000   | 400     |
| Custom   | ₹3 each | floored |

A place unlock gives 15 Q&A questions. Once used up, the place relocks and a
fresh unlock (10 credits) is needed to ask more.

## API overview

All routes are prefixed with `/api` and documented at `/docs`.

### Auth
`POST /auth/signup` → `POST /auth/verify-otp` → access token.
Also: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`.

Notes:
- Access tokens are short-lived JWTs (30 min). Logout and token renewal are
  handled entirely on the client side — no server-side logout or refresh endpoints.
- Re-calling `/auth/signup` with the same email before verification resends a fresh OTP (no separate resend endpoint).
- Password reset is two calls: `/auth/forgot-password` sends the OTP, then `/auth/reset-password` verifies it and sets the new password in one request.

### Locations
`GET /locations/me`, `POST /locations/gps`, `GET /locations/history`,
`GET /locations/latest`, `DELETE /locations/current`,
`DELETE /locations/history/{id}`.

### Discovery
`POST /discovery/search` (text), `POST /discovery/nearby`,
`GET /discovery/autocomplete`.

### Places
`POST /places/{place_id}/unlock`, `GET /places/{place_id}/details`,
`POST /places/{place_id}/question`, `GET /places/unlocked`,
`GET /places/qa/sessions`, `GET /places/qa/sessions/{id}`,
`DELETE /places/qa/sessions`.

### Saved places & visits
`POST /places/{place_id}/save`, `DELETE /places/saved/{saved_id}`,
`GET /places/saved`, `GET /places/saved/nearby`,
`POST /places/{place_id}/visit`,
`GET/PATCH/DELETE /visits[/{id}]`, `GET /visits/stats`.

### Travel assistant
`POST /chat/message` — or stream over WebSocket `/ws/chat`.

### Routes & weather
`POST /routes/compute`, `POST /weather`.

### Comparison
`POST /compare` with `comparison_type` set to `basic` or `recommendation`.

### Payments
`GET /payments/packages`, `POST /payments/orders`, `POST /payments/verify`,
`GET /payments` (history), plus the webhook at `POST /payments/webhook`
(called by Razorpay).

## Common flows

**Signup**
1. `POST /auth/signup` with full name, email, password.
2. Receive the 6-digit OTP by email (Mailpit locally).
3. `POST /auth/verify-otp` → returns an access token.

**Discover a place**
1. `POST /locations/gps` with your lat/lng.
2. `POST /discovery/search` ("best cafe near me") or use autocomplete.
3. `POST /places/{place_id}/unlock` (10 credits).
4. `GET /places/{place_id}/details` for the full profile.

**Ask about a place**
- `POST /places/{place_id}/question` for a one-shot answer, or
- Connect to `ws://localhost:8000/ws/chat` and stream the answer token by token.

**Buy credits**
1. `GET /payments/packages` to see options.
2. `POST /payments/orders` to create a Razorpay order.
3. Complete checkout on the frontend, then `POST /payments/verify` with the
   returned signature. (The webhook also credits the user automatically.)

## WebSocket usage

Connect to `/ws/chat`, then send an auth frame first:

```json
{ "type": "auth", "token": "Bearer <access-token>" }
```

Then you can send:

```json
{ "type": "chat_message", "query": "Plan a 3-day Goa itinerary", "session_id": null }
```

or

```json
{ "type": "place_question", "place_id": "ChIJ...", "query": "What time does it close?", "session_id": null, "top_k": 5 }
```

Answers arrive as streaming frames: `metadata` (with the session id), repeated
`token` frames, then `done`. Errors come as `error` frames and never kill the
connection.

## Running tests

```bash
pytest -q
```

The suite covers auth flows, location handling, payment workflows, AI fallback
behavior, and retry logic.

## Notes

- The knowledge sync for a place runs automatically when its details are
  fetched (first time or when the data is stale). The Pinecone index powers
  Q&A answers.
- Key endpoints (auth, payments, AI chat, Q&A, weather, comparison) are
  rate-limited per IP and per route — the limits are tuned to keep external
  API costs in check.
- If OpenAI or Pinecone is unavailable, Q&A and chat degrade gracefully: the
  AI returns structured facts it already has instead of a dead error.
- Logs are written to `logs/app.log` (and `logs/crashes.log` for unhandled
  errors) as well as stdout.
