# NMEA Simulator

This directory contains a simulator that generates synthetic NMEA 0183 sentences and publishes them to an MQTT broker. 
It uses the same data structures and configuration as the main `nmea-logger` program.

## Usage

To run the simulator:

```bash
python3 simulator/sim_mqtt.py
```

The simulator reads its configuration from `config.py` in the parent directory. It will generate data for all sentence types listed in `PUBLISH_INTERVALS` and publish them every 10 seconds.

## Requirements

- Python 3
- `paho-mqtt` library
