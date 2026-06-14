"""Parse NMEA sentence VLW - Distance travelled through water

For field descriptions: https://gpsd.gitlab.io/gpsd/NMEA.html#_vlw_distance_traveled_through_water
"""
from parse_nmea.__init__ import *


def decode(parts: list[str]) -> NmeaDict:
    data = {
        "water_total_nm": parse_float(parts[1]),
        "water_since_reset_nm": parse_float(parts[3]),
    }
    if len(parts) > 7:
        data["ground_total_nm"] = parse_float(parts[5])
        data["ground_since_reset_nm"] = parse_float(parts[7])
    else:
        data["ground_total_nm"] = None
        data["ground_since_reset_nm"] = None

    return data
