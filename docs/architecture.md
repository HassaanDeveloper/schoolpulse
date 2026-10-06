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

| Role | Classes | Students | School setup | QR credentials | Scan attendance |
| --- | --- | --- | --- | --- | --- |
| `school_admin` | create, read, update, delete | create, read, update, deactivate | create schools | generate, revoke | yes |
| `teacher` | read | read | no | no | yes |
| `parent` | no | no | no | no | no |

The user who creates a school becomes its first `school_admin`. Roles are
assigned server-side only.

Parents are denied both QR management and scanning, in the UI and in the API.
A parent's own attendance is not modelled in this stage.

## QR credentials (Day 3)

A student's QR code carries **only an opaque token**. No student id, name,
admission number, school or role is encoded in it.

```text
generate (school admin)
  │
  ▼
secrets.token_urlsafe(32)        32 random bytes → 43 URL-safe characters
  │
  ├─► returned to the client ONCE, as "credential"
  │
  └─► SHA-256 hex digest stored as student_qr_credentials.token_hash
        (the plaintext is never written to the database or any log)
```

The token is unguessable, so possession of a QR code is the authentication
factor. A stolen QR code is therefore a real credential and is treated as
sensitive; regenerating a code revokes the previous one.

Because only the hash is stored, a lost code cannot be recovered. It must be
regenerated, which is why the app warns the admin at generation time.

### Lifecycle

```text
no credential  ──generate──►  active  ──generate──►  (revoke old) + active
                                │
                                ├──revoke──► revoked
                                │
                                └──scan──► arrival, then departure, then no-op
```

Historical rows are never deleted, so an audit trail of which credential was
active over time is preserved. `revoked_at IS NULL` marks the active one.

## Attendance recording (Day 3)

```text
scanner (teacher / school admin)
  │  POST /api/v1/attendance/scan  { "credential": "<opaque token>" }
  ▼
resolve active credential → student → school
  │  reject if inactive student, or school the scanner doesn't belong to
  ▼
attendance_date = today in the SCHOOL's timezone
  ▼
UNIQUE (student_id, attendance_date) row
  arrival_at NULL   → set arrival,     ARRIVAL_RECORDED
  departure_at NULL → set departure,   DEPARTURE_RECORDED
  both set          → change nothing,  ALREADY_RECORDED
```

The request body accepts nothing but the credential. A client cannot nominate a
student, a date or a school, so it cannot mark someone present who was not
scanned.

### Concurrency

Two guards prevent duplicate attendance for the same student on the same day:

1. `UNIQUE (student_id, attendance_date)` rejects a second insert at the
   database level.
2. The existing-row path takes a `SELECT ... FOR UPDATE` row lock on
   PostgreSQL, so simultaneous scanners are serialised and only the first
   observes `departure_at IS NULL`.

If two scanners race on the first scan, the loser's insert fails on the unique
constraint, it rolls back, re-reads the winning row, and applies the departure
transition — so exactly one arrival and one departure are recorded.

SQLite does not implement row locking, so guard 1 is what the test suite
exercises; guard 2 protects production PostgreSQL.

### Day boundaries

`attendance_date` is computed in `School.timezone` (default `Asia/Karachi`),
never in server time. A student arriving at 00:15 Karachi time is recorded
against the new local day even though it is still the previous day in UTC.
Timestamps themselves are stored timezone-aware in UTC.

## Database schema (Day 3 additions)

```text
schools  (Day 3 addition)
  timezone      VARCHAR(64) NOT NULL DEFAULT 'Asia/Karachi'

student_qr_credentials
  id               UUID PK
  student_id       UUID FK -> students.id        ON DELETE CASCADE
  school_id        UUID FK -> schools.id         ON DELETE CASCADE
  token_hash       VARCHAR(64) NOT NULL UNIQUE  -- SHA-256 hex, never plaintext
  created_at       TIMESTAMP NOT NULL
  revoked_at       TIMESTAMP NULL               -- NULL means active
  INDEX  (student_id)
  INDEX  (school_id)
  INDEX  (student_id, revoked_at)

attendance_records
  id                   UUID PK
  school_id            UUID FK -> schools.id         ON DELETE CASCADE
  student_id           UUID FK -> students.id        ON DELETE CASCADE
  attendance_date      DATE NOT NULL                 -- school-local date
  arrival_at           TIMESTAMP WITH TIME ZONE NULL
  arrival_scanned_by   UUID FK -> user_profiles.id   ON DELETE SET NULL
  departure_at         TIMESTAMP WITH TIME ZONE NULL
  departure_scanned_by UUID FK -> user_profiles.id   ON DELETE SET NULL
  created_at           TIMESTAMP NOT NULL
  updated_at           TIMESTAMP NOT NULL
  UNIQUE (student_id, attendance_date)
  INDEX  (school_id)
  INDEX  (school_id, attendance_date)
  INDEX  (student_id)
```

