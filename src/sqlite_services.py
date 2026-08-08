#
# Copyright (c) 2025-present Tom Keffer <tkeffer@gmail.com>
#
# This source code is licensed under the MIT license found in the
# LICENSE.txt.txt file in the root directory of this source tree.
#
"""
Provides functionality to handle and publish NMEA sentence data into a SQLite database.

The module organizes NMEA sentence data based on their types and inserts it into
predefined tables in a SQLite database in batches. The schema for each table is
defined based on supported sentence types. It also supports publishing data from
an async queue to the database with configurable batch size and interval.
"""
import asyncio
import logging
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager

from service_utils import RETRYABLE_ERRORS, warn_print_sleep

log = logging.getLogger("nmea-logger.sqlite")

TABLE_SCHEMAS = {
    "DPT": """CREATE TABLE IF NOT EXISTS DPT
              (
                  timestamp                     INTEGER NOT NULL,
                  talker                        TEXT NOT NULL,
                  depth_below_transducer_meters REAL,
                  transducer_depth_meters       REAL,
                  water_depth_meters            REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "GLL": """CREATE TABLE IF NOT EXISTS GLL
              (
                  timestamp INTEGER NOT NULL,
                  talker    TEXT NOT NULL,
                  latitude  REAL,
                  longitude REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "HDT": """CREATE TABLE IF NOT EXISTS HDT
              (
                  timestamp INTEGER NOT NULL,
                  talker    TEXT NOT NULL,
                  hdg_true  REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "MDA": """CREATE TABLE IF NOT EXISTS MDA
              (
                  timestamp                 INTEGER NOT NULL,
                  talker                    TEXT NOT NULL,
                  pressure_millibars        REAL,
                  temperature_air_celsius   REAL,
                  temperature_water_celsius REAL,
                  humidity_relative         REAL,
                  dew_point_celsius         REAL,
                  twd_true                  REAL,
                  twd_magnetic              REAL,
                  tws_knots                 REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "MWV": """CREATE TABLE IF NOT EXISTS MWV
              (
                  timestamp INTEGER NOT NULL,
                  talker    TEXT NOT NULL,
                  awa       REAL,
                  aws_knots REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "ROT": """CREATE TABLE IF NOT EXISTS ROT
              (
                  timestamp    INTEGER NOT NULL,
                  talker       TEXT NOT NULL,
                  rate_of_turn REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "RSA": """CREATE TABLE IF NOT EXISTS RSA
              (
                  timestamp    INTEGER NOT NULL,
                  talker       TEXT NOT NULL,
                  rudder_angle REAL,
                  PRIMARY KEY (timestamp, talker)
              );""",
    "VTG": """CREATE TABLE IF NOT EXISTS VTG
              (
                  timestamp    INTEGER NOT NULL,
                  talker       TEXT NOT NULL,
                  cog_true     REAL,
                  cog_magnetic REAL,
                  sog_knots    REAL,
                  PRIMARY KEY (timestamp, talker)
              );"""
}

def map_fields(sentence_type: str, talker: str, parsed_nmea: dict[str, float | str | None]):
    # TODO: read the ordering from the database schema
    timestamp = parsed_nmea["timestamp"]
    if sentence_type == "DPT":
        return timestamp, talker, parsed_nmea.get(
            "depth_below_transducer_meters"), parsed_nmea.get(
            "transducer_depth_meters"), parsed_nmea.get("water_depth_meters")
    elif sentence_type == "GLL":
        return timestamp, talker, parsed_nmea.get("latitude"), parsed_nmea.get("longitude")
    elif sentence_type == "HDT":
        return timestamp, talker, parsed_nmea.get("hdg_true")
    elif sentence_type == "MDA":
        return timestamp, talker, parsed_nmea.get("pressure_millibars"), parsed_nmea.get(
            "temperature_air_celsius"), parsed_nmea.get(
            "temperature_water_celsius"), parsed_nmea.get("humidity_relative"), parsed_nmea.get(
            "dew_point_celsius"), parsed_nmea.get("twd_true"), parsed_nmea.get(
            "twd_magnetic"), parsed_nmea.get("tws_knots")
    elif sentence_type == "MWV":
        return timestamp, talker, parsed_nmea.get("awa"), parsed_nmea.get("aws_knots")
    elif sentence_type == "ROT":
        return timestamp, talker, parsed_nmea.get("rate_of_turn")
    elif sentence_type == "RSA":
        return timestamp, talker, parsed_nmea.get("rudder_angle")
    elif sentence_type == "VTG":
        return timestamp, talker, parsed_nmea.get("cog_true"), parsed_nmea.get(
            "cog_magnetic"), parsed_nmea.get("sog_knots")
    return None


def write_batch(conn: sqlite3.Connection, batch: list[tuple[str, dict]]) -> None:
    """
    Writes a batch of NMEA sentences to a SQLite database.

    This function processes a list of NMEA sentences and organizes them into
    appropriate database table formats based on their sentence types. The
    data is then inserted into the corresponding tables in a SQLite database
    using a single transaction.

    Parameters:
        conn (sqlite3.Connection): The SQLite connection object used for database
            operations.
        batch (list[tuple[str, dict]]): A list of tuples where each tuple consists
            of an NMEA address field (str) and its parsed data (dict).

    Raises:
        Exception: If any error occurs during the insertion process, the changes
            are rolled back and the exception is re-raised.
    """
    grouped = defaultdict(list)
    for address_field, parsed_nmea in batch:
        talker = address_field[0:2]
        sentence_type = address_field[2:]
        if sentence_type in TABLE_SCHEMAS:
            row = map_fields(sentence_type, talker, parsed_nmea)
            if row:
                grouped[sentence_type].append(row)

    # Don't do anything if there was nothing in the batch:
    if not grouped:
        return

    try:
        # Use the connection as a transaction context manager. The inserts inside will be committed
        # as a single transaction. If there is a failure, they will be rolled back.
        with conn:
            for table_name, rows in grouped.items():
                placeholders = ", ".join(["?"] * len(rows[0]))
                conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
        log.debug(f"Inserted {len(batch)} rows into database.")
    except Exception as e:
        log.error(f"Error inserting batch into SQLite: {e}")
        raise


async def sqlite_publisher_task(db_conn: sqlite3.Connection,
                                queue: asyncio.Queue,
                                config: dict) -> None:
    """
    Publishes data from an asynchronous queue to a SQLite database in batches. The batches
    are configurable in size and interval. The function initializes the database schemas on
    startup.

    The function catches CancelledError exceptions and arranges to drain any remaining items from
    the queue.

    Args:
        db_conn: SQLite database connection.
        queue: The asyncio queue containing items to be batched and inserted into
            the database. Each item represents a single row to be processed.
        config: Configuration dictionary.
    """
    # Initialize schemas
    for schema_sql in TABLE_SCHEMAS.values():
        await asyncio.to_thread(db_conn.execute, schema_sql)

    batch_size = config.get("SQLITE", {}).get("SQLITE_BATCH_SIZE", 100)
    batch_interval = config.get("SQLITE", {}).get("SQLITE_BATCH_INTERVAL", 10)
    log.info(f"Using SQLite batch size {batch_size} and batch interval {batch_interval} seconds.")

    batch = []
    try:
        while True:
            # Get items from the queue until we reach the batch size or batch interval, whichever
            # happens first. Measure elapsed time using the event loop clock, which is guaranteed
            # to increase monotonically (unlike time.time()).
            start_time = asyncio.get_event_loop().time()
            while len(batch) < batch_size:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = batch_interval - elapsed
                if remaining <= 0:
                    break
                try:
                    # In order to honor the batch interval, we need to process the batch
                    # eventually, so set a timeout for the queue get operation.
                    item = await asyncio.wait_for(queue.get(), timeout=remaining)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break

            # Group and insert batch in a single thread-safe transaction
            await asyncio.to_thread(write_batch, db_conn, batch)

            for _ in range(len(batch)):
                queue.task_done()
            batch = []
    except asyncio.CancelledError:
        log.info("SQLite publisher task cancelled. Draining remaining items from the queue.")
        # Drain the remaining items from the queue
        while not queue.empty():
            try:
                item = queue.get_nowait()
                batch.append(item)
            except asyncio.QueueEmpty:
                break
        if batch:
            log.info(f"Draining SQLite queue: writing final {len(batch)} items.")
            await asyncio.to_thread(write_batch, db_conn, batch)
            for _ in range(len(batch)):
                queue.task_done()
        raise


async def sqlite_service(queue: asyncio.Queue, config: dict[str, dict[str, str]]):
    """
    Runs the SQLite service to handle asynchronous database operations and tasks.

    The SQLite service continuously connects to the specified SQLite database file 
    and runs a publisher task to process data using the database. Any retryable 
    errors or unexpected exceptions are logged and handled appropriately. The 
    service operates on an asynchronous loop until explicitly cancelled.

    Parameters:
    queue: The asyncio queue for handling asynchronous task communication.
    config: A dictionary containing configuration settings, including database path and other
        service-related parameters.

    Raises:
    asyncio.CancelledError: Raised when the service loop is cancelled.
    RETRYABLE_ERRORS: Raised when encountering retryable errors during execution.
    Exception: Raised for unexpected errors that occur during service operation.
    """
    sqlite_database_path = config.get('SQLITE', {}).get("SQLITE_DATABASE_PATH", "nmea_database.sdb")
    while True:
        try:
            async with sqlite_connection(sqlite_database_path) as sqlite_conn:
                await sqlite_publisher_task(sqlite_conn, queue, config)
        except asyncio.CancelledError:
            break
        except RETRYABLE_ERRORS as e:
            await warn_print_sleep(str(e), config, prefix="SQLite service")
        except Exception as e:
            log.exception("Unexpected error in SQLite service")
            await warn_print_sleep(str(e), config, prefix="SQLite service")


@asynccontextmanager
async def sqlite_connection(database_path):
    conn = await asyncio.to_thread(sqlite3.connect, database_path, check_same_thread=False)
    try:
        yield conn
    finally:
        log.info("Closing SQLite connection.")
        await asyncio.to_thread(conn.close)
