FROM python:3.12-slim

WORKDIR /app

# Prevent .pyc files and enable stdout/stderr flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system deps needed by psycopg2 build tools (slim image lacks them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install torch CPU-only BEFORE requirements.txt to avoid the ~2 GB GPU build.
# CPU-only wheel : ~750 MB (vs ~2 GB CUDA). Sufficient for sentence-transformers inference.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code is mounted as a volume in dev; COPY covers production builds
COPY . .

# Hot reload via uvicorn --reload watches /app (mounted volume in dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
