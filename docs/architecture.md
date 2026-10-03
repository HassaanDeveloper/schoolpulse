# Architecture

## System shape

```text
                 Flutter Mobile App
                         │
                         │ HTTPS / REST
                         ▼
                   FastAPI Backend
                         │
                         ▼
                 Supabase PostgreSQL

        Identity: Supabase Auth (separate from the data store)
```

The Flutter app authenticates directly against Supabase Auth. Supabase issues
an access token (JWT). The app then presents that token to FastAPI on every
protected request.

The web administration dashboard will be another client of the same FastAPI
API. It is not implemented yet.

## Authentication

```text
Flutter
  │  signInWithPassword (Supabase SDK)
  ▼
Supabase Auth
  │  access token (JWT)
  ▼
FastAPI
  │  Authorization: Bearer <token>
  ▼
verify signature + expiry + audience
  ▼
user identity (auth user id) → user_profiles row → school_memberships → role
```

### JWT verification approach

`backend/src/backend/core/security.py` implements `get_current_user()`:

1. Reads the bearer token via `HTTPBearer`.
2. Decodes it with `python-jose` using `SUPABASE_JWT_SECRET` (HS256), verifying
   signature, expiry and audience.
3. Extracts the subject claim (`sub`) as the authenticated identity.
4. Rejects missing, malformed, expired or wrongly-signed tokens with `401`.
5. Loads the matching `user_profiles` row and exposes it to the endpoint.

Passwords are never handled by FastAPI and never stored in the database.

The `SUPABASE_SERVICE_ROLE_KEY` is **not** used for user authorization. It is an
administrative credential and must not ship in the mobile app.

### Authentication vs authorization

These are separate concerns:

- **Authentication** — `get_current_user()` answers "who is calling?".
- **Authorization** — `require_school_admin()` and `require_teacher_or_admin()`
  answer "may this identity perform this operation?".

Roles always come from `school_memberships` rows in the database. Roles,
`user_id` and `school_id` supplied by a client are never trusted.

## Multi-tenancy

```text
Authenticated User
        ↓
UserProfile (1)
        ↓
SchoolMembership (many)  ── role ──┐
        ↓                            │
School (many per user)              │
   ├── Classes                       │
   └── Students ────────────────────┘
```

A user may belong to several schools, so there is deliberately **no** global
`school_id` on the user.

> `school_id` is a tenant boundary and must be enforced server-side.

Every school-owned table carries `school_id`. Queries are always filtered by the
school ids the caller actually belongs to. When a caller requests a resource
belonging to another school, the API returns `404` rather than `403`, so that
the existence of another school's data is not disclosed.

Cross-school writes are also rejected: a student can never be attached to a
class that belongs to a different school.

## Database schema (Day 2)

```text
schools
  id            UUID PK
  name          VARCHAR(255) NOT NULL
  slug          VARCHAR(255) NOT NULL UNIQUE
  created_at    TIMESTAMP NOT NULL
  updated_at    TIMESTAMP NOT NULL

user_profiles
  id            UUID PK
  auth_user_id  VARCHAR(255) NOT NULL UNIQUE   -- Supabase Auth user id
  full_name     VARCHAR(255)
  email         VARCHAR(255)
  created_at    TIMESTAMP NOT NULL
  updated_at    TIMESTAMP NOT NULL

school_memberships
  id            UUID PK
  school_id     UUID FK -> schools.id        ON DELETE CASCADE
  user_id       UUID FK -> user_profiles.id  ON DELETE CASCADE
  role          ENUM(school_admin|teacher|parent) NOT NULL
  created_at    TIMESTAMP NOT NULL
  updated_at    TIMESTAMP NOT NULL
  UNIQUE (school_id, user_id)
  INDEX  (school_id)
  INDEX  (user_id)

classes
  id            UUID PK
  school_id     UUID FK -> schools.id        ON DELETE CASCADE
  name          VARCHAR(100) NOT NULL
  section       VARCHAR(50)
  academic_year VARCHAR(20)
  created_at    TIMESTAMP NOT NULL
  updated_at    TIMESTAMP NOT NULL
  UNIQUE (school_id, name, section, academic_year)
  INDEX  (school_id)

students
  id               UUID PK
  school_id        UUID FK -> schools.id   ON DELETE CASCADE
  class_id         UUID FK -> classes.id   ON DELETE RESTRICT
  admission_number VARCHAR(50) NOT NULL
  first_name       VARCHAR(100) NOT NULL
  last_name        VARCHAR(100) NOT NULL
  date_of_birth    DATE
  gender           VARCHAR(20)
  status           ENUM(active|inactive) NOT NULL DEFAULT 'active'
  created_at       TIMESTAMP NOT NULL
  updated_at       TIMESTAMP NOT NULL
  UNIQUE (school_id, admission_number)
  INDEX  (school_id)
  INDEX  (class_id)
```

Deleting a class that still has students is rejected with `409`, because
`students.class_id` uses `ON DELETE RESTRICT`.

Student records are deliberately minimal. No national ID, home address, medical
records or other sensitive data is stored.

## Roles

| Role | Classes | Students | School setup |
| --- | --- | --- | --- |
| `school_admin` | create, read, update, delete | create, read, update, deactivate | create schools |
| `teacher` | read | read | no |
| `parent` | no | no | no |

The user who creates a school becomes its first `school_admin`. Roles are
assigned server-side only.

## Flutter application structure

```text
mobile/lib/
├── main.dart
├── app.dart
├── core/
│   ├── config/app_config.dart        compile-time configuration
│   ├── network/
│   │   ├── api_client.dart           REST client, attaches bearer token
│   │   └── supabase_service.dart     Supabase client + session
│   └── theme/app_theme.dart
└── features/
    ├── auth/
    │   ├── auth_controller.dart      loading / unauthenticated / authenticated
    │   ├── auth_gate.dart            session routing
    │   └── login_screen.dart
    └── home/
        ├── home_screen.dart          role-aware home
        └── account_repository.dart   GET /api/v1/me
```

No state-management framework is used; a single `ValueNotifier` is sufficient for
the authentication stage.

## Planned (not implemented)

- QR code generation and scanning
- Attendance capture, check-in/check-out, late calculation
- Parent-child linking and notifications (WhatsApp / SMS / push)
- Attendance history and reports
- Payments and subscription plans
- School administration web dashboard
- Parent portal in the mobile application