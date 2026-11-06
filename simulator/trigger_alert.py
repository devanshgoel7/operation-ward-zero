"""Queue a short oxygen-saturation scenario for the running demo monitor."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from simulator.buffer import DEVICE_IDS, connect


def queue_alert(connection: sqlite3.Connection, device_id: UUID) -> bool:
    # One statement reserves the next generated sequence, even while sampling.
    result = connection.execute("""
        INSERT OR IGNORE INTO alert_demo (device_id, first_sequence)
        SELECT ?, COALESCE(MAX(sequence), 0) + 1 FROM frames WHERE device_id = ?
    """, (str(device_id), str(device_id)))
    return result.rowcount == 1


def main() -> None:
    devices = dict(zip(("mira", "aryan", "lena"), DEVICE_IDS, strict=True))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient", nargs="?", choices=devices)
    patient = parser.parse_args().patient
    with closing(connect(Path(os.environ["BUFFER_PATH"]))) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if patient is None:
                index = connection.execute("SELECT next_index FROM demo_rotation").fetchone()[0]
                patient = tuple(devices)[index]
            queued = queue_alert(connection, devices[patient])
            if queued:
                index = tuple(devices).index(patient)
                connection.execute("UPDATE demo_rotation SET next_index = ?", ((index + 1) % len(devices),))
    if queued:
        print(f"{patient.title()}: queued three samples at 93% followed by three at 88%, then baseline.")
    else:
        print(f"{patient.title()}: scenario already in progress.")


if __name__ == "__main__":
    main()