`arrival_scanned_by` / `departure_scanned_by` record *which staff member*
performed each scan, so a disputed attendance entry can be traced. They use
`ON DELETE SET NULL` to preserve the attendance record if a staff account is
removed.

`UNIQUE (student_id, attendance_date)` intentionally omits `school_id`: a
student belongs to exactly one school, so the student id already determines it,
and including it would weaken the guarantee for no benefit.

## Attendance reporting (Day 4)

Day 3 made attendance writable; Day 4 makes it readable. The reporting endpoints
add no columns and no status field — they derive everything from the timestamps
Day 3 already writes.

```text
dashboard (teacher / school admin)
  │  GET /api/v1/attendance/summary
  │  GET /api/v1/attendance/today
  ▼
resolve school from caller's memberships
  │  reject a school_id that is not one of them
  ▼
attendance_date = today in the SCHOOL's timezone
  ▼
Students LEFT JOIN AttendanceRecord ON (student_id, attendance_date)
  ▼
status derived per student → absent | present | completed
```

### Derived status

| `arrival_at` | `departure_at` | Status |
| --- | --- | --- |
| `null` | `null` | `absent` |
| set | `null` | `present` |
| set | set | `completed` |

A departure with no arrival is treated as `absent`, because the scanner only ever
writes a departure after an arrival.

The status is expressed twice: as Python (`derive_status`) for building
responses, and as SQL (`status_predicate`) for counting and filtering. Both live
in `backend/src/backend/services/`, and a comment on each points at the other, so
the counting rules and the rendered rules cannot drift apart. The SQL predicates
must be given the aliased `AttendanceRecord` used in the join — referencing the
base table there silently produces a cartesian product and wrong counts.

Absent + present + completed always equals the student total. Only active
students are counted; an inactive student cannot be scanned, so counting them
would report a permanently absent student who is actually withdrawn.

### History and gaps

`history_for_student` walks the **requested date range**, not the rows that
happen to exist, and looks each day up by date. A day on which nothing was
scanned is therefore reported as `absent` instead of being silently omitted,
which is the behaviour a teacher expects from a register. The response is ordered
newest first.

Ranges default to the last 7 school days, must be given as a `start_date` /
`end_date` pair, and are capped at 90 days. Violations return `422`.

### Summary query shape

The summary is one grouped aggregate over a `LEFT JOIN`, so its cost tracks the
number of students rather than the number of attendance rows:

```sql
SELECT COUNT(students.id),
       SUM(attendance_records.id IS NULL)                    AS absent,
       SUM(arrival_at IS NOT NULL AND departure_at IS NULL) AS present,
       SUM(arrival_at IS NOT NULL AND departure_at IS NOT NULL) AS completed
FROM students
LEFT JOIN attendance_records
  ON attendance_records.student_id = students.id
 AND attendance_records.attendance_date = :date
WHERE students.school_id = :school_id AND students.status = 'active'
```

### Tenant isolation

`resolve_staff_school` is the single gate: the school always comes from the
caller's `school_memberships`, and a client-supplied `school_id` is honoured
only if it matches one of them. If a user belongs to several schools the API asks
them to choose (`400`) rather than guessing. `resolve_student` and
`resolve_class` return `404` for another school's records, so the response never
confirms that a given student or class exists elsewhere.

Day 2's student and class routes now share these helpers instead of repeating
the membership checks, which keeps the tenant rules in one place.

