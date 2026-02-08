# Unplugd — Implementation Plan

## Strategic Decisions

Reassessment after Phases 0-4 established these foundational choices:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Content model | Private per-user libraries | Legally clean processing tool (same as lalal.ai, moises.ai). No shared catalog = no distribution liability. Dedup behind the scenes for compute savings. |
| Frontend | React/Next.js web app | Avoids App Store review risk around user-uploaded copyrighted audio. Broader accessibility, faster to ship. |
| Inference compute | Fargate SPOT | $0.013/song (Demucs + Whisper). SageMaker Async is 6-8x more expensive for sporadic usage due to idle timeout billing. |
| ML platform | SageMaker (training only) | Training pipeline, experiment tracking, model registry. ~$3-5/training run on Spot instances. Inference stays on Fargate. |
| ML architecture | Band-Split RNN (new) | Legacy U-Net (~6 dB SDR, magnitude-only) is outclassed. Modern architectures reach ~8-10 dB SDR. New model, not U-Net improvement. |
| Lyrics | Must-have for v1 | Synced lyrics are central to karaoke UX. Without them, it's just a stem splitter. |

---

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Project Scaffolding | **Done** |
| 1 | Storage, Auth & Data Layer | **Done** |
| 2 | Upload API | **Done** |
| 3 | WebSocket API | **Done** |
| 4 | Demucs Container (Fargate) | **Done** |
| 4.5 | Code Audit Refactoring | **Done** |
| 5 | Whisper Container (Fargate) | **Done** |
| 6 | Step Functions Orchestration | **Done** |
| 7 | Song Library API | **Done** |
| 7.5 | E2E Testing & Fixes | In Progress |
| 8 | Web Frontend (React/Next.js) | Pending |
| 9 | CI/CD | Pending |
| 10 | SageMaker Training Pipeline | Pending |
| 11 | Custom Model Integration | Pending |
| 12 | Monitoring, Hardening, Polish | Pending |

## Dependency Graph

```
Phase 0 (scaffolding)                     DONE
  |
  v
Phase 1 (storage + auth)                  DONE
  |
  +---> Phase 2 (upload API)           --+  DONE
  +---> Phase 3 (WebSocket)            --+  DONE
  +---> Phase 4 (Demucs)              --+  DONE
                                         |
                                         v
                                 Phase 4.5 (refactoring)  DONE
                                         |
                            +------------+------------+
                            |                         |
                            v                         v
                    Phase 5 (Whisper)  DONE   Phase 7 (Song Library API)  DONE
                            |                         |
                            v                         |
                    Phase 6 (Step Functions) <--------+  DONE
                            |
                            v
                    Phase 8 (Web Frontend) -------> Tangible demo
                            |
                            v
                    Phase 9 (CI/CD)
                            |
                            v
                    Phase 10 (SageMaker Training) --> Custom model
                            |
                            v
                    Phase 11 (Model Integration)
                            |
                            v
                    Phase 12 (Monitoring + Hardening)
```

## Template Architecture

Nested SAM stacks split by domain:

```
template.yaml                  # Root — orchestrates nested stacks
templates/
  storage.yaml                 # DynamoDB + S3                      (Phase 1) DONE
  auth.yaml                    # Cognito                           (Phase 1) DONE
  monitoring.yaml              # SQS DLQ + CloudWatch alarms       (Phase 1) DONE
  api.yaml                     # REST API Gateway + routes          (Phase 2) DONE
  websocket.yaml               # WebSocket API Gateway              (Phase 3) DONE
  vpc.yaml                     # VPC, subnets, IGW, SG              (Phase 4) DONE
  ecs.yaml                     # ECR + ECS Fargate tasks            (Phase 4-5) DONE
  orchestration.yaml           # Step Functions                     (Phase 6) DONE
```

---

## Phase 0: Project Scaffolding (DONE)

**Goal**: Set up SAM project structure, move legacy code.

**Deliverables**:
- `template.yaml` — SAM template skeleton with Parameters (Environment, AppName) and Globals
- `samconfig.toml` — Deploy config for dev/prod (us-east-1)
- `pyproject.toml` — uv + Python 3.12, dev deps (pytest, moto, ruff, mypy, mutagen, python-ulid)
- Directory structure: `functions/`, `containers/`, `layers/`, `statemachines/`, `tests/`, `events/`
- Legacy code moved to `_reference/`

