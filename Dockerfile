# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the project files into the container
COPY pyproject.toml .
COPY README.md .
COPY LICENSE.txt .
COPY src/ ./src/

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# Create directories for configuration and data
RUN mkdir /config /data

# Set environment variables for common defaults
# These can be overridden at runtime
ENV NMEA_LOGGER_DEBUG=1
ENV SQLITE_DATABASE_PATH=/data/nmea_database.sdb

# Define volumes for persistence
# /config: Mount your config.toml here
# /data: Mount a volume for the SQLite database
VOLUME ["/config", "/data"]

# Run the application
ENTRYPOINT ["nmea-logger"]
CMD ["--config", "/config/config.toml"]