## Database schema (Day 5 additions)

Migration `0003_day5_parent_notifications` adds two tables and two PostgreSQL
enum types.

```text
student_parent_links                notifications
  id            PK                   id             PK
  school_id     FK schools           school_id      FK schools
  student_id    FK students          parent_user_id FK user_profiles
  parent_user_id FK user_profiles    student_id     FK students
  created_at                         attendance_id  FK attendance_records (null)
  updated_at                         type           notificationtypeenum
  UQ (student_id, parent_user_id)    status         notificationstatusenum
  IX school_id                      title, message
  IX student_id                     occurred_at, created_at, read_at
  IX parent_user_id                 UQ (parent_user_id, attendance_id, type)
                                     IX parent_user_id, student_id, school_id,
                                        created_at, status
```

Choices worth stating:

- **Enums, not free strings.** `notificationtypeenum` (`arrival`, `departure`)
  and `notificationstatusenum` (`queued`, `sent`, `failed`) match the pattern
  already used for `schoolrole` and `attendancestatus`, so an invalid value is
  rejected by the database as well as by the ORM.
- **The downgrade drops both enum types.** Postgres will not let you re-create a
  type that still exists, so leaving them behind would break a re-upgrade. Both
  directions were rendered as offline PostgreSQL SQL and checked by hand, and
  `check_migration.py` re-renders the upgrade on every run. Neither has been
  applied to a live database.
- **Composite unique, not two separate ones.** A guardian may hold several links
  at one school, and a student may have several guardians, so both indexes are
  composite with `school_id` first, matching the tenant-first access pattern.
- **Cascades follow the ownership direction.** Deleting a student, a profile or
  a school removes its links; deleting an `attendance_records` row removes the
  notices derived from it, because the notice has no meaning without the event.
  Deleting a *link* does not touch notifications.
- **`read_at IS NULL` is unread.** No separate boolean column to fall out of
  sync, and the unread index covers the exact inbox query.

## Parent access and notifications (Day 5)

### The authorization chain

A parent's authority is never derived from anything the client sends. It is a
chain of four server-side facts:

```text
verified JWT
  -> UserProfile                        (auth_user_id from claims["sub"])
  -> SchoolMembership(role=parent)      (at least one)
  -> student_parent_links               (granted by a school admin)
  -> Student                            (in the link's school)
```

`require_parent` is a separate dependency from `require_school_admin` and
`require_teacher_or_admin`. The parent routes sit under `/me`, which every
authenticated account can read, so the role has to be re-checked there;
otherwise a teacher would silently receive empty parent data instead of a `403`.

Two helper pairs keep this in one place:

- `resolve_linked_student` returns `404` unless a link exists for *this* parent
  and *this* student. Unlinked students, other schools' students and
  nonexistent ids are indistinguishable, so the route cannot be used to probe
  which students exist.
- `linked_students` joins from the link table outwards, so a student outside the
  caller's school can never appear even if a link were ever written wrongly.

The admin side resolves the school *from the student* rather than from a
request field (`resolve_admin_school_for_student`), which answers the
multi-school case without the client guessing a `school_id`, and lets a
cross-tenant admin be answered with `404` rather than `403`.

### Scan to notification

```text
POST /api/v1/attendance/scan
  validate credential -> school -> active student
  attendance_date = school_local_date(school)
  |
  +-- no row yet  -> create record, arrival = now
  |                  notify(arrival)  -> commit
  +-- row, no departure -> set departure
  |                  notify(departure) -> commit
  +-- row complete -> ALREADY_RECORDED, no notification
```

`notify_attendance_event` runs inside the scan's own transaction, between the
attendance flush and the commit. So attendance and its notices are one atomic
unit rather than two writes that can disagree.

Failure handling is deliberately asymmetric:

| Failure | Result |
| --- | --- |
| Student has no linked parent | No notices, attendance commits normally |
| Notice already exists for this parent/event/type | Skipped, count unchanged |
| Provider raises | That notice is recorded `failed`, attendance still commits |
| Attendance `IntegrityError` (concurrent scan) | Existing row reloaded, `409` if absent |

