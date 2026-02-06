# Unplugd

**Serverless AWS Karaoke Platform**

Upload any song. Get separated stems. See synced lyrics. Practice any instrument.

---

## Vision

Unplugd transforms any music file into an interactive karaoke and practice tool. Users upload a song, and the platform:

1. **Separates** the audio into 4 stems (drums, bass, other instruments, vocals) using Meta's Demucs
2. **Extracts** word-level synced lyrics using OpenAI's Whisper
3. **Serves** the stems and lyrics for playback with real-time mixing controls

Users can toggle individual stems on/off for different use cases — karaoke (vocals off), drum practice (drums off), bass practice (bass off), or isolate vocals for learning.

**v1**: Backend API only (serverless AWS). **v2**: Flutter iOS app + custom ML model on SageMaker + Spotify integration.

---

## Features

### Core (v1)
- Upload audio files (MP3, WAV, M4A, FLAC — max 10 min / 50MB)
- AI source separation into 4 stems: drums, bass, other, vocals
- AI lyrics extraction with word-level timestamps
- Real-time processing progress via WebSocket
- Persistent song library per user
- Stem mixing presets:
  - **Karaoke** — vocals off, instruments on
  - **Drum Practice** — drums off, everything else on
  - **Bass Practice** — bass off, everything else on
  - **Vocals Only** — isolate vocals
  - **Custom** — individual on/off toggles per stem
- Audio delivery via CloudFront CDN
- Privacy: original uploads deleted after processing

### Planned (v2)
- Flutter iOS app (App Store submission)
- Custom source separation model trained on SageMaker
- Spotify library integration (browse + metadata)
- External lyrics API fallback (Musixmatch/Genius)
- Per-user CloudFront signed URLs
- Usage tiers (free/premium)
- Android app

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────────┐
│ Client App   │────►│ API Gateway  │────►│ UploadRequest λ   │
│ (future)     │     │ (REST+Auth)  │     │ → presigned URL   │
└─────────────┘     └──────────────┘     └───────────────────┘
       │                                          │
       │  PUT file to S3                          │ DynamoDB: PENDING_UPLOAD
       ▼                                          ▼
┌──────────────┐     ┌──────────────────┐  ┌──────────────────┐
│ S3 Upload    │────►│ ProcessUpload λ  │─►│ Step Functions   │
│ Bucket       │     │ validate + start │  │ Execution        │
└──────────────┘     └──────────────────┘  └────────┬─────────┘
                                                     │
              ┌──────────────────────────────────────┘
              ▼
     ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐
     │ Demucs (Fargate) │───►│ Whisper (Fargate)│───►│ Completion λ │
     │ 4 stems → S3    │    │ lyrics.json → S3 │    │ DDB: COMPLETE│
     └────────┬────────┘    └────────┬─────────┘    └──────┬───────┘
              │                      │                      │
              │  progress events     │  progress events     ▼
              ▼                      ▼               ┌──────────────┐
     ┌─────────────────┐                             │ Cleanup λ    │
     │ SendProgress λ  │                             │ delete upload│
     │ → WebSocket API │                             └──────┬───────┘
     │ → Client App    │                                    ▼
     └─────────────────┘                             ┌──────────────┐
                                                     │ Notify λ     │
         ┌──────────────────┐                        │ → WebSocket  │
         │ CloudFront + S3  │◄───── stems + lyrics   └──────────────┘
         │ (audio delivery) │        served here
         └──────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | API Gateway (REST + WebSocket) |
| Compute | AWS Lambda (Python 3.12) + ECS Fargate (Docker) |
| Orchestration | AWS Step Functions |
| Auth | AWS Cognito |
| Database | DynamoDB (PAY_PER_REQUEST) |
| Storage | S3 (uploads + output) + CloudFront CDN |
| ML: Separation | Meta Demucs `htdemucs_ft` (Fargate, CPU) |
| ML: Lyrics | OpenAI Whisper `base` (Fargate, CPU, word timestamps) |
| IaC | SAM / CloudFormation |
| CI/CD | GitHub Actions |
| Python deps | uv (Python 3.12) |
| Monitoring | CloudWatch (logs, metrics, dashboards, alarms) |
| Region | us-east-1 |
| Environments | Dev + Prod (parameterized SAM stacks) |

---

## Processing Pipeline

### Upload Flow
1. Client requests a presigned S3 PUT URL via `POST /songs/upload-url`
2. Client uploads audio directly to S3 using the presigned URL
3. S3 event triggers `ProcessUpload` Lambda
4. Lambda validates file (format, size, duration via `mutagen`)
5. Lambda starts Step Functions execution
6. WebSocket sends `PROCESSING_STARTED` to client

