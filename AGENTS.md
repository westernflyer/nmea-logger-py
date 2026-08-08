# Agent Guide for NMEA Logger Py

This document provides essential information for AI agents (like Junie) working on the `nmea-logger-py` project.

## Project Overview

`nmea-logger-py` is a Python-based utility designed to read NMEA 0183 sentences from one or more TCP sockets, parse
them, publish the results to an MQTT broker as JSON, and store them in a SQLite database.

## Architecture

The project uses `asyncio` for concurrent operations. The main loop (`src/main.py`) coordinates the following components:

- **NMEA Readers**: Connect to TCP sockets and yield NMEA sentences.
- **Parser**: Decodes NMEA sentences into structured data.
- **MQTT Service**: Publishes parsed data to an MQTT broker based on configured intervals.
- **SQLite Service**: Batches parsed data and writes it to a SQLite database.
- **Shared Queues**: `mqtt_queue` and `sqlite_queue` are used to pass data between the readers and the services.

## Key Files and Directories

- `src/main.py`: Entry point and service orchestration.
- `src/parse_nmea/`: Core parsing logic.
  - `decoders/`: Individual NMEA sentence decoders (e.g., `gll.py`, `mwv.py`).
- `src/mqtt_services.py`: MQTT publishing logic.
- `src/sqlite_services.py`: SQLite storage implementation.
- `src/service_utils.py`: Shared utilities for services (e.g., error handling).
- `config.toml`: User configuration (use `config_sample.toml` as a template).
- `Dockerfile`: Container definition.
- `docker-compose.yml`: Example Compose configuration.
- `simulator/`: A tool for generating synthetic NMEA data for testing.

## Common Development Tasks

### Adding a New NMEA Sentence Decoder

1.  Create a new decoder file in `src/parse_nmea/decoders/` (e.g., `zda.py`).
2.  Implement the `decode(parts: list[str])` function in that file, following the pattern in existing decoders.
3.  The parser in `src/parse_nmea/__init__.py` will automatically discover the new decoder using dynamic import based on
    the sentence type.
4.  If the sentence should be stored in SQLite:
    - Add a new entry to `TABLE_SCHEMAS` in `src/sqlite_services.py`.
    - Update `map_fields()` in `src/sqlite_services.py` to map the parsed data to the table columns.
5.  Add tests for the new decoder in `tests/test_parse_nmea.py`.

### SQLITE Schema

The following are common fields for all tables:
-   Timestamps are stored in field `timestamp` in milliseconds since epoch.
-   The NMEA talker is stored in field `talker`.
 
### Modifying SQLite Schema

-   Database initialization and table creation happen in `src/sqlite_services.py` via `TABLE_SCHEMAS`.
-   If you add a new table, ensure it's handled in the `map_fields()` function.

### Troubleshooting Services

-   The application uses `SysLogHandler` on Linux and `TimedRotatingFileHandler` on macOS.
-   In Docker containers or environments without syslog, it falls back to `logging.StreamHandler` (console logging).
-   Check logs for "self-healing" messages if services restart due to errors.

### Docker Networking

-   Containers can reach external LAN IPs (like NMEA gateways) by default.
-   `localhost` in `config.toml` refers to the container itself. To reach a broker on the host, use the host's LAN IP or `host.docker.internal`.
-   On Linux, using `network_mode: host` in `docker-compose.yml` is often the simplest way to ensure full access to LAN resources and the host's services.

## Testing

Testing is done using `pytest`.

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_parse_nmea.py
```

### Simulator

You can use the simulator to test MQTT publishing without a real NMEA source:

```bash
python3 simulator/simulate.py
```

The simulator reads from `config.toml` and generates data for the sentences listed in `[MQTT_PUBLISH_INTERVALS]`.

## Agent Guidelines

- **Asynchronous Code**: Always use `async`/`await` for I/O operations.
- **Error Handling**: Use the retry patterns and `RETRYABLE_ERRORS` defined in `service_utils.py` for network-related tasks.
- **Configuration**: Do not hardcode values; use the `config` dictionary passed to services.
- **Dependency Management**: Update `pyproject.toml` if adding new dependencies.
- **Documentation**: Keep `README.md` and `AGENTS.md` updated with major changes.