The provider call is wrapped per notice rather than per request, so one broken
channel cannot cost a family its attendance record, and the error is logged and
recorded rather than swallowed — a `failed` notice is still delivered to the
inbox and still counts as unread.

A `SAVEPOINT` (`db.begin_nested()`) wraps each notice insert, so the unique
constraint firing from a concurrent scan rolls back only that insert and leaves
the attendance write intact.

### Idempotency

`UNIQUE (parent_user_id, attendance_id, type)` is the real guarantee. The
service also checks for an existing notice first, which keeps the common
repeat-scan case cheap and avoids relying on an exception for normal operation.

`ALREADY_RECORDED` is a no-op by design: both events for the day already
happened, so there is nothing new to tell anyone.

### Why `occurred_at` exists

`created_at` is when the row was written; `occurred_at` is when the attendance
event happened. The inbox is ordered by `occurred_at` so the list follows the
day's actual sequence rather than write latency. It also lets Flutter show a
real timestamp instead of parsing the human-readable `message`.

### Message construction

Messages are built server-side and formatted in `School.timezone`:

```text
Ayesha Khan arrived at Demo School at 8:04 AM.
Ayesha Khan departed Demo School at 4:30 PM.
```

The hour is rendered 12-hour without a leading zero, and midnight/noon are
handled explicitly. SQLite returns naive datetimes, so `_as_utc` treats a naive
value as UTC rather than shifting the message. The client never recomputes the
scan time.

Only the child's name, the school name and the time appear. No classmate, no
staff identity, no QR or token material.

### Provider abstraction

`NotificationProvider` is a plain class, not a dataclass — a dataclass base would
generate an `__init__` that subclasses inherit, silently shadowing each
subclass's own `name`.

`InAppNotificationProvider` marks a notice `sent`, which means "created in
SchoolPulse and visible in-app". `sent` is deliberately not a claim about
WhatsApp, SMS or push; those arrive as additional providers implementing the same
`deliver` method, and the status vocabulary already has room for them.

Day 5 deliberately ships no queue, worker, retry or outbox. Notices are written
in the scanner's transaction, which is the honest choice while delivery is a
local database insert.

### Data minimization

Parent-facing schemas omit `scanned_by`, `token_hash`, `credential`, date of
birth, gender and admission number. The attendance response exposes exactly
`date`, `status`, `arrival_at`, `departure_at`, `arrival_time` and
`departure_time`; the notification response exposes exactly `id`, `type`,
`title`, `message`, `status`, `occurred_at`, `occurred_time`, `read_at` and
`created_at`; the parent children response exposes exactly `student_id`,
`first_name`, `last_name`, `class_name`, `section`, `school_id`, `school_name`,
`school_timezone`, `today_status` and `today_status_date`.

Each of those field sets is asserted field-by-field in the tests, so a new field
cannot appear in a parent payload without a deliberate change to an allow-list.

`arrival_time` / `departure_time` are the same instant rendered by the server in
`School.timezone`. The raw `*_at` fields stay UTC and exact; the `*_time` fields
exist so the Flutter parent screens never convert an instant with the phone's
timezone and show a family a time the school did not record. `occurred_time` and
`today_status_date` follow the same rule for notifications and the children list.

Unlinking a parent deletes only the link. Notifications already delivered stay as
an audit trail, and attendance records are never modified by any Day 5 route.

## School administration endpoints (Day 6)

Day 6 reuses the Day 2–3 endpoints for classes, students and QR credentials. Two
small additions were needed.

### `GET /api/v1/parents`

A read-only directory of parent accounts, for linking an existing guardian.

- Requires `school_admin`. A teacher or parent gets `403` even though the route
  reveals nothing sensitive; the response exists only to serve the admin UI.
- `school_id` is optional and is validated against the caller's own admin
  memberships by `resolve_admin_school`. It scopes the result but never grants
  access: a multi-school admin with no matching membership gets `400`, and a
  single-school admin who names a different school gets `403`.
- `search` is a case-insensitive substring match over name and email, applied in
  SQL. The response exposes only `user_id`, `full_name` and `email`.
- There is no `POST`. SchoolPulse has no public parent registration, so this
  surface cannot mint an account, and a test asserts the route rejects writes.

