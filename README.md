# SchoolPulse

A QR-based school attendance and parent notification platform.

## Current architecture

```text
Flutter mobile app  ──HTTPS/REST──>  FastAPI  ──>  Supabase PostgreSQL
```

Authentication is handled by **Supabase Auth**. FastAPI never stores passwords.

## Planned applications

- Flutter mobile app (teachers, school admins, parents)
- School administration web dashboard (not started)

## Day 7 — Production readiness and demo preparation

Day 7 makes the Day 1–6 system deployable and demonstrable. It adds **no new
product features and no new tables**; the work is configuration, hardening,
build tooling, demo data and documentation.

- **Production configuration audit**: every setting is environment-driven, no
  secret is committed, and `.gitignore` covers `.env*` with `.env.example`
  tracked as the template.
- **Fail-fast startup**: with `ENVIRONMENT=production` the API refuses to boot
  if `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET` or `CORS_ORIGINS` are
  missing, or if `DATABASE_URL` is not PostgreSQL. Only setting *names* are
  logged.
- **Health endpoint**: `GET /api/v1/health` stays lightweight and unauthenticated
  (a load balancer has no token), reports `version` and whether a database is
  configured, and never echoes a credential, path or stack trace.
- **Unhandled errors**: a global handler logs the traceback server-side and
  returns a generic 500 body, so an exception never reaches a phone.
- **Android release hardening**: the release manifest now sets
  `usesCleartextTraffic="false"` and `allowBackup="false"`; cleartext is
  re-enabled only in the debug and profile manifests for local development.
  Application ID moved off the `com.example` default.
- **Release APK built**: `build/app/outputs/flutter-apk/app-release.apk`
  (62.8 MB), min SDK 24, target SDK 36, permissions INTERNET and CAMERA only.
- **Demo dataset**: `backend/prepare_demo.py` creates a fictional school,
  class, student and parent accounts, and can reset the demo day. It is a local
  script, not an endpoint — there is no `/seed`, `/demo-login` or
  `/create-admin-without-auth` route anywhere in the API.
- **Network-failure handling** covered by
  `mobile/test/network_failure_test.dart`: a socket failure, a timeout, a
  `500` and a server stack trace all resolve to a readable sentence rather than
  raw error text.
- **Demonstration rehearsal**: `backend/tests/test_demo_journey.py` walks the
  exact Day 8 sequence, including the assertion that a third scan returns
  `ALREADY_RECORDED` and creates **no** duplicate notification.
- **Documentation**: see [`docs/day7-release.md`](docs/day7-release.md) for
  deployment, demo setup and the school demo checklist.

Full detail, deployment variables and the demo checklist:
[`docs/day7-release.md`](docs/day7-release.md).

## Current status

**Day 7 — Production readiness, Android build, demo preparation.**
**Day 6 — Mobile school management and parent attendance workflow.**

Day 6 connects the Days 2–5 APIs into usable mobile journeys. It adds no new
tables.

Admin and teacher experience:

- Class management: list, create and delete classes, with the Day 2 "class still
  has students" conflict explained in plain language instead of a status code
- Student management: paginated list with search and class filter, enrolment,
  and a student detail hub
- Student detail hub: QR status, attendance history, linked parents, link and
  unlink guardians, and soft deactivation
- QR management: preselects the student you arrived from, shows Active, Revoked
  or Not generated, and refreshes that state after issuing or revoking
- Role separation: teachers get view-only classes and students, with no QR
  issuing, no parent linking and no deactivation
- Staff home links to classes, students, QR codes, the scanner and the dashboard
- Multi-school staff can switch school, and the role that governs the available
  tools is the role held at the selected school

Parent experience:

- Each linked child shows today's attendance status on the parent home
- Child attendance has a Today section, kept separate from the history list
- Notifications show title, message, the school-local recorded time and a clear
  read/unread state

Two small backend additions supported the above:

- `GET /api/v1/parents` — a read-only directory of parent accounts that already
  exist at a school the administrator administers, with search
- `GET /api/v1/students/{id}/qr` now returns `last_revoked_at`, so "revoked" can
  be distinguished from "never issued"

Days 1–5 remain in place and unchanged in behaviour: Day 5 parent linking,
parent self-service and in-app notifications; Day 4 attendance dashboard and
history; Day 3 QR credentials and scanner; Day 2 auth, tenancy, classes and
students.

