FROM python:3.12-slim

WORKDIR /app

# System deps (ffmpeg required by demucs for audio I/O)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch first (saves ~1.8GB vs CUDA build)
RUN pip install --no-cache-dir \
    torch torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Demucs + boto3 + torchcodec (torchaudio needs torchcodec to save WAV files)
RUN pip install --no-cache-dir demucs boto3 torchcodec

# Set model cache location before pre-download
ENV TORCH_HOME=/app/.cache/torch

# Pre-download htdemucs_ft model weights (no audio file needed)
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs_ft')"

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy application code (flat layout: shared/ alongside entrypoint.py)
COPY containers/shared/ /app/shared/
COPY containers/demucs/entrypoint.py /app/entrypoint.py

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app /tmp
USER appuser

ENTRYPOINT ["python", "/app/entrypoint.py"]
