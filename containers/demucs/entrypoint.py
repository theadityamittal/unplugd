"""Demucs stem separation — Fargate entrypoint.

Downloads audio from S3, runs htdemucs_ft model, uploads 4 stem WAVs back to S3.
Progress milestones are sent via the SendProgress Lambda (fire-and-forget).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import boto3

try:
    from shared.progress import send_progress  # Docker (flat layout)
except ImportError:
    from containers.shared.progress import send_progress  # Tests (package layout)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

s3_client = boto3.client("s3")

STEM_NAMES = ("drums", "bass", "other", "vocals")
TEMP_DIR = "/tmp"


def download_input(bucket: str, key: str, local_path: str) -> None:
    """Download the input audio file from S3."""
    logger.info("Downloading s3://%s/%s to %s", bucket, key, local_path)
    s3_client.download_file(bucket, key, local_path)


def run_demucs(input_path: str, output_dir: str) -> str:
    """Run demucs CLI on the input file. Returns path to stems directory."""
    cmd = [
        "python",
        "-m",
        "demucs",
        "--name",
        "htdemucs_ft",
        "-d",
        "cpu",
        "--out",
        output_dir,
        input_path,
    ]
    logger.info("Running demucs: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Demucs failed with exit code {result.returncode}: {stderr}")

    track_name = Path(input_path).stem
    stems_dir = Path(output_dir) / "htdemucs_ft" / track_name

    if not stems_dir.is_dir():
        raise RuntimeError(f"Expected stems directory not found: {stems_dir}")

    return str(stems_dir)


def upload_stems(stems_dir: str, bucket: str, output_prefix: str) -> None:
    """Upload all 4 stem WAV files to S3."""
    for stem in STEM_NAMES:
        local_path = Path(stems_dir) / f"{stem}.wav"
        if not local_path.is_file():
            raise FileNotFoundError(f"Stem file not found: {local_path}")

        s3_key = f"{output_prefix}/{stem}.wav"
        logger.info("Uploading %s to s3://%s/%s", local_path, bucket, s3_key)
        s3_client.upload_file(
            str(local_path),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": "audio/wav"},
        )


def main() -> None:
    """Orchestrate: download -> demucs -> upload with progress milestones."""
    try:
        upload_bucket = os.environ["UPLOAD_BUCKET"]
        output_bucket = os.environ["OUTPUT_BUCKET"]
        s3_input_key = os.environ["S3_INPUT_KEY"]
        s3_output_prefix = os.environ["S3_OUTPUT_PREFIX"]

        filename = Path(s3_input_key).name
        local_input = str(Path(TEMP_DIR) / filename)
        output_dir = str(Path(TEMP_DIR) / "demucs_output")

        send_progress(stage="demucs", progress=5, message="Downloading audio file...")
        download_input(upload_bucket, s3_input_key, local_input)

        send_progress(stage="demucs", progress=15, message="Separating stems with Demucs...")
        stems_dir = run_demucs(local_input, output_dir)

        send_progress(stage="demucs", progress=85, message="Stem separation complete, uploading...")
        upload_stems(stems_dir, output_bucket, s3_output_prefix)

        send_progress(stage="demucs", progress=100, message="All stems uploaded successfully")
        logger.info("Demucs processing complete")

    except Exception:
        logger.exception("Fatal error in demucs entrypoint")
        sys.exit(1)


if __name__ == "__main__":
    main()
