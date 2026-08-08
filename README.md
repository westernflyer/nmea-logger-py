# NMEA 0183 Logger and MQTT Publisher

Read NMEA 0183 sentences from one or more sockets, parse them, then publish to
MQTT as JSON, and store to a SQLite database.

## Socket input

One or more sockets can be monitored. See option `NMEA_SOCKETS` under the
`[NMEA_OPTIONS]` section in `config.toml`.

The input is expected to be standard NMEA sentences, possibly with a checksum.
For example,

```
$GPGLL,4202.8367,N,12416.0404,W,123408.8,A,D*44
$SDDBT,347.24,f,105.84,M,57.87,F*05
$GPDTM,W84,,0.0000,N,0.0000,E,0,W84*71
$HETHS,327,D*30
$WIMWV,20.4,R,3.19,N,A*2E
$IIVHW,327,T,308.4,M,,N,,K*42
$IIVBW,,,V,-0,-0.01,A,,V,0,A*5C
...
```

## MQTT output

As an example of what gets published to MQTT, let's look at NMEA address field
`GPGLL`. It will get published as topic `nmea/MMSI/GPGLL`, where `MMSI` is the
MMSI number of the boat. The message will look something like:

    {
    "latitude": 22.929,
    "longitude": -109.755,
    "timeUTC": "23:55:31",
    "gll_mode": "D",
    "sentence_type": "GLL",
    "timestamp": 1743983731183
    }

There is a hack in the code for the FT602 anemometer. If an address field of
`WIMWV` is received from port 60002, it will be changed to `FTMWV` to
disambiguate it from sentences being sent by the Airmar 200WX.

## SQLite database

Parsed NMEA data is also written to a SQLite database.

Example configuration:

```toml
[SQLITE]
SQLITE_DATABASE_PATH = "nmea_database.db"
SQLITE_BATCH_SIZE = 100
SQLITE_BATCH_INTERVAL = 10
```

The data is grouped by sentence type and written using batch insertions whose
size and frequency can be set. The database contains eight distinct tables, one
for each supported NMEA sentence type (`DPT`, `GLL`, `HDT`, `MDA`, `MWV`, `ROT`,
`RSA`, `VTG`). Naive UTC timestamps are stored under the `timestamp` column in
milliseconds since the epoch.

Here is the schema for the `GLL` table. Other tables are similar.

```sql
CREATE TABLE IF NOT EXISTS GLL
(
    timestamp INTEGER NOT NULL,
    talker    TEXT    NOT NULL,
    latitude  REAL,
    longitude REAL,
    PRIMARY KEY (timestamp, talker)
);
```

## Requirements

- An MQTT broker.
- Python v3.12 or greater. Earlier versions cannot be used due to how parameter
  types have been specified, and how `asyncio` raises `Timeout`
  exceptions.
- `git`
- Root privileges to install (but not to run).

## Installation

1. Create the user `nmea` and set a password:

    ```
    sudo useradd -m -c"Owns the nmea-logger process" -s /bin/bash nmea
    sudo passwd nmea
   ```

2. Log in as that user, then clone the Git repository. The following will place
   the repository at `~nmea/git/nmea-logger-py`. Adjust the path to your
   preference, but make sure you use it consistently in what follows.

    ```
    cd ~
    mkdir git
    cd git
    git clone https://github.com/westernflyer/nmea-logger-py
    ```

3. Create a Python virtual environment, activate it, then install requirements

    ```
    cd ~/git/nmea-logger-py
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```

4. Copy a configuration file into place, then edit it with your requirements.

   ```
   cd ~/git/nmea-logger-py
   cp config_sample.toml config.toml
   nano config.toml
   ```

5. Time to install a systemd service file. Log into an account that has root
   privileges. Copy the provided systemd service file into place, then edit it
   appropriately. In particular, make sure the entries for `WorkingDirectory`
   and
   `ExecStart` reflect your choices.

   ```
   cd ~nmea/git/nmea-logger-py/systemd
   sudo cp nmea-logger.service /etc/systemd/system
   sudo nano /etc/systemd/system/nmea-logger.service
   ```

6. Reload the systemd manager to reflect your changes, then start the
   `nmea-logger` daemon. Finally, enable the daemon so it will automatically 
   start when the system boots.

   ```
   sudo systemctl daemon-reload
   sudo systemctl start nmea-logger
   sudo systemctl enable nmea-logger
   ```

## Running with Docker

You can also run `nmea-logger` using Docker. This is nice for isolating it from
your host system.

### Using Docker Compose (Recommended)

1. Create a `config.toml` by copying the sample:
   ```bash
   cp config_sample.toml config.toml
   ```

2. Edit `config.toml` to match your environment. If you are running an MQTT
   broker in another container, use its service name or IP address.

3. Start the container:
   ```bash
   docker compose up -d
   ```

### Using Docker CLI

1. Build the image:
   ```bash
   docker build -t nmea-logger .
   ```
2. Run the container:
   ```bash
   docker run -d \
     --name nmea-logger \
     -v $(pwd)/config.toml:/config/config.toml:ro \
     -v $(pwd)/data:/data \
     -e NMEA_LOGGER_DEBUG=1 \
     nmea-logger
   ```

### Docker Networking

When running in a Docker container, there are a few networking considerations:

- **Reaching LAN IPs**: The container can typically reach external LAN IPs (like
  `192.168.2.226`) without a problem.
- **The `localhost` Pitfall**: If your MQTT broker is running on the host
  machine (not in a container), setting `MQTT_BROKER = "localhost"` in
  `config.toml` will **not** work, as `localhost` inside the container refers to
  the container itself.
    - On Linux, you can use the host's LAN IP address or use
      `network_mode: host` in `docker-compose.yml`.
    - On macOS or Windows, you can use `host.docker.internal`.
- **Host Networking (Linux only)**: For the best performance and to avoid any
  routing issues when accessing NMEA devices on your local network, you can use
  host networking. In your `docker-compose.yml`, add `network_mode: host` to the
  service definition. Note that when using host networking, port mappings and
  custom networks are ignored.

### Accessing the Database

The SQLite database is stored in the container at `/data/nmea_database.sdb`.
Here are the ways to access it from your host machine:

#### 1. Bind Mount (Default in Docker Compose)

The provided `docker-compose.yml` maps the local `./data` directory to the
container's `/data` directory:

```yaml
    volumes:
      - ./config.toml:/config/config.toml:ro
      - ./data:/data
```

The database file will be available at `./data/nmea_database.sdb` on your host
machine.

#### 2. Copy from Container

If you are not using a bind mount, you can copy the database file out of a
running container:

```bash
docker cp nmea-logger:/data/nmea_database.sdb ./nmea_database.sdb
```

#### 3. Inspect Named Volume

If you have switched to using a named volume, you can find its location on the
host (usually `/var/lib/docker/volumes/...`):

```bash
docker volume inspect nmea-logger_nmea_data
```

## Configuration via Environment Variables

The following environment variables can be used to override settings in
`config.toml`:

- `NMEA_LOGGER_DEBUG`: Set to `1` for debug logging, `0` for info.
- `SQLITE_DATABASE_PATH`: Path to the SQLite database file inside the container
  (default: `/data/nmea_database.sdb`).

## Copyright

Copyright (c) 2025-present Tom Keffer <tkeffer@gmail.com>

See the file LICENSE.txt for your rights.