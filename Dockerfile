# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Copy source code and run script
COPY src/ ./src/
COPY run.py .
COPY setup.py .

EXPOSE 9658

# Environment variable (optional but can help in some cases)
ENV PYTHONPATH=/app

CMD ["python", "run.py"]