The alternative was one request per candidate parent in the Flutter link sheet.
A read-only listing keeps the endpoint count at one and keeps the search server
side, which matters once a school has more parents than fit on a phone screen.

### `last_revoked_at` on `GET /api/v1/students/{id}/qr`

The existing response carried `has_active_credential`. That boolean cannot
distinguish "this student had a code and it was revoked" from "this student never
had a code", and the two need different wording: one is a security event, the
other is a first-time setup step.

Rather than add a table, the status route now also reports the most recent
revocation. The credential rows already existed with a `revoked_at` column, so no
migration was required and the client derives the three states:

```text
has_active_credential = true   -> Active
has_active_credential = false, last_revoked_at != null -> Revoked
has_active_credential = false, last_revoked_at == null -> Not generated
```

Only the three states and the timestamps are returned. The credential itself is
still issued exactly once, at generation time, and the response never carries a
token hash.

### `today_status` on `GET /api/v1/me/students`

Each linked child now carries the derived status for the school's local today.

The status is resolved in one query for all children rather than one request per
child, because this is the parent home's first screen and an N+1 there would be
felt on every app open. "Today" is computed per school from
`School.timezone`, so a parent whose children attend schools in different
timezones gets each child's own local day instead of one global date.

A day with no attendance row is reported as `absent`, which is exactly what the
Day 4 attendance rules already mean by absent.

## Error disclosure

Unknown and revoked credentials return an identical `404`
(`"Invalid or inactive QR credential."`). If revoked codes returned a distinct
status, the API would become an oracle for testing whether a given code ever
existed.

A valid credential used at the wrong school returns `403`, which discloses
nothing an attacker holding the code does not already know.

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
    ├── attendance/                   (Day 3 write, Day 4 read)
    │   ├── attendance_repository.dart       POST /api/v1/attendance/scan
    │   ├── attendance_scanner_screen.dart   mobile_scanner camera view
    │   ├── qr_credential_screen.dart        admin: generate / revoke QR
    │   ├── qr_repository.dart               students + credential endpoints
    │   ├── attendance_report_repository.dart  read models + report endpoints
    │   ├── attendance_dashboard_screen.dart   summary, filters, today's list
    │   └── student_attendance_screen.dart      one student's history
    ├── parent/                       (Day 5)
    │   ├── parent_repository.dart       /me/students + child attendance
    │   ├── parent_home_screen.dart      children list, today status, badge
    │   └── child_attendance_screen.dart  today section, history, summary
    ├── notifications/                (Day 5)
    │   ├── notification_repository.dart  /me/notifications + read state
    │   └── notifications_screen.dart    inbox, unread filter, mark read
    ├── classes/                      (Day 6)
    │   └── class_list_screen.dart       list, create, delete + 409 wording
    ├── students/                     (Day 6)
    │   ├── students_repository.dart      class/student models + endpoints
    │   ├── student_list_screen.dart      search, class filter, paging, enrol
    │   └── student_detail_screen.dart    QR, parents, attendance, deactivate
    ├── parents/                      (Day 6)
    │   ├── parents_admin_repository.dart  /parents directory + link routes
    │   └── parent_link_sheet.dart         searchable link/unlink sheet
    └── home/
        ├── home_screen.dart          role-aware home, school switcher
        └── account_repository.dart   GET /api/v1/me