**Not implemented yet, by design:** WhatsApp, SMS, email and push delivery;
parent self-registration; notification queues, workers or retries; realtime or
polling updates; absence/late/fee notifications; reports and exports; the admin
web dashboard; AI; face recognition; payments and billing.

## Day 6 mobile workflow

```text
School admin            Teacher              Parent
-----------            --------              ------
Classes  --------+
Students ---------+-> Student QR ------> Scan ----+-> attendance_records
  |                |                    |           |
  |                +-> Classes (view)    +-----------+-> notifications
  +-> Student detail                          |             |
        |                                     +-> Dashboard  +-> Inbox
        +-> QR codes (issue/revoke)                           |
        +-> Linked parents  <--+                              +-> Today status
        +-> Attendance history |
        +-> Deactivate student +--> parent home --> child attendance --> Today
```

## Day 6 API

Day 6 reuses the existing endpoints and adds two changes:

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/parents?school_id=&search=` | school admin | Read-only directory of existing parent accounts at one administered school |
| `GET` | `/api/v1/students/{id}/qr` | school admin | Now also returns `last_revoked_at` |

`GET /api/v1/me/students` now returns `today_status` and `today_status_date`
per child, and `/api/v1/me/notifications` returns a school-local
`occurred_time`. Both are resolved on the server so the app never converts a
timestamp using the phone's own timezone.

The directory is deliberately read-only: SchoolPulse has no public parent
registration, so an administrator can only link an account that already exists.
It accepts `school_id` for clarity and search, but authorization is always
decided from the caller's memberships, never from that parameter.

## Day 5 data model

```text
student_parent_links        notifications
  id                           id
  school_id     -> schools     school_id     -> schools
  student_id    -> students    parent_user_id -> user_profiles
  parent_user_id-> user_profiles student_id  -> students
  created_at                   attendance_id -> attendance_records (nullable)
  updated_at                   type          arrival | departure
  UNIQUE(student_id,           status        queued | sent | failed
         parent_user_id)       title, message
                               occurred_at   the attendance event time
  indexes: school_id,          read_at       NULL until opened
            student_id,        created_at
            parent_user_id     UNIQUE(parent_user_id, attendance_id, type)
                               indexes: parent_user_id, student_id, school_id,
                                        created_at, status
```

The unique constraint on `(parent_user_id, attendance_id, type)` is what makes a
repeated scan harmless: at most one notice per parent, per attendance record, per
notice type.

`occurred_at` is the time of the attendance event and is what the inbox is
ordered by, so the list stays in step with the day's arrival and departure times
regardless of write latency. `created_at` remains the row write time.

`status = sent` means **the notice was created in SchoolPulse and is visible
in-app**. It does not claim that WhatsApp, SMS or push delivered anything.

## Day 5 scan to notification flow

```text
POST /api/v1/attendance/scan
  -> validate credential, school, active student
  -> record arrival or departure (Day 3)
  -> notify_attendance_event() in the SAME transaction
       -> linked parents for that student and school
       -> skip any parent who already has this notice
       -> INSERT notification (queued)
       -> provider.deliver()  ->  sent
                                on failure -> failed, attendance still commits
  -> commit once
```

Rules this implements:

- `ARRIVAL_RECORDED` produces one arrival notice per linked parent.
- `DEPARTURE_RECORDED` produces one departure notice per linked parent.
- `ALREADY_RECORDED` produces nothing.
- A student with no linked parent still gets attendance recorded, with no error.
- A provider failure is caught per notice, recorded as `failed`, and the
  attendance record is still committed. A notice is never silently dropped.
- The scanner's request and response are unchanged.

Notification messages are built on the server from the stored timestamp and
rendered in `School.timezone`, for example
`Ayesha Khan arrived at Demo School at 8:04 AM.` Child attendance carries the
same rendering in `arrival_time` / `departure_time`. The Flutter app never
recomputes a scan time from the device clock; the UTC `arrival_at` /
`departure_at` values are returned for accuracy but are not displayed.

Removing a parent link stops future access immediately but keeps notifications
already delivered, as an audit trail. Attendance records are never touched.

## Day 5 API

```text
POST   /api/v1/students/{student_id}/parents                link a parent (school_admin)
GET    /api/v1/students/{student_id}/parents                list guardians (school_admin)
DELETE /api/v1/students/{student_id}/parents/{user_id}      unlink (school_admin)

