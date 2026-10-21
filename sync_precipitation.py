"""Rīga LU CLIDATA HPRAB hourly precipitation sums; independent QC cache."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sync_clidata import DATA_DIR, VALUE_COLUMNS, FLAG_COLUMNS, open_connection

PRECIP_CACHE = DATA_DIR / "RIGASLU_HPRAB.json.gz"
FII_COLUMNS = [f"FII{i:02d}" for i in range(1, 32)]
REJECT_FII = frozenset("ERN?IA")  # CLIDATA QC_FLAGS: erroneous, interpolated, omitted, suspect, corrected, calculated.


def validate_metadata(connection):
    """Fail closed if CLIDATA changes HPRAB identity, unit or source interval."""
    with connection.cursor() as cursor:
        cursor.execute("""SELECT NAME, DESCRIPTION, UN_DESCRIPTION, LOWER_LIMIT, UPPER_LIMIT
                          FROM CLIDATA.ELEMENTS WHERE ABBREVIATION='HPRAB'""")
        element = cursor.fetchone()
        cursor.execute("""SELECT DISTINCT TI_INTERVAL FROM CLIDATA.ST_ELEMENTS
                          WHERE EG_GH_ID='RIGASLU' AND EG_EL_ABBREVIATION='HPRAB'""")
        intervals = {row[0] for row in cursor}
        cursor.execute("""SELECT FLAG, DESCRIPTION FROM CLIDATA.ELEMENTS_FLAGS
                          WHERE EL_ABBREVIATION='HPRAB'""")
        value_flags = {str(flag): str(description) for flag, description in cursor}
    if not element or "hourly sum" not in str(element[0]).lower() or str(element[2]).strip() != "mm":
        raise ValueError("HPRAB stundas summas mērvienība nav apstiprināta CLIDATA.ELEMENTS.")
    if intervals != {"01:00"} or element[3] != 0 or element[4] != 250:
        raise ValueError("HPRAB intervāls vai pieļaujamās robežas CLIDATA metadatos mainījušās.")
    return {"name": str(element[0]), "description": str(element[1]), "unit": "mm",
            "interval": "01:00", "lowerLimit": 0, "upperLimit": 250,
            "valueFlags": value_flags,
            "timestampConvention": "RDATA UTC time label; hourly amount assigned to [label, label + 1h)"}


def parse_hour(raw, flag, quality):
    """Return accepted mm or None; zero is accepted only when explicitly stored."""
    if raw is None:
        return None, "missing"
    if flag is not None and str(flag).strip():
        return None, "valueFlag"
    marks = str(quality or "").upper()
    if any(code in marks for code in REJECT_FII):
        return None, "qualityFlag"
    try:
        value = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(value) or not 0 <= value <= 250:
        return None, "range"
    return round(value, 2), None


def fetch_precipitation(from_year=2005, *, connection=None):
    own_connection = connection is None
    if own_connection:
        connection = open_connection()
    accepted, conflicted, qc = {}, set(), Counter()
    try:
        metadata = validate_metadata(connection)
        query = f"""SELECT YEAR, MONTH, TIME, {', '.join(VALUE_COLUMNS)},
                           {', '.join(FLAG_COLUMNS)}, {', '.join(FII_COLUMNS)}
                    FROM CLIDATA.RDATA
                    WHERE EG_GH_ID='RIGASLU' AND EG_EL_ABBREVIATION='HPRAB'
                      AND REGULAR='Y' AND YEAR >= :year"""
        with connection.cursor() as cursor:
            cursor.arraysize = 500
            cursor.execute(query, {"year": str(from_year)})
            for row in cursor:
                qc["sourceRows"] += 1
                try:
                    year, month = int(row[0]), int(row[1])
                    time_text = str(row[2]).strip()
                    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):?00", time_text):
                        raise ValueError("time")
                    hour = int(time_text[:2])
                except (ValueError, TypeError):
                    qc["invalidTimeRows"] += 1
                    continue
                for day in range(1, 32):
                    raw, flag, quality = row[day + 2], row[day + 33], row[day + 64]
                    value, reason = parse_hour(raw, flag, quality)
                    if reason:
                        qc[reason] += 1
                        continue
                    try:
                        moment = datetime(year, month, day, hour, tzinfo=timezone.utc)
                    except ValueError:
                        qc["invalidDateCells"] += 1
                        continue
                    key = int(moment.timestamp() // 3600)
                    if key in conflicted:
                        continue
                    if key in accepted:
                        if accepted[key] == value:
                            qc["identicalDuplicates"] += 1
                        else:
                            del accepted[key]
                            conflicted.add(key)
                            qc["conflictingHours"] += 1
                    else:
                        accepted[key] = value
    finally:
        if own_connection:
            connection.close()
    qc["acceptedHours"] = len(accepted)
    return accepted, dict(qc), metadata


def read_precip_cache():
    with gzip.open(PRECIP_CACHE, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if (payload.get("station") != "RIGASLU" or payload.get("element") != "HPRAB"
            or payload.get("unit") != "mm" or payload.get("interval") != "01:00"):
        raise ValueError("HPRAB keša identitāte vai mērvienība neatbilst.")
    return {int(hour): float(value) for hour, value in payload["rows"]}, payload


def sync_precipitation(from_year=2005, *, connection=None):
    observations, qc, metadata = fetch_precipitation(from_year, connection=connection)
    if from_year > 2005 and PRECIP_CACHE.is_file():
        previous, _ = read_precip_cache()
        cutoff = int(datetime(from_year, 1, 1, tzinfo=timezone.utc).timestamp() // 3600)
        observations = {hour: value for hour, value in previous.items() if hour < cutoff} | observations
    qc["cachedHours"] = len(observations)
    payload = {"station": "RIGASLU", "element": "HPRAB", "unit": "mm",
               "interval": "01:00", "syncedAt": datetime.now(timezone.utc).isoformat(),
               "metadata": metadata, "qc": qc,
               "rows": [[hour, value] for hour, value in sorted(observations.items())]}
    PRECIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = PRECIP_CACHE.with_suffix(".gz.tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(PRECIP_CACHE)
    return {"cache": str(PRECIP_CACHE), "hours": len(observations), "qc": qc, "metadata": metadata}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync RIGASLU HPRAB hourly sums with QC")
    parser.add_argument("--from-year", type=int, default=2005)
    args = parser.parse_args()
    result = sync_precipitation(args.from_year)
    print(json.dumps(result, ensure_ascii=False), flush=True)
