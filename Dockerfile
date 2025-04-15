# Use official Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY config/ ./config/
COPY run.py .

# Expose metrics port
EXPOSE 9657

# Set environment variables
ENV PYTHONPATH=/app

# Run exporter
CMD ["python", "run.py"]