GET    /api/v1/me/students                                  my children
GET    /api/v1/me/students/{student_id}/attendance          my child's attendance
GET    /api/v1/me/notifications                             my notifications
GET    /api/v1/me/notifications/unread-count                badge count
PATCH  /api/v1/me/notifications/{id}/read                   mark one read
```

Query parameters:

| Route | Parameters |
| --- | --- |
| `/me/students` | `school_id` |
| `/me/students/{id}/attendance` | `start_date`, `end_date` |
| `/me/notifications` | `school_id`, `unread_only`, `limit`, `offset` |
| `/me/notifications/unread-count` | `school_id` |

The only write a parent can perform is marking their own notification read. There
is no parent route that creates, edits or deletes attendance.

## Day 5 authorization and privacy

Every parent route resolves identity from the verified JWT, never from a request
body or path value:

```text
JWT -> UserProfile -> SchoolMembership(role=parent)
    -> student_parent_links -> Student
```

- Teachers and school admins receive `403` from every `/me` parent route.
- An unlinked student, a student at another school and a nonexistent id are all
  `404`, so ids cannot be probed to discover which students exist.
- A duplicate link is `409`.
- A profile with no `parent` membership in the student's school cannot be linked
  (`400`), so a teacher account cannot be turned into a guardian account.
- An admin of another school receives `404` when linking that school's students.
- Parent responses carry no `token_hash`, `credential`, `scanned_by`, date of
  birth, gender or admission number, and never expose which staff member
  scanned.

Parent accounts already exist as Supabase users with a `parent` membership.
There is no parent registration, invitation or password reset in Day 5.

## Flutter parent experience

- A parent-only account lands on a children list; a user with any staff role
  keeps the staff home.
- Parent screens contain no scanner, no QR management and no staff dashboard.
- Children list shows each child's name, class and school.
- Child attendance shows a summary plus one row per day with the derived status
  and the arrival/departure times.
- Notification inbox lists notices newest first, marks them read on tap, and
  filters to unread only.
- The unread badge is refreshed on open, on pull-to-refresh and on return from
  the inbox. There is no polling, streaming or push subscription.
- Every list has explicit loading, error (with retry) and empty states.

## Day 4 attendance status rules

Status is derived at read time from the timestamps Day 3 already stores, so the
same data can never disagree with itself.

| `arrival_at` | `departure_at` | Status |
| --- | --- | --- |
| `null` | `null` | `absent` (no row exists) |
| set | `null` | `present` |
| set | set | `completed` |

Absent + present + completed always equals the student total. The SQL predicates
that count and filter these buckets are held next to the Python derivation so
the two cannot drift apart.

Only **active** students are counted, because an inactive student cannot be
scanned and would otherwise be reported as permanently absent.

## Attendance API

```text
POST   /api/v1/students/{student_id}/qr    generate or regenerate (school_admin)
GET    /api/v1/students/{student_id}/qr    credential status, no secret
DELETE /api/v1/students/{student_id}/qr    revoke active credential
POST   /api/v1/attendance/scan              record arrival/departure
GET    /api/v1/attendance/summary           absent/present/completed for local today
GET    /api/v1/attendance/today             paginated student list with status
GET    /api/v1/attendance/history           one student's days over a range
GET    /api/v1/attendance/classes           classes available as a filter
GET    /api/v1/students/{student_id}/attendance   detail with summary counts
```

Every Day 4 route is a GET. Attendance is written only by the scanner, so there
is no endpoint to edit or delete a record.

Day 4 query parameters:

| Route | Parameters |
| --- | --- |
| `/attendance/summary` | `school_id`, `class_id` |
| `/attendance/today` | `class_id`, `status`, `search`, `page`, `page_size`, `school_id` |
| `/attendance/history` | `student_id`, `start_date`, `end_date`, `page`, `page_size`, `school_id` |
| `/students/{id}/attendance` | `start_date`, `end_date`, `page`, `page_size`, `school_id` |

The dashboard never accepts a date: the server resolves the school's local today
through `School.timezone`, so a client in another timezone cannot ask for "its"
today. History ranges default to the last 7 school days, must be supplied as a
pair, and are capped at 90 days (`422` otherwise).

The plaintext credential is returned exactly once, at generation. It is never
logged, never persisted on the device, and cannot be recovered later — a lost
code must be regenerated.

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

### Camera permission

Attendance scanning needs the device camera. `android.permission.CAMERA` is
declared in the Android manifest and requested at runtime the first time the
scanner opens. The camera is declared `required="false"` so the app still
installs on devices without one.

## Day 6 verification status

Verified locally:

- `pytest` — 337 tests pass as of Day 7 (299 through Day 6: 281 from Day 5, plus
  11 admin-console security tests, 3 QR status tests and 4 parent status/time
  tests; Day 7 adds 13 production-config, 13 demo-safety and 12 demo-journey
  tests)
- `check_migration.py` — models and migration agree across all four Day 3–5
  tables and 19 indexes. Days 6 and 7 add no migration.
- `flutter analyze` — no issues
- `flutter test` — 161 tests pass as of Day 7 (120 through Day 5, 21 admin
  console, 9 parent Day 6 additions, 4 staff home, 7 Day 7 network-failure
  messages)

Day 6 Flutter tests cover class create/delete and the 409 explanation, student
search and filtering, the teacher read-only split, the three QR states, linked
parents, link/unlink with confirmation, the failed-link explanation, today's
status on the parent home, the child attendance Today section anchored to the
server's date, the notification recorded time, and staff school switching.

Not verified:

- Real Supabase sign-in and session persistence (no project credentials
  available in this environment)
- Applying migrations to a live Supabase database
- The full mobile workflow end to end against a live backend, for the same
  credential reason
- Camera scanning and the parent screens on a physical Android device or
  emulator
- PostgreSQL `SELECT ... FOR UPDATE` on the scanner, and the concurrent-scan
  savepoint path, which SQLite cannot exercise locally

## Day 6 deliberate limitations

- The parent directory is read-only by design. There is no parent registration,
  so an administrator links only accounts that already exist.
- `today_status` is computed server-side for all linked children in one query.
  A parent with many children still gets one request, not one per child.
- Student list search is debounced by 350 ms in the app, but not on the server.
- Class deletion is only possible while a class is empty; the server refuses with
  `409` and the app explains it rather than offering a forced delete.
- Deactivation is soft. A deactivated student keeps their attendance history and
  can no longer be scanned or counted in daily totals.
- Staff school switching is offered in the AppBar only when the account has more
  than one membership. A parent at several schools still picks one with
  `school_id`, which the parent home forwards.
- Notifications remain in-app only; Day 6 changes no delivery behaviour.

## Day 5 verification status

Verified locally at the end of Day 5:

- `pytest` — 281 tests pass (110 from Days 1–3, 50 dashboard, 45 history and
  detail, 6 Day 4 OpenAPI contract, 59 Day 5 behaviour, 13 Day 5 OpenAPI
  contract)
- Migration `0003_day5_parent_notifications` — offline PostgreSQL SQL renders in
  both directions, including dropping the two enum types on downgrade so a
  re-upgrade can succeed. Rendered with `alembic upgrade --sql` /
  `downgrade --sql`, not applied to a live database.
- `check_migration.py` — models and migration agree across all four Day 3–5
  tables and 19 indexes
- `flutter analyze` — no issues
- `flutter test` — 120 tests pass (92 from Days 1–4, 28 parent and notification)

Not verified:

- Real Supabase sign-in and session persistence (no project credentials
  available in this environment)
- Applying migration `0003` to a live Supabase database
- The parent experience end to end against a live backend, for the same
  credential reason
- Camera scanning and the parent screens on a physical Android device or
  emulator
- PostgreSQL `SELECT ... FOR UPDATE` on the scanner, and the concurrent-scan
  savepoint path, which SQLite cannot exercise locally

## Day 5 deliberate limitations

- Notifications are in-app only. `status = sent` records that the notice exists
  in SchoolPulse, not that an external channel delivered it.
- There is no queue, worker, retry or outbox. Notices are written in the
  scanner's transaction.
- A parent at several schools picks one with `school_id`; there is no school
  switcher in the Flutter UI yet.
- The admin-side Flutter UI for linking a parent is not built. The endpoints are
  available and tested; the parent-side UI is the delivered surface.
- Child attendance is one unpaginated range per request, capped at 90 days by
  the shared server rule.

Both Day 5 limitations above about the parent-side UI and the school switcher
were addressed in Day 6; see the Day 6 sections above.

## Git

The repository is initialised with `main` as the default branch. Secrets are
excluded through `.gitignore`; only `.env.example` files are committed.