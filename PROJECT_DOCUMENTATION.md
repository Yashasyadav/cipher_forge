# CipherForge Project Documentation

## 1. Project Summary

CipherForge is a multi-service data sanitization platform with:

- A **Spring Boot backend** (`cipherforge-spring-backend`) for authentication, RBAC, job/certificate persistence, admin stats, and API aggregation.
- A **Python FastAPI wipe engine** (`wipe_engine_service`) that performs actual wipe operations, file/folder shredding, forensic verification, and certificate generation.
- An **Angular dashboard** (`cipherforge-dashboard`) for operators/admins.
- A **legacy desktop script** (`data_wipe.py`) that provides a standalone GUI for local secure delete + Android wipe.

The product goal is secure wiping (device/file/folder), progress tracking, and evidence generation (JSON/PDF certificates + verification URL/QR).

---

## 2. Repository Layout

Top-level relevant paths:

- `cipherforge-dashboard/` - Angular 20 frontend.
- `cipherforge-spring-backend/` - Java 17 Spring Boot backend.
- `wipe_engine_service/` - FastAPI wipe engine microservice.
- `certificates/` - generated certificate artifacts (JSON/PDF/QR).
- `start-system.bat` - convenience launcher for PostgreSQL + Python engine + backend + frontend.
- `run-python-engine.bat` - starts Python wipe engine module.
- `data_wipe.py` - standalone desktop app (CustomTkinter).
- `cipherforge/` - older/alternate Python service package (not the one started by `start-system.bat`).

---

## 3. Runtime Architecture

### 3.1 Standard startup path

`start-system.bat` starts (in this order):

1. PostgreSQL (tries known Windows service names on port `5432`)
2. Python engine (`python -m wipe_engine_service.main`) on port `8000`
3. Spring backend (`mvn spring-boot:run`) on port `8081` by default
4. Angular app (`ng serve`) on port `4300`

### 3.2 Service responsibilities

#### Angular (`4300`)

- Login and route protection.
- Device wipe UI, file/folder shred UI.
- Progress monitor (polling + websocket).
- Certificates page (download PDF/JSON, verification open).
- Admin stats with charts.

#### Spring backend (`8081`)

- JWT auth and role-based authorization.
- Persistence of users/devices/wipe jobs/certificates in PostgreSQL.
- Device/job orchestration using Python engine client.
- Scheduled sync of running jobs + certificate backfill.
- Certificate download and verification endpoints.
- WebSocket broadcast of job progress.

#### Python wipe engine (`8000`)

- Hardware detection (`/devices`, `/drives`).
- Device wipe execution (`/wipe` + `/wipe/status/{jobId}`).
- File wipe (`/wipe/file`) and folder wipe (`/wipe/folder`, async folder job endpoints).
- Safe filesystem browse endpoint for UI (`/filesystem`).
- Forensic verification and certificate generation (`/certificate/{jobId}` + `/verify/{certificateId}`).

---

## 4. End-to-End Workflows

## 4.1 Device wipe workflow

1. User logs in through Angular (`/auth/login`).
2. Angular calls backend `/devices` and `/wipe/methods`.
3. User starts wipe -> backend `POST /wipe/start`.
4. Backend `WipeJobService`:
   - Validates method mapping (NIST/DoD/Gutmann),
   - Ensures device exists/synced,
   - Calls Python engine `POST /wipe`,
   - Stores local `wipe_jobs` row.
5. Progress:
   - Backend polls Python engine on status endpoints (scheduled + explicit status requests),
   - Backend broadcasts updates on websocket (`/ws/progress`).
6. On completion:
   - Backend fetches Python certificate (`GET /certificate/{jobId}`),
   - Persists certificate in DB.
7. Certificate is available in Angular certificate page via backend list/download endpoints.

## 4.2 File/folder shred workflow

1. Angular loads logical drives and folder tree directly from Python engine.
2. For file shred:
   - Angular calls Python `POST /wipe/file` directly.
3. For folder shred:
   - Angular starts async folder job via Python `POST /wipe/folder/start`,
   - Polls Python `GET /wipe/folder/status/{jobId}`.
4. Local shred history is also stored in browser `localStorage` (`FileShredHistoryService`).

Note: file/folder shredding currently bypasses Spring backend persistence and RBAC enforcement.

## 4.3 Verification and evidence workflow

- Backend certificate download:
  - `GET /certificate/download/{jobId}` -> PDF
  - `GET /certificate/download-json/{jobId}` -> normalized JSON with `qrCode.verificationUrl`