---

## Phase 1: Storage, Auth & Data Layer (DONE)

**Goal**: Deploy all foundational AWS infrastructure and create shared Lambda utilities.

**AWS Resources** (11 total across 3 nested stacks):

| Stack | Resources |
|-------|-----------|
| `storage.yaml` | SongsTable (DynamoDB), ConnectionsTable (DynamoDB), OutputBucket (S3) |
| `template.yaml` (root) | UploadBucket (S3, 24h lifecycle) — moved from storage.yaml in Phase 2 |
| `auth.yaml` | CognitoUserPool, CognitoUserPoolClient |
| `monitoring.yaml` | DeadLetterQueue (SQS), DeadLetterQueueAlarm (CloudWatch) |

**Shared Utilities** (`functions/shared/`):
- `constants.py` — env var lookups, status values, upload constraints, stem names
- `response.py` — API Gateway response helpers (200, 201, 400, 404, 500)
- `error_handling.py` — exception hierarchy + `@handle_errors` decorator
- `dynamodb_utils.py` — CRUD for Songs + Connections tables
- `s3_utils.py` — presigned URLs (upload + download), delete ops

**Tests**: 25 unit tests (constants, response, error_handling, dynamodb_utils)

**Verification**: `sam validate` + `ruff check` + `pytest` all passing

---

## Phase 2: Upload API (DONE)

**Goal**: Implement file upload flow — presigned URL generation, S3 trigger, file validation.

**Files**:
- `functions/upload_request/handler.py` — `POST /songs/upload-url` → generates presigned S3 PUT URL + songId (ULID)
- `functions/process_upload/handler.py` — S3 event trigger → validates file (format, size, duration via mutagen) → updates DDB status (Step Functions stub for Phase 6)
- `templates/api.yaml` — REST API Gateway + Cognito authorizer + routes
- `layers/common/requirements.txt` — Layer deps: mutagen, python-ulid
- `events/upload_request.json`, `events/s3_upload.json` — SAM local test events
- `tests/unit/test_upload_request.py` (6 tests), `tests/unit/test_process_upload.py` (5 tests)
- `.pre-commit-config.yaml` — ruff lint, ruff format, SAM validate hooks

**API**: `POST /songs/upload-url` (Cognito-authorized) → `{uploadUrl, songId, expiresIn}`

**Architecture notes**:
- UploadBucket moved from `storage.yaml` to root `template.yaml` — SAM S3 event sources require the bucket in the same template
- S3→Lambda notification uses explicit `NotificationConfiguration` + `AWS::Lambda::Permission` (not SAM Events) to avoid circular dependency
- All UploadBucket references use `!Sub` (not `!Ref`) to prevent implicit CFN dependency cycles
- `CodeUri: functions/` with `Handler: upload_request/handler.lambda_handler` — so `from shared.xxx` resolves at runtime
- Layer requires `typing_extensions` (transitive dep of `python-ulid`)
- Mutagen `File()` wrapped in try/except — corrupt files with known extensions raise instead of returning `None`

**Dev tooling**:
- Pre-commit hooks: ruff lint (with auto-fix), ruff format check, SAM template validation
- `.gitignore` updated to exclude audio files (*.wav, *.mp3, *.m4a, *.flac)

**Tests**: 36 total (11 new + 25 existing)

**Verified on deployed dev stack**:
- `POST /songs/upload-url` → 201 with presigned URL
- Upload valid WAV → process_upload triggers → status=PROCESSING with metadata
- Upload fake audio → status=FAILED with error message
- Missing filename / invalid contentType / no auth → 400/401
- `sam validate --lint` + `ruff check` + `pytest` + `sam build` all passing

---

## Phase 3: WebSocket API (DONE)

**Goal**: Real-time progress push to connected clients.

**Handlers** (4 Lambdas in root `template.yaml`):
- `functions/ws_connect/handler.py` — `$connect`: validate Cognito JWT from `?token=` query param, store connection in ConnectionsTable
- `functions/ws_disconnect/handler.py` — `$disconnect`: delete connection from ConnectionsTable
- `functions/ws_default/handler.py` — `$default`: ping/pong
- `functions/send_progress/handler.py` — async Lambda invoke: query user's connections via GSI, push message via API Gateway Management API, cleanup stale connections (GoneException)

