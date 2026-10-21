"""Read regular CLIDATA HTDRY through the existing REPORT_INTERPOL connection.

Only accepted, distinct UTC hourly values are cached. No credentials live here.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "stations"
RIGA_CACHE = DATA_DIR / "RIGASLU.json.gz"


def load_local_env():
    """Load only CLIDATA settings from ignored .env, without printing secrets."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"CLIDATA_USER", "CLIDATA_PASSWORD", "CLIDATA_DSN", "CLIDATA_REFERENCE"}:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_local_env()
REFERENCE = Path(os.environ.get(
    "CLIDATA_REFERENCE",
    str(Path.home() / "EUROPEGRID" / "PIPELINE" / "file_generator_month_2025.py"),
))
VALUE_COLUMNS = [f"VAL{i:02d}" for i in range(1, 32)]
FLAG_COLUMNS = [f"FI{i:02d}" for i in range(1, 32)]


def open_connection():
    if all(os.environ.get(key) for key in ("CLIDATA_USER", "CLIDATA_PASSWORD", "CLIDATA_DSN")):
        import oracledb
        return oracledb.connect(user=os.environ["CLIDATA_USER"],
                                password=os.environ["CLIDATA_PASSWORD"],
                                dsn=os.environ["CLIDATA_DSN"])
    if not REFERENCE.is_file():
        raise FileNotFoundError("CLIDATA .env settings or private connection helper not found")
    spec = importlib.util.spec_from_file_location("clidata_reference", REFERENCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module._open_oracle()


def cache_path(station):
    if station != "RIGASLU":
        raise ValueError("Only RIGASLU is supported")
    return RIGA_CACHE


def fetch_observations(station="RIGASLU", from_year=1998, *, connection=None):
    """Return accepted hours and counts of rejected raw cells.

    FI codes are conservatively excluded if present. FII and VALIDATION are
    intentionally not interpreted: their code meanings are undocumented here.
    """
    cache_path(station)
    own_connection = connection is None
    if own_connection:
        connection = open_connection()
    values = {}
    conflicted = set()
    qc = Counter()
    query = f"""
        SELECT YEAR, MONTH, TIME, {', '.join(VALUE_COLUMNS)}, {', '.join(FLAG_COLUMNS)}
        FROM CLIDATA.RDATA
        WHERE EG_GH_ID = :station AND EG_EL_ABBREVIATION = 'HTDRY'
          AND REGULAR = 'Y' AND YEAR >= :from_year
    """
    try:
        with connection.cursor() as cursor:
            cursor.arraysize = 500
            cursor.execute(query, {"station": station, "from_year": str(from_year)})
            for row in cursor:
                qc["sourceRows"] += 1
                try:
                    year, month = int(row[0]), int(row[1])
                    time_text = str(row[2]).strip()
                    if not re.fullmatch(r"(?:[01][0-9]|2[0-3])(?::?00)?", time_text):
                        raise ValueError("invalid time")
                    hour = int(time_text[:2])
                except (ValueError, TypeError):
                    qc["invalidTimeRows"] += 1
                    continue
                for day, (raw, flag) in enumerate(zip(row[3:34], row[34:65]), 1):
                    if raw is None:
                        continue
                    qc["nonNullCells"] += 1
                    if flag is not None and str(flag).strip():
                        qc["flaggedCells"] += 1
                        continue
                    try:
                        value = float(str(raw).strip().replace(",", "."))
                        moment = datetime(year, month, day, hour, tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        qc["invalidCells"] += 1
                        continue
                    if not math.isfinite(value) or not -55 <= value <= 55:
                        qc["outOfRangeCells"] += 1
                        continue
                    key = int(moment.timestamp() // 3600)
                    if key in conflicted:
                        continue
                    value = round(value, 2)
                    if key in values:
                        if values[key] != value:
                            del values[key]
                            conflicted.add(key)
                            qc["conflictingHours"] += 1
                        else:
                            qc["identicalDuplicates"] += 1
                    else:
                        values[key] = value
    finally:
        if own_connection:
            connection.close()
    qc["acceptedHours"] = len(values)
    return values, dict(qc)


def read_cache(station):
    with gzip.open(cache_path(station), "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("station") != station or payload.get("element") != "HTDRY":
        raise ValueError(f"Unexpected cache identity: {station}")
    return {int(hour): float(value) for hour, value in payload["rows"]}, payload.get("qc", {})


def write_cache(station, observations, qc):
    path = cache_path(station)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "station": station, "element": "HTDRY", "unit": "°C",
        "timezone": "UTC", "syncedAt": datetime.now(timezone.utc).isoformat(),
        "qc": qc,
        "rows": [[hour, value] for hour, value in sorted(observations.items())],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(payload, stream, separators=(",", ":"), ensure_ascii=False)
    temporary.replace(path)
    return path


def sync_station(station, from_year=1998, *, connection=None):
    observations, qc = fetch_observations(station, from_year, connection=connection)
    if from_year > 1998 and cache_path(station).is_file():
        old, _ = read_cache(station)
        cutoff = int(datetime(from_year, 1, 1, tzinfo=timezone.utc).timestamp() // 3600)
        observations = {hour: value for hour, value in old.items() if hour < cutoff} | observations
    qc["cachedHours"] = len(observations)
    path = write_cache(station, observations, qc)
    return {"station": station, "hours": len(observations), "qc": qc, "cache": str(path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync QC-filtered Rīgas LU CLIDATA HTDRY observations")
    parser.add_argument("--station", choices=["RIGASLU"], default="RIGASLU")
    parser.add_argument("--from-year", type=int, default=1998)
    args = parser.parse_args()
    with open_connection() as connection:
        result = sync_station(args.station, args.from_year, connection=connection)
        print(json.dumps(result, ensure_ascii=False), flush=True)
