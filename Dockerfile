# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.10.11
FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr.
ENV PYTHONUNBUFFERED=1

# --- CRITICAL CHANGE 1: Set the working directory before user creation ---
# Define the app directory where all files will reside.
WORKDIR /app

# Create a dedicated directory for EasyOCR models.
RUN mkdir -p /app/easyocr_models

# --- CRITICAL CHANGE 2: Modify User Creation for Write Access ---
# The default creation path (/nonexistent) causes EasyOCR to fail because it is not writeable.
# We change the user's home directory (ENV HOME) to /app and ensure /app is owned by the user.
ARG UID=10001
RUN groupadd -g "${UID}" appuser && useradd \
    --uid "${UID}" \
    --gid appuser \
    --shell "/sbin/nologin" \
    --create-home \
    --home "/app" \
    appuser

# --- CRITICAL CHANGE 3: Set environment variable for user's home directory ---
# This explicitly tells Python/EasyOCR where the user's home directory is.
ENV HOME=/app

# Download system dependencies for OpenCV/GLib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    # Clean up APT cache to keep the image small
    && rm -rf /var/lib/apt/lists/*

# Download Python dependencies as a separate step to take advantage of Docker's caching.
# Download Python dependencies
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Copy the source code into the container.
# NOTE: This is done *after* dependency installation for better caching.
COPY parking_proto_sensor.py /app/
COPY templates /app/templates
COPY make_qrs.py /app/

# --- CRITICAL CHANGE 4: Change ownership of all app files to the non-root user ---
# This step MUST be done before switching to the user. 
# It ensures 'appuser' can write to the /app folder (and /app/easyocr_models).
RUN chown -R appuser:appuser /app

# Switch to the non-privileged user to run the application.
USER appuser

# Expose the port that the application listens on.
EXPOSE 5000

# Run the application.
CMD ["python", "parking_proto_sensor.py"]