**Shared Utilities**:
- `functions/shared/jwt_utils.py` — `validate_cognito_token(token) -> claims | None`, JWKS cached in module-level var
- `functions/shared/websocket.py` — `ws_success()`, `ws_unauthorized()`, `ws_response()`, `ws_error()`, `send_to_connection()`
- `functions/shared/constants.py` — added `WEBSOCKET_API_ENDPOINT`

**SAM Template**: `templates/websocket.yaml` — API Gateway V2 (WEBSOCKET), 3 integrations, 3 routes, stage (AutoDeploy), 3 Lambda invoke permissions

**Architecture decisions**:
- JWT validated directly in `ws_connect` (no separate Lambda authorizer) — simpler, avoids extra cold start
- Auth on `$connect` only — once connected, messages are trusted
- `verify_aud=False` — skip audience validation, tighten in Phase 12
- `send_progress` is Lambda-invoke-only (not a WebSocket route) — called by Fargate/Step Functions
- No circular dependency: SendProgressFunction → WebSocketStack (for endpoint), WebSocketStack only takes 3 route handler ARNs

**Layer deps added**: `PyJWT>=2.8`, `cryptography>=42.0` in `layers/common/requirements.txt` + `uv add --dev`

**Tests**: 60 total (24 new across 6 files + 36 existing)
- `test_jwt_utils.py` (4) — real test JWTs via RSA keypair in `cognito_jwt_keys` conftest fixture
- `test_websocket.py` (6) — response helpers + mocked `apigatewaymanagementapi`
- `test_ws_connect.py` (5) — happy path, missing/invalid token, TTL, connectedAt
- `test_ws_disconnect.py` (2) — happy path, idempotent for nonexistent
- `test_ws_default.py` (3) — ping/pong, unknown action, empty body
- `test_send_progress.py` (4) — broadcast, warning on zero connections, stale cleanup, missing userId

**Messages** (server → client):
- `PROCESSING_STARTED`, `PROGRESS` (stage + percentage), `COMPLETED` (with URLs), `FAILED`

**Lessons learned**:
- **Mock patch location**: When a handler uses `from shared.x import func`, patch at the handler's module (`functions.handler_name.handler.func`), NOT at `shared.x.func`. The direct import creates a local binding that doesn't update when the source module is patched.
- **`PyJWK.from_json()`**: Expects a JSON string, not a dict. Use `json.dumps(jwk_dict)`.

**Test cleanup (CI/CD prep)**:
- Removed redundant `@mock_aws` decorators from 30 tests across 6 files — fixtures already provide mock context
- Standardized all handler test files to lazy imports (import inside test functions, not at module level)

**Verification**: `ruff check` + `ruff format --check` + `pytest` (60 passed) + `sam validate --lint` + `sam build` all passing

**Manual verification on deployed dev stack**:
- Token retrieval, WebSocket connect/disconnect, ping/pong, SendProgress delivery (all 4 message types), negative tests (no token → 401, invalid token → 401), CloudWatch warning log for zero connections — all passing

---

## Phase 4: Demucs Container (Fargate) (DONE)

**Goal**: Docker container that separates audio into 4 stems.

**Files**:
- `containers/demucs/Dockerfile` — Python 3.12 + CPU-only PyTorch + Demucs + ffmpeg, model pre-downloaded
- `containers/demucs/entrypoint.py` — S3 download → `htdemucs_ft` separation → upload 4 stem WAVs to S3
- `containers/shared/progress.py` — Fire-and-forget Lambda invoke helpers (shared by demucs + whisper)
- `templates/vpc.yaml` — Minimal VPC: 2 public subnets, IGW, egress-only SG (reused by Phase 6)
- `templates/ecs.yaml` — ECR repo, ECS Cluster (FARGATE_SPOT), DemucsTaskDefinition (4 vCPU / 16GB), IAM roles

**Architecture decisions**:
- VPC in separate `vpc.yaml` (not inline in ecs.yaml) — reusable by orchestration.yaml in Phase 6
- FARGATE_SPOT only, CPU Fargate (no GPU). GPU deferred to Phase 12+
- Container does NOT send FAILED progress — just `sys.exit(1)`. Step Functions handles failure notification
- Fixed progress milestones (5%, 15%, 85%, 100%) — no demucs output parsing
- Flat Docker layout: entrypoint.py imports `from shared.progress import ...`. Try/except import for test compatibility
- CPU-only PyTorch install (`--index-url .../whl/cpu`) saves ~1.8GB image size
- Model pre-downloaded via `demucs.pretrained.get_model('htdemucs_ft')` (direct Python download, no audio file needed)

