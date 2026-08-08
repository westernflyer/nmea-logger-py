# 1.8.1
Avoid errors when attempting to write to `/dev/log` when using Docker.

# 1.8.0
Added Docker support and comprehensive documentation for containerized deployment.
Improved environment-aware configuration and logging for better container compatibility.
Added Docker networking guide for reaching LAN NMEA devices.
Fixed `ModuleNotFoundError` when running in Docker.

# 1.7.1
Fixed potential errors in `VLW` and `RMC` parsers.

# 1.7.0
Added support for the DuckDB "Quack" protocol.

# 1.6.0
Changed name to `nmea-logger-py`.

# 1.5.0
Wait for the DuckDB queue to drain before exiting.

# 1.4.0
Make recovery more robust and consistent between MQTT and DuckDB.

# 1.3.0
Switch from InfluxDB to DuckDB. InfluxDB had too many limitations.

# 1.2.0
Writes to the InfluxDB database are now batched in order to improve performance.

# 1.1.0
Changed the schema to something less sparse. The sentence type is now used as 
the table name.

# 1.0.0
Added support for InfluxDB V3