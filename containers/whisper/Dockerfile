FROM python:3.12-slim

WORKDIR /app

# System deps (ffmpeg required by faster-whisper for audio decoding)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# faster-whisper (CTranslate2 backend — no PyTorch needed) + boto3
RUN pip install --no-cache-dir faster-whisper boto3

# Set model cache location before pre-download
ENV HF_HOME=/app/.cache/huggingface

# Pre-download Whisper base model weights
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy application code (flat layout: shared/ alongside entrypoint.py)
COPY containers/shared/ /app/shared/
COPY containers/whisper/entrypoint.py /app/entrypoint.py

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app /tmp
USER appuser

ENTRYPOINT ["python", "/app/entrypoint.py"]