**Docker build lessons** (discovered during manual testing):
- `torchcodec` is a required dependency — torchaudio needs it to save WAV files (`ImportError: TorchCodec is required`)
- Must build with `--platform linux/amd64` on Apple Silicon — Fargate runs x86_64 (`exec format error` otherwise)
- Must build with `--provenance=false` — Docker BuildKit's OCI image index format is incompatible with ECR basic scanning
- Original silent WAV approach (`anullsrc`) caused `pad1d` assertion errors in htdemucs_ft — zero-valued samples trigger a bug in demucs's reflect-padding code
- 10-second song: ~37s processing on 4 vCPU Fargate. 3-minute song: ~8.5 min

**Output**: `output/{userId}/{songId}/{drums,bass,other,vocals}.wav`

**Tests**: 77 total (13 new: 3 progress module + 10 entrypoint)

**Manual verification on deployed dev stack**:
- Upload via presigned URL → ECS RunTask → 4 stem WAVs in S3 OutputBucket — all working
- Progress events sent to SendProgress Lambda
- VPC, subnets, IGW, SG, ECS cluster, task definition, ECR repo — all verified
- ECR image scan: 1 MEDIUM (SQLite CVE, no action needed)
- Fargate vCPU quota: default may be 0, needs `L-36FBB829` increase to at least 4

**Verification**: `ruff check` + `pytest` (77 passed) + `sam validate --lint` (3 templates) all passing

---

## Phase 4.5: Code Audit Refactoring (DONE)

**Goal**: Address 8 findings from code audit before building new features.

### 4.5.1 — Parameterize CORS origins (Security)
All CORS configs use `"*"`. Add `CorsOrigin` parameter to root template (default `"*"` for dev). Pass as `CORS_ORIGIN` env var to Lambdas. Update `functions/shared/response.py` to read from env. Update `template.yaml` UploadBucket CORS and `templates/api.yaml` API CORS.

### 4.5.2 — CORS preflight handling (Web compatibility)
Verify `templates/api.yaml` handles OPTIONS preflight correctly. Add `AddDefaultAuthorizerToCorsPreflight: false` so OPTIONS requests don't require Cognito auth.

### 4.5.3 — Container env var validation (Robustness)
Add explicit validation of required env vars at top of `containers/demucs/entrypoint.py` `main()`. Clear error message listing which vars are missing.

### 4.5.4 — process_upload error differentiation (Reliability)
Separate validation errors (permanent → FAILED) from infrastructure errors (transient → re-raise for DLQ/retry) in `functions/process_upload/handler.py`.

### 4.5.5 — Container failure message improvement (Debuggability)
Include exception class name in `send_failure()` call in `containers/demucs/entrypoint.py`.

### 4.5.6 — Progress logging context (Debuggability)
Log message type and songId in `containers/shared/progress.py` exception handler.

### 4.5.7 — WebSocket action constants (Code quality)
Add `WS_ACTION_PING`, `WS_ACTION_PONG` to `functions/shared/constants.py`. Use in `functions/ws_default/handler.py`.

### 4.5.8 — send_progress exception handling (Reliability)
Wrap `send_to_connection()` call in try/except in `functions/send_progress/handler.py`. Clean up connection on any exception, not just when it returns False.

### Tests
- `test_process_upload.py` — verify transient errors re-raise (not marked FAILED)
- `test_send_progress.py` — verify exception in send_to_connection triggers cleanup
- `test_entrypoint_demucs.py` — verify missing env var raises RuntimeError

**Tests**: 81 total (3 new + 78 existing)

**Files changed**: 13 files (10 source + 3 test), 112 insertions, 11 deletions

**Verification**: `ruff check` + `pytest` (81 passed) all passing

---

## Phase 5: Whisper Container (Fargate) (DONE)

**Goal**: Docker container that extracts word-level synced lyrics for karaoke UX.