### Step Functions Workflow
```
ValidateInput (Pass)
  → RunDemucs (ecs:runTask.sync, 15min timeout)
  → RunWhisper (ecs:runTask.sync, 10min timeout)
  → UpdateSongCompleted (Lambda)
  → DeleteOriginalUpload (Lambda)
  → NotifyCompletion (Lambda → WebSocket)
  → ProcessingComplete (Succeed)

On error at any stage:
  → MarkSongFailed (Lambda)
  → NotifyFailure (Lambda → WebSocket)
  → ProcessingFailed (Fail)
```

### Demucs Container
- Downloads audio from S3
- Runs `htdemucs_ft` model (waveform-based, no STFT needed)
- Outputs 4 stems as WAV files to S3: `output/{userId}/{songId}/{drums,bass,other,vocals}.wav`
- Reports progress via async Lambda invocation → WebSocket

### Whisper Container
- Downloads `vocals.wav` from S3 (Demucs output)
- Runs Whisper `base` with `word_timestamps=True`
- Outputs lyrics JSON to S3: `output/{userId}/{songId}/lyrics.json`
- Handles instrumental tracks gracefully (empty lyrics, not an error)

### Progress Reporting
Fargate containers invoke `SendProgress` Lambda asynchronously via `boto3`. Lambda looks up user's WebSocket connections in DynamoDB and pushes events via API Gateway Management API.

---

## Database Schema

### SongsTable (DynamoDB)

| Attribute | Type | Description |
|-----------|------|-------------|
| `userId` (PK) | S | Cognito user sub |
| `songId` (SK) | S | ULID |
| `title` | S | Original filename or user-provided |
| `status` | S | PENDING_UPLOAD, PROCESSING, COMPLETED, FAILED |
| `uploadedAt` | S | ISO 8601 timestamp |
| `completedAt` | S | ISO 8601 timestamp |
| `durationSec` | N | Audio duration in seconds |
| `stemsS3Prefix` | S | S3 key prefix for output stems |
| `lyricsS3Key` | S | S3 key for lyrics JSON |
| `originalFormat` | S | mp3, wav, m4a, flac |
| `fileSizeBytes` | N | Original file size |
| `errorMessage` | S | Error details (on FAILED) |
| `executionArn` | S | Step Functions execution ARN |

**GSI StatusIndex**: PK=`userId`, SK=`status` — query songs by processing state

### ConnectionsTable (DynamoDB)

| Attribute | Type | Description |
|-----------|------|-------------|
| `connectionId` (PK) | S | API Gateway WebSocket connection ID |
| `userId` | S | Cognito user sub |
| `connectedAt` | S | ISO 8601 timestamp |
| `ttl` | N | Auto-expire after 2 hours |

**GSI UserIndex**: PK=`userId`, SK=`connectionId` — find all connections for a user

---

## API Reference

### REST Endpoints (Cognito-authorized)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/songs/upload-url` | Get presigned S3 upload URL + songId |
| `GET` | `/songs` | List user's song library (optional `?status=` filter) |
| `GET` | `/songs/{songId}` | Get song details + CloudFront stem/lyrics URLs |
| `DELETE` | `/songs/{songId}` | Delete song, stems, and lyrics |
| `GET` | `/presets` | Get available mixing presets |

### WebSocket

| Route | Description |
|-------|-------------|
| `$connect` | Authenticate + store connection |
| `$disconnect` | Remove connection |
| `$default` | Ping/pong |

### WebSocket Messages (server → client)

```json
{"type": "PROCESSING_STARTED", "songId": "01HX..."}
{"type": "PROGRESS", "songId": "01HX...", "stage": "demucs", "progress": 50, "message": "Separating stems..."}
{"type": "PROGRESS", "songId": "01HX...", "stage": "whisper", "progress": 80, "message": "Extracting lyrics..."}
{"type": "COMPLETED", "songId": "01HX...", "stems": {"drums": "https://cdn.../drums.wav", ...}, "lyricsUrl": "https://cdn.../lyrics.json"}
{"type": "FAILED", "songId": "01HX...", "error": "Processing failed: ..."}
```

---

## Lyrics JSON Format

```json
{
  "language": "en",
  "segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "text": "Hello darkness my old friend",
      "words": [
        {"word": "Hello", "start": 0.0, "end": 0.5},
        {"word": "darkness", "start": 0.6, "end": 1.2},
        {"word": "my", "start": 1.3, "end": 1.5},
        {"word": "old", "start": 1.6, "end": 1.9},
        {"word": "friend", "start": 2.0, "end": 2.8}
      ]
    }
  ],
  "fullText": "Hello darkness my old friend..."
}
```

