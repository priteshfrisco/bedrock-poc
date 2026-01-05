# Dockerfile for Bedrock AI Data Enrichment Pipeline
# Multi-stage build for smaller final image

FROM python:3.13-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.13-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/
COPY reference_data/ ./reference_data/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set Python path
ENV PYTHONPATH=/app

# Create directories for data
RUN mkdir -p /app/data/input /app/data/output /app/data/audit /app/data/logs /app/data/tracking

# Run as non-root user (security best practice)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Default command runs in AWS mode
# Override with --mode local for local processing
CMD ["python", "src/main.py", "--mode", "aws"]