**Files**:
- `containers/whisper/Dockerfile` — Python 3.12-slim + faster-whisper (CTranslate2) + ffmpeg, model pre-downloaded
- `containers/whisper/entrypoint.py` — S3 download vocals.wav → faster-whisper `base` with `word_timestamps=True` → upload lyrics.json to S3
- `templates/ecs.yaml` — WhisperRepository (ECR), WhisperTaskRole, WhisperLogGroup, WhisperTaskDefinition (2 vCPU / 8 GB)
- `template.yaml` — WhisperRepositoryUri + WhisperTaskDefinitionArn outputs
- `tests/unit/test_entrypoint_whisper.py` (11 tests)

**Output**: `output/{userId}/{songId}/lyrics.json`

**Architecture decisions**:
- **faster-whisper** (not openai-whisper) — 4x faster on CPU via CTranslate2, int8 quantization, identical word timestamps. No PyTorch dependency → much smaller Docker image
- Same pattern as Demucs: download → process → upload, with progress milestones (5%, 15%, 85%, 100%)
- Input: `vocals.wav` from OUTPUT_BUCKET (Demucs output), not UPLOAD_BUCKET
- Instrumental detection: if total text < 10 chars → `{instrumental: true, segments: []}` (prevents hallucination on instrumental tracks)
- Always uploads lyrics.json, even for instrumental tracks (simpler for frontend — file always exists)
- `condition_on_previous_text=False` + `vad_filter=True` to prevent Whisper hallucination
- Module-level `WhisperModel` import with `None` fallback for tests (faster-whisper not a dev dependency)

**Lyrics JSON schema**:
```json
{
  "language": "en",
  "instrumental": false,
  "segments": [
    {
      "start": 0.0, "end": 3.5, "text": "Hello world",
      "words": [
        {"word": "Hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.6, "end": 1.0}
      ]
    }
  ]
}
```

**Docker build**:
```bash
docker build --provenance=false --platform linux/amd64 \
  -f containers/whisper/Dockerfile -t unplugd-whisper .
```

**Tests**: 92 total (11 new + 81 existing)

**Verification**: `ruff check` + `pytest` (92 passed) + `sam validate --lint` all passing

**Manual verification on deployed dev stack**:
- `sam deploy` → WhisperRepository, WhisperTaskRole, WhisperLogGroup, WhisperTaskDefinition all created
- Docker image built and pushed to ECR (`unplugd-dev-whisper:latest`)
- Demucs RunTask → 4 stems in S3 → Whisper RunTask → `lyrics.json` in S3 — full pipeline working
- Lyrics JSON has correct structure: `language`, `instrumental`, `segments[].words[].{word, start, end}`
- Progress events (5%, 15%, 85%, 100%) delivered via SendProgress Lambda

**Lessons learned**:
- **faster-whisper has no PyTorch dependency** — CTranslate2 handles inference natively. Docker image is ~2GB vs Demucs ~4GB. No need for `--index-url .../whl/cpu` trick.
- **Module-level import with `None` fallback** — faster-whisper is not a dev dependency, so `WhisperModel` is set to `None` at import time when not installed. Tests patch it at `containers.whisper.entrypoint.WhisperModel`. This differs from Demucs (which uses subprocess, no import to mock).
- **Docker tag collision gotcha** — If a stale ECR tag exists locally (e.g. from a typo like `whisperatest`), `docker tag` is a no-op when both tags share the same image ID, and `docker push` may push to the wrong repo. Fix: `docker rmi` the stale tag first, then re-tag and push.
- **`samconfig.toml` default deploy** — Added `[default.deploy.parameters]` mirroring `[dev.deploy.parameters]` so `sam deploy` (no flags) defaults to dev. `config_env` is not a valid config key — must duplicate the parameters.

---

## Phase 7: Song Library API (DONE)

**Goal**: CRUD endpoints for the user's song library + mixing presets.

**Endpoints** (4 new routes in `templates/api.yaml`, all Cognito-authorized):

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| `GET` | `/songs` | `list_songs/handler.py` | List user's songs (optional `?status=` filter) |
| `GET` | `/songs/{songId}` | `get_song/handler.py` | Song details + presigned stem/lyrics URLs (if COMPLETED) |
| `DELETE` | `/songs/{songId}` | `delete_song/handler.py` | Delete song record + S3 objects (any status) |
| `GET` | `/presets` | `get_presets/handler.py` | 5 mixing presets (Balanced, Karaoke, Drum/Bass Practice, Vocals Only) |

