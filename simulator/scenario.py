"""Select persistent synthetic M7 scenarios; normal sampling/upload continues."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from simulator.buffer import DEVICE_IDS, connect, initialize

PATIENTS = dict(zip(("mira", "aryan", "lena"), DEVICE_IDS))
SCENARIOS = ("stable", "deterioration", "recovery", "missing")


def select(connection: sqlite3.Connection, device: UUID, name: str) -> None:
    if device not in DEVICE_IDS or name not in SCENARIOS:
        raise ValueError("Unknown demo device or scenario")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DELETE FROM alert_demo WHERE device_id=?", (str(device),))
        connection.execute("INSERT INTO scenarios VALUES (?,?) ON CONFLICT(device_id) "
                           "DO UPDATE SET name=excluded.name", (str(device), name))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient", choices=PATIENTS)
    parser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args()
    with closing(connect(Path(os.environ["BUFFER_PATH"]))) as connection:
        initialize(connection)
        select(connection, PATIENTS[args.patient], args.scenario)
    print(f"{args.patient}: {args.scenario} (synthetic demonstration settings)")


if __name__ == "__main__":
    main()
