import asyncio
import sqlite3
import pytest

import sqlite_services
import main


@pytest.mark.asyncio
async def test_schema_creation(tmp_path):
    db_path = str(tmp_path / "test_nmea.db")
    main.config = {
        "MMSI": "368323170",
        "SQLITE": {
            "SQLITE_DATABASE_PATH": db_path,
            "SQLITE_BATCH_SIZE": 1,
            "SQLITE_BATCH_INTERVAL": 10
        }
    }

    queue = asyncio.Queue()

    # Start publisher task
    conn = sqlite3.connect(db_path, check_same_thread=False)
    task = asyncio.create_task(sqlite_services.sqlite_publisher_task(conn, queue, main.config))

    # Allow some time for table creation/initialization
    await asyncio.sleep(0.2)

    # Cancel the task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    conn.close()

    # Verify tables in the database file
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    expected_tables = ["DPT", "GLL", "HDT", "MDA", "MWV", "ROT", "RSA", "VTG"]
    for t in expected_tables:
        assert t in tables

    # Verify columns in GLL
    cursor = conn.execute("PRAGMA table_info('GLL')")
    columns = cursor.fetchall()
    # columns format: (cid, name, type, notnull, dflt_value, pk)
    col_names = [col[1] for col in columns]
    assert col_names == ["timestamp", "talker", "latitude", "longitude"]

    conn.close()