**Files created**:
- `functions/list_songs/handler.py` — queries DynamoDB by user, optional status filter with validation
- `functions/get_song/handler.py` — single song lookup, attaches presigned S3 URLs for COMPLETED songs
- `functions/delete_song/handler.py` — deletes DDB record + S3 objects (output stems/lyrics + upload)
- `functions/get_presets/handler.py` — returns static `MIXING_PRESETS` from constants
- `functions/shared/constants.py` — added `MIXING_PRESETS` (5 presets with `volumes` dict)
- `templates/api.yaml` — 4 new parameters, 4 routes, 4 Lambda permissions
- `template.yaml` — 4 new Lambda functions, updated ApiStack parameters
- `tests/unit/test_list_songs.py` (5 tests), `test_get_song.py` (5 tests), `test_delete_song.py` (4 tests), `test_get_presets.py` (2 tests)

**Architecture decisions**:
- All handlers reuse existing shared utilities — no new shared modules needed
- Presigned S3 URLs (not CloudFront) for stem/lyrics delivery — CloudFront deferred to Phase 12
- DELETE allows any status — Step Functions handles graceful failure if song is mid-processing
- Presets use `volumes` dict (`{drums: 1.0, bass: 0.0, ...}`) for Web Audio API gain control compatibility
- TDD approach: tests written first, then handlers, then infrastructure

**Tests**: 108 total (16 new + 92 existing)

**Verification**: `ruff check` + `ruff format` + `pytest` (108 passed) + `sam validate --lint` all passing

---

## Phase 6: Step Functions Orchestration (DONE)

**Goal**: Wire everything together into a state machine with automatic retry on failures.

**Files created**:
- `statemachines/processing.asl.json` — ASL definition (9 states, DefinitionSubstitutions for 10 ARNs)
- `functions/completion/handler.py` — mark song COMPLETED in DynamoDB
- `functions/cleanup/handler.py` — delete original upload from S3
- `functions/notify/handler.py` — send status-only WebSocket notification (frontend calls GET /songs/{songId})
- `functions/failure_handler/handler.py` — mark song FAILED, clean up partial S3 outputs, send FAILED notification
- `templates/orchestration.yaml` — StateMachine resource, IAM role (ECS RunTask, PassRole, Lambda Invoke, EventBridge)

**Files modified**:
- `template.yaml` — 4 new Lambda functions, OrchestrationStack nested stack, wired STATE_MACHINE_ARN, StartExecution IAM policy
- `templates/ecs.yaml` — exported 3 IAM role ARNs (TaskExecutionRole, DemucsTaskRole, WhisperTaskRole)
- `layers/common/requirements.txt` — added `aws-lambda-powertools>=2.0`
- `functions/process_upload/handler.py` — switched to powertools Logger (existing SFN stub was already correct)

**Flow**:
```
ValidateInput → RunDemucs (30min timeout) → RunWhisper (15min timeout) → MarkCompleted → SendNotification → CleanupUpload → Done
On error: MarkFailed (DDB + S3 cleanup + notify) → Failed
```

**Design decisions**:
- **ECS RunTask .sync**: Step Functions waits natively for Fargate task completion (no callback tokens)
- **Status-only notifications**: Send `{type: COMPLETED, songId}` — frontend fetches details via GET /songs/{songId}
- **Failure cleanup**: Removes partial S3 outputs on failure (user can also clean via DELETE /songs/{songId})
- **aws-lambda-powertools**: Added to CommonLayer for structured JSON logging with correlation IDs
- **Separate ASL file**: `statemachines/processing.asl.json` with DefinitionUri + DefinitionSubstitutions

**Auto-retry** (ASL Retry blocks on RunDemucs and RunWhisper):
- `ErrorEquals: ["States.TaskFailed"]` — catches Fargate task failures (spot interruptions, transient S3 errors)
- `MaxAttempts: 2`, `IntervalSeconds: 30`, `BackoffRate: 2`
- `ErrorEquals: ["ECS.AmazonECSException"]` — catches capacity/quota errors
- `IntervalSeconds: 60`, `BackoffRate: 2`, `MaxAttempts: 5`

**Tests**: 15 new tests (test_completion, test_cleanup, test_notify, test_failure_handler, test_processing_asl, test_process_upload SFN test) — **123 total**

