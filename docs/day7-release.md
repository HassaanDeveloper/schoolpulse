# Day 7: SchoolPulse release documentation

## 1. Current MVP status (Day 1–7)

| Day | Capability |
| --- | --- |
| 1 | Supabase Auth wired into Flutter, session restore, role-aware home |
| 2 | Schools, classes, students, school/role model |
| 3 | QR credential issue/regenerate/revoke, camera scanner, arrival/departure scan |
| 4 | Teacher attendance dashboard and per-student history, read-only reporting |
| 5 | Parent linking, parent self-service, in-app arrival/departure notifications |
| 6 | Admin school management UI, parent directory, today-status, multi-school staff home |
| 7 | Production configuration, Android release build, demo dataset, demo rehearsal |

Deliberately **not** built: WhatsApp/SMS/email/push, chat, attendance editing or
correction, exports, advanced analytics, payments, web dashboard, Docker,
Kubernetes, Redis/Celery/Kafka, WebSockets, RFID, face recognition, AI.

## 2. Architecture

```
Flutter (Android)
   │  HTTPS, Bearer access token
   ↓
FastAPI (Uvicorn)
   │  verifies Supabase JWT, enforces role + school tenancy
   ↓
Supabase PostgreSQL
```

The backend is the authorization authority. The app never decides who may see
what; it only renders what the API returns.

## 3. Core flow

```
real QR credential → real scanner → POST /attendance/scan
    → attendance_records row
    → notifications row for each linked parent
    → parent inbox + today status + child attendance
```

A scan returns exactly one of `ARRIVAL_RECORDED`, `DEPARTURE_RECORDED` or
`ALREADY_RECORDED`. The third scan of a completed day is refused and creates no
notification.

## 4. Backend deployment configuration

Required environment variables, **by name only** (values never in the repo):

| Name | Purpose |
| --- | --- |
| `ENVIRONMENT` | `production` enables startup validation |
| `DATABASE_URL` | Supabase **direct** connection, port 5432, `sslmode=require` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_JWT_SECRET` | Project JWT secret used to verify access tokens |
| `SUPABASE_JWT_AUDIENCE` | Defaults to `authenticated` |
| `CORS_ORIGINS` | Comma-separated exact origins |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` | Pool sizing |

Template: `backend/.env.production.example`.

**Use the direct connection, not the transaction pooler (port 6543).** The scan
endpoint uses `SELECT ... FOR UPDATE`, and the transaction pooler breaks the
prepared statements SQLAlchemy relies on.

Run:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Terminate TLS at the hosting provider's HTTPS proxy and forward to the process
over the private network. Health probe: `GET /api/v1/health`.

Startup behaviour:

- `ENVIRONMENT=production` **refuses to boot** if `DATABASE_URL`,
  `SUPABASE_URL`, `SUPABASE_JWT_SECRET` or `CORS_ORIGINS` are missing, or if
  `DATABASE_URL` is not a PostgreSQL URL. Only setting *names* are logged.
- `ENVIRONMENT=development` starts regardless, for local work.

## 5. Flutter production API configuration

Values are compiled in via `--dart-define`; nothing is hardcoded in Dart.

```bash
flutter build apk --release \
  --dart-define=API_BASE_URL=https://api.example.com \
  --dart-define=SUPABASE_URL=https://PROJECT_REF.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
```

`API_BASE_URL` must be `https://` for a release build: the release manifest sets
`usesCleartextTraffic="false"`, so a plain-HTTP URL will not connect. Debug and
profile manifests re-enable cleartext for local work against
`http://10.0.2.2:8000`.

Never pass `SUPABASE_JWT_SECRET` or `DATABASE_URL` to the app. The anon key is
public by design and is protected by Supabase row-level security; the service
role key is not used by this application at all.

## 6. Android build

```bash
flutter build apk --release
# -> build/app/outputs/flutter-apk/app-release.apk
```

Permissions requested: `INTERNET`, `CAMERA`. No location, contacts, microphone,
storage or Bluetooth.

Minimum SDK 24, target SDK 36. Application ID `com.schoolpulse.app`.

