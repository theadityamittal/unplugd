"""Whisper lyrics extraction — Fargate entrypoint.

Downloads vocals.wav from S3, runs faster-whisper base model with word-level
timestamps, uploads lyrics.json back to S3. Handles instrumental tracks
gracefully (empty lyrics, not an error). Progress milestones are sent via the
SendProgress Lambda (fire-and-forget).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import boto3

try:
    from faster_whisper import WhisperModel  # Docker
except ImportError:
    WhisperModel = None  # Tests (faster-whisper not installed)

try:
    from shared.progress import send_failure, send_progress  # Docker (flat layout)
except ImportError:
    from containers.shared.progress import send_failure, send_progress  # Tests (package layout)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

s3_client = boto3.client("s3")

TEMP_DIR = "/tmp"
WHISPER_MODEL = "base"
MIN_TEXT_LENGTH = 10  # Below this = instrumental (prevents hallucination)
REQUIRED_ENV_VARS = (
    "OUTPUT_BUCKET",
    "S3_INPUT_KEY",
    "S3_OUTPUT_PREFIX",
    "USER_ID",
    "SONG_ID",
)


def download_vocals(bucket: str, key: str, local_path: str) -> None:
    """Download the vocals.wav file from S3."""
    logger.info("Downloading s3://%s/%s to %s", bucket, key, local_path)
    s3_client.download_file(bucket, key, local_path)


def run_whisper(vocals_path: str) -> dict:
    """Run faster-whisper on vocals.wav. Returns lyrics dict with word timestamps."""
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    segments_gen, info = model.transcribe(
        vocals_path,
        word_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=True,
    )

    segments_list = list(segments_gen)

    # Check if instrumental (no meaningful text)
    total_text = " ".join(seg.text for seg in segments_list).strip()
    if not total_text or len(total_text) < MIN_TEXT_LENGTH:
        logger.info("Instrumental track detected (no lyrics)")
        return {"language": None, "instrumental": True, "segments": []}

    return {
        "language": info.language,
        "instrumental": False,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
                "words": [
                    {"word": w.word.strip(), "start": w.start, "end": w.end}
                    for w in (seg.words or [])
                ],
            }
            for seg in segments_list
        ],
    }


def upload_lyrics(lyrics_data: dict, bucket: str, output_prefix: str) -> None:
    """Upload lyrics.json to S3."""
    s3_key = f"{output_prefix}/lyrics.json"
    lyrics_json = json.dumps(lyrics_data, indent=2)

    logger.info("Uploading lyrics to s3://%s/%s", bucket, s3_key)
    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=lyrics_json.encode("utf-8"),
        ContentType="application/json",
    )


def main() -> None:
    """Orchestrate: download vocals -> whisper -> upload lyrics with progress milestones."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    try:
        output_bucket = os.environ["OUTPUT_BUCKET"]
        s3_input_key = os.environ["S3_INPUT_KEY"]
        s3_output_prefix = os.environ["S3_OUTPUT_PREFIX"]

        local_vocals = str(Path(TEMP_DIR) / "vocals.wav")

        send_progress(stage="whisper", progress=5, message="Downloading vocals stem...")
        download_vocals(output_bucket, s3_input_key, local_vocals)

        send_progress(stage="whisper", progress=15, message="Extracting lyrics with Whisper...")
        lyrics_data = run_whisper(local_vocals)

        send_progress(stage="whisper", progress=85, message="Uploading lyrics...")
        upload_lyrics(lyrics_data, output_bucket, s3_output_prefix)

        send_progress(stage="whisper", progress=100, message="Lyrics processing complete")
        logger.info("Whisper processing complete")

    except Exception as exc:
        logger.exception("Fatal error in whisper entrypoint")
        try:
            send_failure(f"{type(exc).__name__}: {exc}")
        except Exception:
            logger.warning("Failed to send failure notification", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