**Notes**:
- EventBridge rule `StepFunctionsGetEventsForECSTaskRule` is auto-created by Step Functions for `.sync` integration — IAM policy must allow events:PutTargets/PutRule/DescribeRule
- `FakeLambdaContext` fixture added to conftest.py for aws-lambda-powertools `@inject_lambda_context` compatibility in tests
- Container names in ASL overrides (`"demucs"`, `"whisper"`) must match Name fields in ecs.yaml task definitions

---

## Phase 7.5: E2E Testing & Fixes (In Progress)

**Goal**: Manual end-to-end testing of the deployed stack, fixing issues discovered along the way.

**Fixes applied**:
- **ASL LaunchType conflict**: Removed `"LaunchType": "FARGATE"` from RunDemucs and RunWhisper states in `statemachines/processing.asl.json` — ECS rejects requests that specify both `LaunchType` and `CapacityProviderStrategy` simultaneously. FARGATE_SPOT via CapacityProviderStrategy is sufficient.

**Issues found**:
- **Stale errorMessage on success**: `completion/handler.py` sets `status: COMPLETED` but doesn't clear `errorMessage` from a prior failed run. GET /songs/{songId} returns the stale error. Fix: add `remove_attrs` support to `update_song()` and pass `remove_attrs=["errorMessage"]` in completion handler.
- **No backpressure on SFN starts**: `process_upload` calls `sfn.start_execution()` directly — burst uploads could exhaust Fargate vCPU quota or hit SFN throttling.

**Planned**:
- **SQS backpressure queue**: `process_upload → SQS → start_execution Lambda → Step Functions`. New processing queue in `monitoring.yaml` (SSE, 1-day retention, redrive to existing DLQ). New `start_execution` consumer Lambda with `ReservedConcurrentExecutions: 5` (tunable parallelism knob). `process_upload` switches from `sfn.start_execution()` to `sqs.send_message()`.
- **Fix stale errorMessage**: Add `remove_attrs` parameter to `dynamodb_utils.update_song()`. Completion handler passes `remove_attrs=["errorMessage"]` to clear leftover error fields on success.
- **Retry endpoint** (`POST /songs/{songId}/retry`) — reprocess a FAILED song without re-uploading
- **Powertools logging migration**: Migrate remaining Lambdas from `logging.getLogger()` to `aws_lambda_powertools.Logger` with `@inject_lambda_context`. Currently only `process_upload`, `completion`, `cleanup`, `notify`, `failure_handler` use powertools. Remaining: `upload_request`, `get_song`, `list_songs`, `delete_song`, `get_presets`, `ws_connect`, `ws_disconnect`, `ws_default`, `send_progress`. Adds structured JSON logging, correlation IDs, and cold start tracking across all handlers.
- Additional issues TBD from continued manual testing

---

## Phase 8: Web Frontend (React/Next.js)

**Goal**: Tangible, demo-able web UI — the portfolio piece.

**Core pages**:
1. **Landing/Login** — Cognito Hosted UI or `amazon-cognito-identity-js`
2. **Upload** — drag-and-drop audio file, real-time progress bar via WebSocket
3. **Song Library** — list of processed songs with status indicators
4. **Player** — stem toggle controls (drums/bass/other/vocals on/off), synced lyrics display, waveform visualization

**Audio playback**: Web Audio API — load all 4 stem WAV files as separate `AudioBufferSourceNode`s with independent gain control. Presets (karaoke, drum practice, etc.) are gain presets.

**Key tech**: Next.js (App Router), Cognito auth, WebSocket for progress, Web Audio API for playback.

---

## Phase 9: CI/CD

**Goal**: Automated testing and deployment.

**Files**:
- `.github/workflows/ci.yml` — lint (ruff) + type-check (mypy) + unit tests on every PR
- `.github/workflows/deploy.yml` — build Docker images + `sam deploy` (dev on merge to main, prod manual)
- `.github/workflows/docker.yml` — build + push Demucs/Whisper images to ECR

---

## Phase 10: SageMaker Training Pipeline

**Goal**: Learn ML by training a modern source separation model on AWS.

**Architecture**: Band-Split RNN (BSRNN) or BS-RoFormer — well-documented, modern, significantly better than legacy U-Net (~8-10 dB SDR vs ~6 dB).

**Dataset**: MUSDB18 (~10 hours, 150 tracks, ~10GB). Slakh2100 as optional augmentation data.