```

`core/` gained two shared pieces in Day 6: `ApiClient.getList`, because the
classes and parent-link endpoints answer with a bare JSON array rather than the
paginated object the student endpoint returns, and
`core/widgets/state_views.dart`, holding the loading, error and empty widgets
plus `describeError`, so every new screen phrases an API failure the same way.

No state-management framework is used; a single `ValueNotifier` is sufficient for
the authentication stage. The Day 4, Day 5 and Day 6 screens are
`StatefulWidget`s holding their own request state and take an injectable
repository, so widget tests never touch HTTP.

### Day 3 client behaviour

- The scanner pauses while a scan request is in flight, so a code held in front
  of the camera cannot be submitted twice, then resumes.
- The issued credential is held in widget state only. It is not written to disk
  and not logged, matching the server's one-time disclosure.
- Regeneration and revocation both require an explicit confirmation dialog.
- Home entries are role-gated: scanning appears for teachers and admins, QR
  management only for school admins.

### Day 4 client behaviour

- The dashboard sends no date. It renders the date the server resolved for the
  school's timezone, so a teacher in another timezone still sees the school's
  day.
- Status is rendered from the server's value and never recomputed in Dart; an
  unrecognised value degrades to an "unknown" badge instead of throwing.
- Search is debounced (350 ms) and every filter change returns to page 1.
- Refreshing is explicit: a toolbar action and pull-to-refresh, with no polling.
- Navigating into a student is gated by the same role check that reveals the
  dashboard on the home screen; the server enforces it again regardless.
- The history screen defaults to 7 days, offers 30-day and custom presets, and
  refuses a range longer than the server's 90-day limit before sending it.

### Day 5 client behaviour

- A parent-only account is routed to `ParentHomeScreen`; an account with any
  staff role keeps the staff home. The check is "has staff roles", not "is not
  a parent", so a teacher who is also a guardian is not locked out of the app.
- The parent home fetches children and the unread count in parallel, so a slow
  notification endpoint cannot delay the children list.
- The unread badge is refreshed on open, on pull-to-refresh and when the inbox
  is popped. There is no polling, no timer and no stream subscription.
- Tapping a notice marks it read and closes the dialog; the badge and the
  unread filter both recompute from the response rather than guessing.
- Notifications are rendered with the server's `message` and `title`. The app
  never recomputes the scan time from a device clock or re-formats it into the
  phone's timezone, because the server already rendered it in the school's.
- Child attendance renders the server's `arrival_time` / `departure_time`
  strings for the same reason. The UTC `arrival_at` / `departure_at` fields are
  parsed but not displayed.
- A `failed` notice is still listed, labelled, and still counted as unread, so a
  family can see that an event happened even when a provider failed.
- Badge text caps at `99+` rather than widening the app bar.
- Child attendance reuses the server's status value and its default 7-day /
  90-day-maximum range rules; the custom range picker refuses to send a longer
  range.
- Parent screens expose no scanner, no QR management and no staff dashboard, and
  the server refuses those routes for a parent role regardless of what the app
  shows.
- Parent data is not cached on disk; it lives in widget state for the session,
  matching how the QR credential is handled on Day 3.

### Day 6 client behaviour

- The staff home resolves the membership it is showing rather than assuming the
  first one. When an account belongs to several schools the AppBar offers a
  switcher, and the available tools follow the role held at the selected school.
  An admin at one school and a teacher at another therefore sees teacher tools
  while the second school is selected, which is what the server would allow.
- Teachers open classes and students with `canManage: false`. That flag hides
  create and delete controls and, on the student detail screen, also skips the
  parent-link request entirely rather than firing a call that would be refused.
- The student detail screen loads the QR status and the linked parents in
  parallel, so a slow parent lookup cannot delay the QR status.
- `StudentDetailScreen` owns its own `late Student _student` state so a
  deactivation can update the screen without a refetch of the whole record.
- The link sheet filters out parents who are already linked before rendering, so
  an administrator cannot create a duplicate link from the UI, and it stays open
  with an explanation if the link call fails.
- "Link a parent" stays enabled once a parent exists and reads "Link another
  parent": a student may have several guardians.
- QR status is refreshed after issuing or revoking, so a screen opened from the
  student detail never shows a stale Active state next to a revoked code.
- The child attendance "Today" section is anchored to the server's `end_date`,
  not to `DateTime.now()`. The server chooses the school-local range, so a phone
  in another timezone still sees the school's day, and the record for that date is
  lifted out of the history list instead of appearing in both.
- The parent home shows `today_status` as plain language and stays silent when the
  field is absent, rather than claiming a status it was not told.
- Notifications show the server's `occurred_time` alongside the type, so a parent
  sees when the event was recorded without the app converting an instant.
- Shared `LoadingView`, `ErrorView`, `EmptyView` and `describeError` widgets are
  used by the Day 6 screens, which is why a `403` reads as "You do not have
  permission to do this." instead of echoing the server's detail.
- Every Day 6 screen body is a `ListView`, so pull-to-refresh keeps working even
  in the loading and empty states.

## Day 7 production readiness

Day 7 changed no domain model. Its architectural decisions are about how the
process is configured and what it reveals when something goes wrong.

### Configuration is entirely environment-driven

`Settings` (Pydantic) reads every value from the environment, with no fallback
that would let a production process silently run on a development default. Three
findings from the audit drove the change:

1. `ENVIRONMENT` was already defined but never read, so
   `ENVIRONMENT=production` had no effect at all. It now gates a startup
   validation performed in the FastAPI lifespan hook.
2. A missing `DATABASE_URL` used to surface as a `500` on the first real request,
   once a user was already on screen. It now aborts during startup.
3. The connection pool was left at SQLAlchemy's default (5 + 10 overflow), which
   is easy to exceed against a Supabase project's connection cap once more than
   one worker is running. Pool sizing is now explicit configuration.

`validate_production_configuration()` names missing settings and never their
values, so a deploy log cannot leak the secret it is complaining about. A test
pins that: the error text for a configuration containing
`super-secret-value` must not contain it.

SQLite remains the test driver and is rejected as a production database, which
a test also pins.

### The health endpoint is deliberately shallow

`GET /api/v1/health` performs no database query. An uptime monitor holding a
request open against an unreachable database is a worse failure than a stale
`database_configured` flag, and a health check that touches the database will
eventually be used as a connection-pool drain. It is unauthenticated because a
load balancer cannot present a Supabase token; the response therefore exposes
nothing but a status string, a version, the environment name, and whether a
database is configured. `test_health_is_lightweight_and_discloses_no_secrets`
fails if the response ever grows a credential, a path or a traceback.

### Errors terminate at the API boundary

An unhandled exception is logged with its traceback under
`schoolpulse.incident` and returned to the caller as a generic `500`. The app
receives `{"detail": "An internal error occurred."}`, which `describeError`
already renders as a sensible message, instead of a stack trace that would
disclose file paths and internals on a shared demo phone.

### Release builds refuse cleartext traffic

The Day 3 manifest set `usesCleartextTraffic="true"` so that a debug build could
reach `http://10.0.2.2:8000`. Left in place it would also have permitted
plaintext HTTP in a release APK talking to a production backend. Cleartext is
now `false` in the release manifest and re-enabled through the debug and
profile manifest overlays, which is why local development still works unchanged.
`allowBackup` is disabled so app data is not copied to cloud backup.