- Public verification:
  - `GET /verify/{certificateId}` (JSON or HTML view)

Python engine also provides direct verification and certificate retrieval endpoints.

---

## 5. Backend API (Spring Boot)

Base URL: `http://localhost:8081`

Auth/public:

- `POST /auth/register` - create user (default role `OPERATOR`)
- `POST /auth/login` - returns JWT
- `GET /health` - health check
- `GET /verify/{certificateId}` - public verification (JSON/HTML)

Operator/Admin:

- `GET /devices`
- `POST /wipe/start`
- `GET /wipe/status/{jobId}`
- `GET /wipe/jobs`
- `GET /wipe/methods`

Admin only:

- `GET /certificates`
- `GET /certificate/download/{jobId}`
- `GET /certificate/download-json/{jobId}`
- `GET /admin/stats`

Security model (`SecurityConfig`):

- JWT bearer auth for protected endpoints.
- Role checks:
  - `ADMIN` for certificates/admin stats.
  - `ADMIN` or `OPERATOR` for wipe/device APIs.

---

## 6. Python Wipe Engine API (FastAPI)

Base URL: `http://localhost:8000`

- `GET /health`
- `GET /devices`
- `GET /drives`
- `GET /filesystem?path=<absolute_path>`
- `POST /wipe` (device wipe start)
- `GET /wipe/status/{jobId}`
- `POST /wipe/file`
- `POST /wipe/folder`
- `POST /wipe/folder/start`
- `GET /wipe/folder/status/{jobId}`
- `GET /certificate/{jobId}`
- `GET /verify/{certificateId}` (JSON/HTML)

Core engine behavior:

- Methods supported: `NIST`, `DoD`, `Gutmann`.
- `WipeExecutor` defaults to **dry run** unless `WIPE_ENGINE_DRY_RUN=false`.
- Certificates generated to `certificates/` with JSON + PDF (+ QR if `segno` available).
- Forensic verification tries `photorec` and `testdisk` if available.

---

## 7. Data Model (Spring/PostgreSQL)

Main tables/entities:

- `users`
  - `username`, `email`, `passwordHash`, `role`, `createdAt`
- `devices`
  - `engineDeviceName` (unique), type/size/serial, `lastSeenAt`
- `wipe_jobs`
  - UUID id, FK `device_id`, method/status/progress, `engineJobId` (unique), times, error
- `certificates`
  - UUID id, one-to-one FK `wipe_job_id`, engine cert id, device metadata, method, verification status, hashes, JSON/PDF paths, raw payload

Enums:

- Role: `ADMIN`, `OPERATOR`, `USER`
- Wipe status: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`
- Method type: `NIST`, `DOD`, `GUTMANN`

Seeding behavior (`StartupDataSeeder`):

- Always syncs default users:
  - `admin / admin12345`
  - `operator / operator12345`
- Optional sample data via `cipherforge.seed-sample-data=true`.

---

## 8. Frontend Behavior (Angular)

Routes:

- `/login`
- `/dashboard`
- `/wipe-control`
- `/progress-monitor`
- `/certificates` (ADMIN)
- `/admin` (ADMIN)

Key services:

- `AuthService`: JWT session in `localStorage`, login/logout, role checks.
- `ApiService`: backend and wipe-engine HTTP calls.
- `WipeJobTrackerService`: tracks remote job status in-memory.
- `ProgressWebSocketService`: connects to `/ws/progress` and merges live updates.
- `FileShredHistoryService`: local file/folder shred history and local evidence blobs.

`Wipe Control` supports two modes:

- `DEVICE_WIPE` (through backend -> persisted job lifecycle)
- `FILE_SHREDDER` (direct wipe engine file/folder operations)

---

## 9. Configuration and Environment

### 9.1 Spring (`application.yml`)

- DB:
  - `DB_URL` (default `jdbc:postgresql://localhost:5432/cipherforge`)
  - `DB_USERNAME` (default `postgres`)
  - `DB_PASSWORD` (default `postgres123`)
- Server:
  - `SERVER_PORT` (default `8081`)
- Python engine client:
  - `PYTHON_ENGINE_BASE_URL` (default `http://localhost:8000`)
  - `PYTHON_ENGINE_TIMEOUT` (seconds)
- Security:
  - `JWT_SECRET`
  - `JWT_VALIDITY_MINUTES`

### 9.2 Python engine