@pytest.mark.asyncio
async def test_size_based_flushing(tmp_path):
    db_path = str(tmp_path / "test_size.db")
    main.config = {
        "MMSI": "368323170",
        "SQLITE": {
            "SQLITE_DATABASE_PATH": db_path,
            "SQLITE_BATCH_SIZE": 3,
            "SQLITE_BATCH_INTERVAL": 10
        }
    }

    queue = asyncio.Queue()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    task = asyncio.create_task(sqlite_services.sqlite_publisher_task(conn, queue, main.config))

    # Feed 3 items
    data = [
        ("GPGLL", {"latitude": 44.623, "longitude": -124.05156, "timestamp": 1778857043108}),
        ("GPGLL", {"latitude": 44.624, "longitude": -124.05157, "timestamp": 1778857043109}),
        ("GPGLL", {"latitude": 44.625, "longitude": -124.05158, "timestamp": 1778857043110}),
    ]
    for item in data:
        await queue.put(item)

    # Queue should be processed almost instantly due to batch size 3
    try:
        await asyncio.wait_for(queue.join(), timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Queue join timed out - batch was not flushed instantly")

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    conn.close()

    # Verify items are in the GLL table
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.execute("SELECT * FROM GLL")
    rows = cursor.fetchall()
    assert len(rows) == 3
    assert rows[0][1] == "GP"
    assert rows[0][2] == 44.623
    assert rows[0][3] == -124.05156
    conn.close()


@pytest.mark.asyncio
async def test_interval_based_flushing(tmp_path):
    db_path = str(tmp_path / "test_interval.db")
    main.config = {
        "MMSI": "368323170",
        "SQLITE": {
            "SQLITE_DATABASE_PATH": db_path,
            "SQLITE_BATCH_SIZE": 10,
            "SQLITE_BATCH_INTERVAL": 0.5
        }
    }

    queue = asyncio.Queue()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    task = asyncio.create_task(sqlite_services.sqlite_publisher_task(conn, queue, main.config))

    # Feed 2 items
    data = [
        ("GPGLL", {"latitude": 44.623, "longitude": -124.05156, "timestamp": 1778857043108}),
        ("GPGLL", {"latitude": 44.624, "longitude": -124.05157, "timestamp": 1778857043109}),
    ]
    for item in data:
        await queue.put(item)

    # Wait for the batch interval (0.5s) to trigger the flush
    try:
        await asyncio.wait_for(queue.join(), timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Queue join timed out - interval flush did not occur")

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    conn.close()

    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.execute("SELECT * FROM GLL")
    rows = cursor.fetchall()
    assert len(rows) == 2
    conn.close()


@pytest.mark.asyncio
async def test_sentence_field_mapping(tmp_path):
    db_path = str(tmp_path / "test_mapping.db")
    main.config = {
        "MMSI": "368323170",
        "SQLITE": {
            "SQLITE_DATABASE_PATH": db_path,
            "SQLITE_BATCH_SIZE": 1,
            "SQLITE_BATCH_INTERVAL": 10
        }
    }

    queue = asyncio.Queue()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    task = asyncio.create_task(sqlite_services.sqlite_publisher_task(conn, queue, main.config))

    # Test 1: MWV sentence
    # Apparent Wind Speed & Angle
    mwv_data = ("WIMWV", {"awa": 240.5, "aws_knots": 12.3, "timestamp": 1778857043110})
    await queue.put(mwv_data)
    await asyncio.wait_for(queue.join(), timeout=1.0)

    # Test 2: MDA sentence
    # Met composite data
    mda_data = ("IIMDA", {
        "pressure_millibars": 1013.25,
        "temperature_air_celsius": 15.6,
        "temperature_water_celsius": 12.1,
        "humidity_relative": 85.0,
        "dew_point_celsius": 13.0,
        "twd_true": 180.0,
        "twd_magnetic": 165.0,
        "tws_knots": 15.5,
        "timestamp": 1778857043111
    })
    await queue.put(mda_data)
    await asyncio.wait_for(queue.join(), timeout=1.0)

    # Test 3: VTG sentence
    vtg_data = ("GPVTG", {
        "cog_true": 230.1,
        "cog_magnetic": 215.0,
        "sog_knots": 6.8,
        "timestamp": 1778857043112
    })
    await queue.put(vtg_data)
    await asyncio.wait_for(queue.join(), timeout=1.0)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    conn.close()

    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Check MWV
    cursor = conn.execute("SELECT * FROM MWV")
    mwv_rows = cursor.fetchall()
    assert len(mwv_rows) == 1
    assert mwv_rows[0][1] == "WI"
    assert mwv_rows[0][2] == 240.5
    assert mwv_rows[0][3] == 12.3

    # Check MDA
    cursor = conn.execute("SELECT * FROM MDA")
    mda_rows = cursor.fetchall()
    assert len(mda_rows) == 1
    assert mda_rows[0][1] == "II"
    assert mda_rows[0][2] == 1013.25
    assert mda_rows[0][3] == 15.6
    assert mda_rows[0][4] == 12.1
    assert mda_rows[0][5] == 85.0
    assert mda_rows[0][6] == 13.0
    assert mda_rows[0][7] == 180.0
    assert mda_rows[0][8] == 165.0
    assert mda_rows[0][9] == 15.5

    # Check VTG
    cursor = conn.execute("SELECT * FROM VTG")
    vtg_rows = cursor.fetchall()
    assert len(vtg_rows) == 1
    assert vtg_rows[0][1] == "GP"
    assert vtg_rows[0][2] == 230.1
    assert vtg_rows[0][3] == 215.0
    assert vtg_rows[0][4] == 6.8

    conn.close()


@pytest.mark.asyncio
async def test_sqlite_drain_on_cancel(tmp_path):
    db_path = str(tmp_path / "test_drain.db")
    config = {
        "SQLITE": {
            "SQLITE_DATABASE_PATH": db_path,
            "SQLITE_BATCH_SIZE": 100,
            "SQLITE_BATCH_INTERVAL": 100
        }
    }
    queue = asyncio.Queue()
    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Put some items in the queue
    for i in range(10):
        await queue.put(("GPGLL", {"latitude": 44.0 + i / 100, "longitude": -124.0, "timestamp": 1700000000000 + i}))

    # Start the task
    task = asyncio.create_task(sqlite_services.sqlite_publisher_task(conn, queue, config))

    # Wait a bit to make sure it started and is waiting for more items (since BATCH_SIZE=100)
    await asyncio.sleep(0.1)

    # Cancel the task. This should trigger the drain.
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify that the 10 items were written
    cursor = conn.execute("SELECT count(*) FROM GLL")
    rows = cursor.fetchone()[0]
    assert rows == 10

    # Also verify queue.join() would have worked
    await asyncio.wait_for(queue.join(), timeout=1.0)

    conn.close()
