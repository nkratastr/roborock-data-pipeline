FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create config directory (for mounting credentials)
RUN mkdir -p /app/config

# Default: run smart sync every 12 hours
ENV ROBOROCK_EMAIL=""
ENV SYNC_INTERVAL=43200

# Run scheduled sync by default
CMD ["python", "pipeline.py", "--mode", "schedule"]