**Files**:
- `ml/` — new top-level directory for ML training code
- `ml/train.py` — SageMaker-compatible training entry point
- `ml/model.py` — Band-Split RNN architecture
- `ml/dataset.py` — MUSDB18 data loading with torchaudio (handles all audio formats natively via FFmpeg)
- `ml/inference.py` — SageMaker inference handlers (model_fn, input_fn, predict_fn, output_fn)
- `ml/Dockerfile` — Training container image
- `ml/requirements.txt` — PyTorch + torchaudio + dependencies

**SageMaker components**: S3 bucket for training data + model artifacts, Training Job config (ml.g4dn.xlarge Spot), Model Registry for versioning, Experiment tracking.

**Training cost**: ~$3-5/run on Spot. Expect 5-10 runs for experimentation → $15-35 total.

---

## Phase 11: Custom Model Integration

**Goal**: Deploy trained custom model alongside Demucs on Fargate.

**S3 contract as abstraction**: Both models produce the same output structure:
- Input: `uploads/{userId}/{songId}/{filename}` (any audio format)
- Output: `output/{userId}/{songId}/{drums,bass,other,vocals}.wav`

**Files**:
- `containers/custom_model/Dockerfile` — custom model inference container
- `containers/custom_model/entrypoint.py` — same interface as Demucs entrypoint
- `templates/ecs.yaml` — add CustomModelTaskDefinition
- `statemachines/processing.asl.json` — add Choice state to route to Demucs or custom model
- `functions/upload_request/handler.py` — accept optional `model` parameter (default: "demucs")

---

## Phase 12: Monitoring, Hardening, Polish

**Goal**: Production readiness.

**Monitoring**:
- `functions/shared/logging_utils.py` — JSON structured logger with correlation IDs
- CloudWatch dashboards: Lambda errors, Step Functions executions, DLQ depth, API Gateway latency, ECS task status
- Alarms: DLQ > 0, Step Functions failure rate > 10%, API 5XX > 1%
- Resource tagging (`Environment`, `Application`, `CostCenter`)

**Hardening**:
- Rate limiting on API Gateway
- WAF rules for abuse prevention
- CloudFront signed URLs for audio delivery
- JWT `verify_aud` tightening (conditional on COGNITO_APP_CLIENT_ID)
- Cold start mitigation (provisioned concurrency for critical Lambdas)

**Scaling (if needed)**:
- SQS backpressure queue between process_upload and Step Functions
- `ReservedConcurrentExecutions` to control concurrent ECS task launches

---

## Cost Estimates

### Per-Song Processing (3-min song, Fargate SPOT)

| Component | Config | Time | Cost |
|-----------|--------|------|------|
| Demucs | 4 vCPU, 16 GB | 8.5 min | $0.010 |
| Whisper | 2 vCPU, 8 GB | ~5 min | $0.003 |
| **Total** | | ~13.5 min | **$0.013** |

### Monthly Infrastructure

| Environment | Songs/mo | Compute | Infra (Lambda, API GW, DDB, S3, CW) | Total |
|-------------|----------|---------|--------------------------------------|-------|
| Dev | 50 | $0.65 | ~$5-8 | ~$6-9 |
| Prod | 1000 | $13 | ~$15-25 | ~$28-38 |

### SageMaker Training (one-time per experiment)

| Instance | GPU | Time | Spot Cost |
|----------|-----|------|-----------|
| ml.g4dn.xlarge | T4 16GB | ~15 hours | $3.30 |
| ml.g5.xlarge | A10G 24GB | ~5 hours | $2.10 |

Expected 5-10 training runs → **$15-35 total**.

### Fargate SPOT vs SageMaker Async Inference

| Option | Per Song (sporadic) | Monthly (50 songs) | Idle Cost |
|--------|--------------------|--------------------|-----------|
| **Fargate SPOT** | **$0.013** | **$0.65** | $0 |
| SageMaker Async GPU (cold) | $0.086 | $4.30 | $0 |
| SageMaker Async GPU (warm) | $0.025 | $1.25 | $0 |
| SageMaker Real-Time GPU | N/A | $530 | 24/7 |

**Verdict**: Fargate SPOT is 6-8x cheaper for sporadic usage. SageMaker Async bills for idle timeout before scale-down (~5 min per cold invocation).
