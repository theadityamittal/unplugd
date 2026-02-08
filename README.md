# Unplugd

Serverless AWS karaoke platform — upload any song, get separated stems and synced lyrics.

## What It Does

1. **Upload** an audio file (MP3, WAV, M4A, FLAC — max 10 min / 50MB)
2. **Separate** into 4 stems (drums, bass, other, vocals) using Meta's Demucs
3. **Extract** word-level synced lyrics using OpenAI's Whisper
4. **Serve** stems + lyrics via presigned S3 URLs for playback with real-time mixing

Users toggle stems on/off: karaoke (vocals off), drum practice (drums off), bass practice (bass off), or isolate vocals.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | API Gateway (REST + WebSocket) |
| Compute | Lambda (Python 3.12) + ECS Fargate (Docker) |
| Orchestration | Step Functions |
| Auth | Cognito |
| Database | DynamoDB |
| Storage | S3 (presigned URLs) |
| ML | Demucs `htdemucs_ft` + Whisper `base` (v2: custom model via SageMaker) |
| IaC | SAM / CloudFormation (nested stacks) |
| Frontend | React / Next.js (planned) |
| Python | uv (3.12) |

## Architecture

```text
Client  -->  API Gateway  -->  UploadRequest Lambda (presigned URL)
                |
        PUT to S3 Upload Bucket
                |
        ProcessUpload Lambda  -->  Step Functions
                                      |
                          Demucs (Fargate) --> Whisper (Fargate)
                                      |
                          Completion --> Cleanup --> Notify
                                      |
                          S3 Output Bucket (stems + lyrics)
```

## Project Structure

```text
unplugd/
├── template.yaml              # Root SAM template (orchestrates nested stacks)
├── templates/                 # Nested CloudFormation templates
│   ├── api.yaml               # REST API Gateway + routes
│   ├── auth.yaml              # Cognito user pool & clients
│   ├── ecs.yaml               # ECR + ECS Fargate task definitions
│   ├── monitoring.yaml        # SQS DLQ + CloudWatch alarms
│   ├── storage.yaml           # DynamoDB tables + S3 output bucket
│   ├── vpc.yaml               # VPC, subnets, IGW, security groups
│   └── websocket.yaml         # WebSocket API Gateway
├── functions/                 # Lambda handlers
│   ├── shared/                # Shared utilities (Lambda layer)
│   ├── upload_request/        # POST /songs/upload-url
│   ├── process_upload/        # S3 trigger → validate → Step Functions
│   ├── ws_connect/            # WebSocket $connect (JWT auth)
│   ├── ws_disconnect/         # WebSocket $disconnect
│   ├── ws_default/            # WebSocket $default (ping/pong)
│   ├── send_progress/         # Push progress via WebSocket
│   ├── list_songs/            # GET /songs
│   ├── get_song/              # GET /songs/{songId}
│   ├── delete_song/           # DELETE /songs/{songId}
│   ├── get_presets/           # GET /presets
│   ├── completion/            # Step Functions: mark COMPLETED
│   ├── cleanup/               # Step Functions: delete upload
│   ├── notify/                # Step Functions: notify completion
│   └── failure_handler/       # Step Functions: mark FAILED
├── containers/                # Fargate Docker images
│   ├── shared/                # Shared progress reporting
│   ├── demucs/                # Source separation
│   └── whisper/               # Lyrics extraction
├── layers/common/             # Lambda layer (symlink → functions/shared)
├── statemachines/             # Step Functions ASL definitions
├── tests/                     # 108 unit tests across 20 files
├── docs/
│   └── PROJECT.md             # Full spec (API, schemas, formats, costs)
│   └── PROJECT_PLAN.md        # Implementation roadmap with phase details and status
└── _reference/                # Legacy U-Net codebase (archived)
```

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS account with credentials configured (`~/.aws/credentials`)
- Docker (for Fargate container builds)

## Quick Start

```bash
# Install dependencies
uv sync

# Validate SAM templates
sam validate

# Build
sam build

# Deploy to dev
sam deploy --config-env dev

# Deploy to prod
sam deploy --config-env prod
```

## Development

```bash
# Run unit tests (92 tests)
uv run pytest tests/unit/ -v

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Type check
uv run mypy functions/shared/

# Local Lambda testing
sam local invoke UploadRequestFunction -e events/upload_request.json

# Build Fargate containers
docker build --provenance=false --platform linux/amd64 \
  -f containers/demucs/Dockerfile -t unplugd-demucs .
docker build --provenance=false --platform linux/amd64 \
  -f containers/whisper/Dockerfile -t unplugd-whisper .
```

## Current Status

**Phases 0-7 complete** — 108 unit tests passing.

| Phase | Description | Status |
|-------|-------------|--------|
| 0-4 | Scaffold, Storage/Auth, Upload API, WebSocket, Demucs Container | **Done** |
| 4.5 | Code audit refactoring | **Done** |
| 5 | Whisper Container (lyrics) | **Done** |
| 7 | Song Library API | **Done** |
| 6 | Step Functions Orchestration | Pending |
| 8 | Web Frontend (React/Next.js) | Pending |
| 9-12 | CI/CD, SageMaker ML, Model Integration, Hardening | Pending |

## Documentation

- **[docs/PROJECT.md](docs/PROJECT.md)** — Full specification (API reference, DB schemas, lyrics format, mixing presets, cost estimates)
- **[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)** — Implementation roadmap with phase details and status

## License

MIT
