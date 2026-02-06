# Unplugd

Serverless AWS karaoke backend — upload any song, get separated stems and synced lyrics.

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
| ML | Demucs `htdemucs_ft` + Whisper `base` |
| IaC | SAM / CloudFormation (nested stacks) |
| Python | uv (3.12) |

## Architecture

```
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

```
unplugd/
├── template.yaml              # Root SAM template (orchestrates nested stacks)
├── templates/                 # Nested CloudFormation templates
│   ├── storage.yaml           # DynamoDB, S3
│   ├── auth.yaml              # Cognito
│   └── monitoring.yaml        # SQS DLQ, CloudWatch alarms
├── functions/                 # Lambda handlers
│   ├── shared/                # Shared utilities (constants, DDB/S3 helpers, error handling)
│   ├── upload_request/        # POST /songs/upload-url
│   ├── process_upload/        # S3 trigger → validate → Step Functions
│   ├── list_songs/            # GET /songs
│   ├── get_song/              # GET /songs/{songId}
│   ├── delete_song/           # DELETE /songs/{songId}
│   └── ...                    # WebSocket, progress, completion handlers
├── containers/                # Fargate Docker images
│   ├── demucs/                # Source separation
│   └── whisper/               # Lyrics extraction
├── layers/common/             # Lambda layer (symlink → functions/shared)
├── statemachines/             # Step Functions ASL definitions
├── tests/                     # Unit + integration tests
├── .claude/                   # Project docs (gitignored)
│   ├── PROJECT.md             # Full spec (API, schemas, formats)
│   └── PROJECT_PLAN.md        # Implementation roadmap
└── _reference/                # Legacy codebase (archived)
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
# Run unit tests
uv run pytest tests/unit/ -v

# Lint
uv run ruff check .

# Type check
uv run mypy functions/shared/

# Local Lambda testing
sam local invoke UploadRequestFunction -e events/upload_request.json
```

## Documentation

- **[PROJECT.md](PROJECT.md)** — Full specification (API reference, DB schemas, lyrics format, mixing presets, cost estimates)
- **[PROJECT_PLAN.md](PROJECT_PLAN.md)** — Implementation roadmap with phase details and status

## License

MIT