- `WIPE_ENGINE_HOST` (default `0.0.0.0`)
- `WIPE_ENGINE_PORT` (default `8000`)
- `LOG_LEVEL` / `WIPE_ENGINE_LOG_LEVEL`
- `CORS_ORIGINS`
- `WIPE_ENGINE_DRY_RUN` (default true)
- `WIPE_ENABLE_FREE_SPACE_CLEANUP` (default false)
- `CERTIFICATE_VERIFY_BASE_URL` (default `http://localhost:8080`)

### 9.3 Frontend

`src/environments/environment.ts`:

- `apiBaseUrl = http://localhost:8081`
- `wipeEngineBaseUrl = http://localhost:8000`

---

## 10. Important Operational Notes

1. Device wipe may be simulated by default.
`WipeExecutor` dry-run default is true; real overwrites require explicit config change.

2. Python engine startup can be duplicated.
`start-system.bat` starts engine, and backend `PythonEngineStarter` can also start it (hardcoded path `D:/SIH_2025-main`).

3. Hardcoded backend engine starter paths.
`PythonEngineStarter` is Windows-path specific and not environment-driven yet.

4. File/folder shredding is not persisted in backend DB.
Angular stores local history in browser storage; this is not centralized evidence.

5. WebSocket auth may need tightening/review.
Frontend websocket uses native `WebSocket` without auth header; backend protects `/ws/**` by role.

6. Verification base URL mismatch risk.
Python default `CERTIFICATE_VERIFY_BASE_URL` is `http://localhost:8080`, while backend default is `8081`.

---

## 11. Upgrade Roadmap (Recommended)

Priority upgrades for production readiness:

1. **Unify orchestration**
- Route all wipe actions (device/file/folder) through backend.
- Persist all jobs and certificates centrally.

2. **Harden auth/security**
- Resolve websocket authentication strategy (token in query/handshake interceptor or dedicated gateway).
- Remove default seeded passwords in non-dev environments.
- Restrict Python engine direct public exposure if backend is gateway.

3. **Make execution mode explicit**
- Set `WIPE_ENGINE_DRY_RUN=false` only in controlled envs.
- Expose dry-run state in API/UI to avoid ambiguous wipe results.

4. **Externalize all hardcoded paths**
- Replace hardcoded `D:/SIH_2025-main` in backend starter with config/env.

5. **Certificate trust model**
- Add digital signing with managed keys (instead of hash-only proof).
- Add immutable audit trail/event store.

6. **Data lifecycle and retention**
- Add cleanup/archive policy for old jobs/certificates.
- Add migration scripts and schema versioning strategy.

7. **Testing**
- Expand integration tests for file/folder APIs, RBAC, websocket flow, and failure paths.

---

## 12. Legacy Components

## 12.1 `data_wipe.py` (desktop app)

- CustomTkinter GUI for local secure deletion and Android ADB factory reset flow.
- Implements in-process overwrite methods, free-space wipe, trace cleanup, and PDF/JSON certificate output.
- Not integrated with the Angular/Spring runtime path.

## 12.2 `cipherforge/` Python package

- Older FastAPI service variant similar to wipe engine.
- Current launcher scripts and backend client target `wipe_engine_service`, not `cipherforge`.

---

## 13. Quick Local Run

From repository root:

1. Start all services:
   - `start-system.bat`
2. Open frontend:
   - `http://localhost:4300`
3. Default users:
   - `admin / admin12345`
   - `operator / operator12345`

Manual service checks:

- Python engine health: `http://localhost:8000/health`
- Spring health: `http://localhost:8081/health`

---

## 14. Source Map for Future Work

Backend core:

- `cipherforge-spring-backend/src/main/java/com/cipherforge/services/WipeJobService.java`
- `cipherforge-spring-backend/src/main/java/com/cipherforge/client/WipeEngineClient.java`
- `cipherforge-spring-backend/src/main/java/com/cipherforge/security/SecurityConfig.java`

Python engine core:

- `wipe_engine_service/main.py`
- `wipe_engine_service/wipe_manager.py`
- `wipe_engine_service/wipe_executor.py`
- `wipe_engine_service/file_wipe_executor.py`
- `wipe_engine_service/folder_wipe_manager.py`

Frontend core:

- `cipherforge-dashboard/src/app/services/api.service.ts`
- `cipherforge-dashboard/src/app/pages/wipe-control/wipe-control-page.component.ts`
- `cipherforge-dashboard/src/app/core/services/progress-websocket.service.ts`

Legacy desktop:

- `data_wipe.py`

