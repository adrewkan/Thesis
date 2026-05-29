FROM python:3.10-slim

WORKDIR /app

# System dependencies
# git is required by some HuggingFace packages
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# ── Install PyTorch with CUDA 12.1 FIRST ────────────────────────────────────
# Must happen before `pip install -r requirements.txt` so pip sees the GPU
# build already installed and does not overwrite it with the CPU-only PyPI build.
# Change cu121 → cu118 if your GPU only supports CUDA 11.8.
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cu121

# ── All other dependencies ───────────────────────────────────────────────────
RUN pip install --no-cache-dir -r requirements.txt

# Copy source into image (volume mount in docker-compose takes precedence at
# runtime, but having the code here makes the image self-contained)
COPY . .

EXPOSE 8501
EXPOSE 8888

CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