The build pins JDK 17 and a small Gradle heap in `gradle.properties`. Flutter's
stock 8 GB default cannot be reserved on a low-memory build host and crashed the
daemon; these are host-specific overrides that a CI machine can drop.

### Demonstration tooling is a script, not a surface

`backend/prepare_demo.py` seeds a fictional school, class, student and three
accounts. It creates no HTTP route, which is asserted against the generated
OpenAPI schema: no path may contain `seed`, `demo`, `register`, `signup` or
similar. A second test sends an unauthenticated request to every mutating route
and fails if any answers below `400`, so adding an unguarded write endpoint is a
test failure rather than a review finding.

The script refuses a hosted PostgreSQL URL unless the operator also passes
`--allow-remote-demo-db` and spells the database name in
`--confirm-demo-database`, and it only ever writes rows it can positively
identify as demo rows.

### Demonstration reset is part of the design, not a bolt-on

The parent's notification count is a visible, cumulative fact. A rehearsal that
runs twice must not show a family three arrivals, so `--reset` deletes the demo
student's attendance rows and the notifications those scans produced. This is
why the reset is documented next to the demo setup rather than left to the
operator to improvise.

The full release and demo documentation is in
[`day7-release.md`](day7-release.md).

## Planned (not implemented)

- Late calculation and absence reports
- External notification channels (WhatsApp, SMS, email, push)
- Parent self-registration, invitations and password reset
- Notification queues, workers, retries and delivery webhooks
- Attendance exports (CSV / PDF) and printable reports
- Realtime attendance updates (websockets, push)
- Attendance analytics and trends
- Payments and subscription plans
- School administration web dashboard
- A school switcher for a parent with links at several schools