The demonstration APK is signed with the debug keystore so it can be
sideloaded. **Any store release must replace this with a private key supplied by
CI.** `mobile/android/gradle.properties` pins JDK 17 and a small heap because
Flutter's 8 GB default cannot be reserved on a low-memory machine; on a normal
developer or CI machine those overrides can be removed.

## 7. Demo setup

Fictional dataset, no real children's data:

| | |
| --- | --- |
| School | Karachi Model School (`Asia/Karachi`) |
| Class | Grade 5 - A |
| Student | Ali Khan, admission `SP-DEMO-001` |
| Accounts | `demo.admin@example.test`, `demo.teacher@example.test`, `demo.parent@example.test` |

```bash
cd backend
python prepare_demo.py --database-url sqlite:///./demo.db
```

Supabase accounts must be created in **Supabase Auth** first (the `auth` schema
is managed by Supabase and cannot be seeded by this application). Re-run with
`DEMO_ADMIN_AUTH_ID`, `DEMO_TEACHER_AUTH_ID`, `DEMO_PARENT_AUTH_ID` set, or
export them, to bind the profiles.

There is **no** `/seed`, `/demo-login` or `/create-admin-without-auth` route.
`prepare_demo.py` is a local script that refuses to touch a hosted database
without `--allow-remote-demo-db --confirm-demo-database <name>`, only writes
rows it can identify as demo rows, and never overwrites unrelated data.

### Demo reset

```bash
python prepare_demo.py --database-url sqlite:///./demo.db --reset
```

`--reset` deletes the demo student's attendance rows **and the notifications
created by those scans**, returning the day to "not yet scanned" so the
demonstration can be repeated without the parent seeing a second arrival.

### Demo QR

No QR is pre-generated by the script. Generate it in the app as the admin:
**Student detail → Generate QR**, then show it on a second phone or print it.
The demonstration must use a real credential from the real generation endpoint
so the real scanner and the real attendance endpoint are exercised.

## 8. School demo checklist

### Before leaving for school

- [ ] Backend reachable over HTTPS: `GET /api/v1/health` returns `"status":"ok"`
- [ ] Supabase project reachable; admin and parent credentials tested
- [ ] `prepare_demo.py --reset` run so the day starts clean
- [ ] Demo student Ali Khan / `SP-DEMO-001` present in Grade 5 - A
- [ ] Demo QR generated in the app and available to display or print
- [ ] APK installed on the staff phone; app launches
- [ ] Camera permission granted and preview visible
- [ ] Internet or mobile hotspot confirmed on **both** devices
- [ ] Charger/power bank packed
- [ ] Second device charged for the parent demonstration

### During the demonstration

1. Admin signs in, opens the school, the class, and the student
2. Show the student's QR (and its status)
3. Parent signs in on the second device, child visible
4. Teacher/admin scans → **Arrival recorded**
5. Parent opens the notification, shows the arrival time
6. Parent opens today's attendance → Present, with arrival time
7. Scan the same QR again → **Departure recorded**
8. Parent opens the second notification
9. Parent opens attendance → Completed, arrival and departure times
10. Scan a third time → **Already recorded**, no new notification

## 9. Limitations and unverified items

**Verified locally**

- Backend: 337 tests, including a full rehearsal of the demonstration journey
- Flutter: 161 tests, `flutter analyze` clean
- Migration chain `0001 → 0002 → 0003`; models and migrations agree (4 tables,
  19 indexes)
- `/api/v1/health` over real HTTP via Uvicorn
- Android release APK built and inspected (`usesCleartextTraffic=false`,
  `allowBackup=false`, only INTERNET and CAMERA)
- Repository scanned for secrets; release APK scanned for embedded secrets

**Not verified**

- Live Supabase migration and authentication — no project credentials available
- PostgreSQL `SELECT ... FOR UPDATE` concurrency — the suite runs on SQLite
- Deployed backend health — nothing is deployed
- Physical device install, camera permission and real QR scanning — no device
- Live multi-tenant isolation — covered by automated tests only

**Blocked**

- Nothing blocks the code. The APK build initially failed because the machine
  had no Android SDK and only 3.7 GB RAM; an SDK, JDK 17 and conservative
  Gradle settings resolved it.