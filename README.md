# SchoolPulse

A QR-based school attendance and parent notification platform.

## Current architecture

```text
Flutter mobile app  ──HTTPS/REST──>  FastAPI  ──>  Supabase PostgreSQL
```

Authentication is handled by **Supabase Auth**. FastAPI never stores passwords.

## Planned applications

- Flutter mobile app (teachers, parents)
- School administration web dashboard (not started)

## Current status

**Day 2 — Authentication, multi-tenancy, classes and students.**

Implemented today:

- Supabase Auth login/logout with persisted session in the Flutter app
- JWT verification in FastAPI (`Authorization: Bearer <access token>`)
- Schools, user profiles, school memberships and roles
- Classes CRUD with school isolation
- Students CRUD with pagination, search and school isolation
- Alembic migration `0001_day2`

**Not implemented yet:** QR generation/scanning, attendance, check-in/check-out,
late calculation, parent notifications (WhatsApp/SMS/push), reports, analytics,
payments, subscription billing, admin web dashboard, AI, face recognition.

## Repository layout

```text
schoolpulse/
├── mobile/     Flutter application
├── backend/    FastAPI application
└── docs/       Architecture notes
```

## Prerequisites

| Tool | Version used |
| --- | --- |
| Flutter | 3.35.6 (stable) |
| Dart | 3.9.2 |
| Python | 3.12.4 |
| uv | 0.8.2 |
| Git | 2.46.0 |

## Backend setup

```bash
cd backend
uv sync
```

Create your local environment file:

```bash
cp .env.example .env
```

Then fill in:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | for migrations | Supabase PostgreSQL connection string |
| `SUPABASE_URL` | yes | Supabase project URL |
| `SUPABASE_JWT_SECRET` | yes | Supabase project JWT secret (server only) |
| `SUPABASE_JWT_AUDIENCE` | no | Defaults to `authenticated` |
| `CORS_ORIGINS` | no | Comma-separated allowed origins |
| `ENVIRONMENT` | no | `development` or `production` |

The application **starts without `DATABASE_URL`**. Only endpoints that touch
the database require it.

### Run the API

```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: <http://localhost:8000/api/v1/health>
- Interactive docs: <http://localhost:8000/docs>
- OpenAPI schema: <http://localhost:8000/openapi.json>

### Database migrations

```bash
# apply migrations
uv run alembic upgrade head

# revert the most recent migration
uv run alembic downgrade -1
```

`alembic.ini` and `SUPABASE`/DATABASE_URL must be set. Alembic reads
`DATABASE_URL` from the environment when present.

### Run backend tests

```bash
uv run pytest
```

Tests run against an in-memory SQLite database using the same SQLAlchemy
models; no PostgreSQL instance is required.

## Flutter setup

```bash
cd mobile
flutter pub get
```

Configuration is supplied at build/run time via `--dart-define`:

| Define | Purpose |
| --- | --- |
| `API_BASE_URL` | FastAPI base URL |
| `SUPABASE_URL` | Supabase project URL (public) |
| `SUPABASE_ANON_KEY` | Supabase publishable key (public) |

Only public Supabase values belong in the app. **Never ship
`SUPABASE_SERVICE_ROLE_KEY`, database passwords or the JWT secret to the client.**

### Running on Android

```bash
# Android emulator: 10.0.2.2 is the host machine
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
            --dart-define=SUPABASE_URL=<your-url> \
            --dart-define=SUPABASE_ANON_KEY=<your-key>

# Physical device: use your computer's LAN IP
flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8000 ...
```

`localhost` inside an Android emulator refers to the emulator itself, not your
development machine.

### Analyze and test Flutter

```bash
flutter analyze
flutter test
```

## Git

The repository is initialised with `main` as the default branch. Secrets are
excluded through `.gitignore`; only `.env.example` files are committed.