---

## Mixing Presets

| Preset | Drums | Bass | Other | Vocals |
|--------|-------|------|-------|--------|
| Karaoke | ON | ON | ON | OFF |
| Drum Practice | OFF | ON | ON | ON |
| Bass Practice | ON | OFF | ON | ON |
| Vocals Only | OFF | OFF | OFF | ON |
| Custom | configurable | configurable | configurable | configurable |

Mixing is performed client-side by playing all 4 stem audio files simultaneously and toggling each on/off. The backend only provides the separated stems and preset definitions.

---

## Project Structure

```
unplugd/
├── template.yaml                     # Root SAM template (imports nested stacks)
├── samconfig.toml                    # SAM deploy config (dev/prod)
├── pyproject.toml                    # uv + Python 3.12
│
├── .claude/
│   └── PROJECT_PLAN.md              # Implementation plan & phases
│
├── docs/
│   └── PROJECT.md                    # This file
│
├── templates/                        # Nested SAM/CloudFormation templates
│   ├── api.yaml                     # API Gateway + Lambda functions
│   ├── auth.yaml                    # Cognito user pool & clients
│   ├── monitoring.yaml              # CloudWatch dashboards & alarms
│   └── storage.yaml                 # S3 buckets + DynamoDB tables
│
├── functions/                        # Lambda functions
│   ├── shared/                       # Shared utilities (Lambda layer)
│   ├── upload_request/               # POST /songs/upload-url
│   ├── process_upload/               # S3 trigger → validate → Step Functions
│   ├── list_songs/                   # GET /songs
│   ├── get_song/                     # GET /songs/{songId}
│   ├── delete_song/                  # DELETE /songs/{songId}
│   ├── get_presets/                  # GET /presets
│   ├── ws_connect/                   # WebSocket $connect
│   ├── ws_disconnect/                # WebSocket $disconnect
│   ├── ws_default/                   # WebSocket $default
│   ├── send_progress/                # Push progress via WebSocket
│   ├── completion/                   # Step Functions: mark COMPLETED
│   ├── cleanup/                      # Step Functions: delete upload
│   ├── notify/                       # Step Functions: final notification
│   └── failure_handler/              # Step Functions: mark FAILED
│
├── containers/                       # ECS Fargate Docker images
│   ├── demucs/                       # Demucs source separation
│   └── whisper/                      # Whisper lyrics extraction
│
├── layers/common/                    # Shared Lambda layer
├── statemachines/                    # Step Functions ASL definitions
├── events/                           # SAM local test events
│
├── tests/                            # Unit + integration tests
│   ├── conftest.py                  # Shared fixtures (moto mocks, env vars)
│   ├── unit/                        # Unit tests per module
│   │   ├── test_constants.py
│   │   ├── test_dynamodb_utils.py
│   │   ├── test_error_handling.py
│   │   ├── test_process_upload.py
│   │   ├── test_response.py
│   │   └── test_upload_request.py
│   └── integration/                 # Integration tests
│
├── .github/workflows/                # CI/CD pipelines
└── _reference/                       # Old codebase (archived)
```

---

## Cost Estimates

### Dev Environment (low usage)

| Resource | ~Monthly Cost |
|----------|--------------|
| Lambda | $0.01 |
| API Gateway | $0.50 |
| DynamoDB | $0.25 |
| S3 (10GB) | $0.23 |
| CloudFront (10GB) | $0.85 |
| Fargate SPOT (50 songs) | $2-5 |
| ECR | $0.30 |
| CloudWatch | $0.50 |
| Cognito (50 users) | Free |
| **Total** | **~$5-8** |

### Production (1000 songs/month)

| Resource | ~Monthly Cost |
|----------|--------------|
| Lambda | $1-2 |
| API Gateway | $5-10 |
| DynamoDB | $5-10 |
| S3 (200GB) | $5 |
| CloudFront (500GB) | $45 |
| Fargate SPOT (1000 songs) | $40-80 |
| ECR | $1 |
| CloudWatch | $5 |
| Cognito (1000 users) | Free |
| **Total** | **~$110-160** |

---

## Deployment

```bash
# Install dependencies
uv sync

# Validate SAM template
sam validate

# Build
sam build

# Deploy to dev
sam deploy --config-env dev

# Deploy to prod
sam deploy --config-env prod

# Local testing
sam local start-api
sam local invoke UploadRequestFunction -e events/upload_request.json

# Build Fargate images
docker build -t unplugd-demucs containers/demucs/
docker build -t unplugd-whisper containers/whisper/
```

---

## License

MIT License - See LICENSE file.
