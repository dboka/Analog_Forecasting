"""Export a credential-free GitHub Pages snapshot from the local QC caches.

Run after local CLIDATA sync. The output contains derived RIGASLU API responses,
never database connection settings or the raw hourly cache files.
"""

from __future__ import annotations

import json
import hashlib
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from model import (RIGA, RIGA_STATION_ID, build_day_index, make_forecast,
                   make_month_overview, make_october_analogues)
from precipitation import make_precip_forecast, make_precip_october
from sync_clidata import read_cache
from sync_precipitation import read_precip_cache


ROOT = Path(__file__).resolve().parent
SITE = (ROOT / "site").resolve()


def save_json(relative_path, value):
    path = SITE / "api" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def build(today=None):
    today = today or datetime.now(RIGA).date()
    if SITE.parent != ROOT or SITE.name != "site":
        raise ValueError("Refusing to replace a directory outside this project")
    riga, _ = read_cache(RIGA_STATION_ID)
    precip, _ = read_precip_cache()
    fingerprint = hashlib.sha256()
    for label, values in (("HTDRY", riga), ("HPRAB", precip)):
        fingerprint.update(label.encode())
        fingerprint.update(json.dumps(sorted(values.items()), separators=(",", ":")).encode())
    for source in sorted((ROOT / "public").iterdir()):
        if source.is_file():
            fingerprint.update(source.name.encode())
            fingerprint.update(source.read_bytes())
    for name in ("model.py", "precipitation.py", "build_static_site.py"):
        fingerprint.update((ROOT / name).read_bytes())
    input_hash = fingerprint.hexdigest()
    old_status = SITE / "api" / "status.json"
    if old_status.is_file():
        try:
            previous = json.loads(old_status.read_text(encoding="utf-8"))
            if previous.get("today") == today.isoformat() and previous.get("inputHash") == input_hash:
                result = {"site": str(SITE), "snapshotDate": today.isoformat(), "unchanged": True}
                print(json.dumps(result, ensure_ascii=False))
                return result
        except (ValueError, OSError):
            pass
    days, pairs = build_day_index({RIGA_STATION_ID: riga})
    precip_days, precip_pairs = build_day_index({RIGA_STATION_ID: precip})
    names = {RIGA_STATION_ID: "Rīga LU"}
    review_year = today.year if today.month >= 10 else today.year - 1
    review_month = f"{review_year}-10"

    # Prepare all calculations before replacing the published snapshot.
    month = make_month_overview(riga, review_year, 10, today, days, pairs, names)
    forecast_days = {date.fromisoformat(item["date"]) for item in month["days"]
                     if item["status"] not in {"future", "unavailable"}}
    forecast_days.add(today)
    temperature_forecasts = {}
    precipitation_forecasts = {}
    for forecast_day in sorted(forecast_days):
        try:
            temperature_forecasts[forecast_day] = make_forecast(
                riga, forecast_day - timedelta(days=1), days, pairs, names)
        except ValueError:
            pass
        try:
            precipitation_forecasts[forecast_day] = make_precip_forecast(
                precip, precip_days, precip_pairs, forecast_day, today)
        except ValueError:
            pass
    if today not in temperature_forecasts or today not in precipitation_forecasts:
        raise ValueError("Today's complete input day is missing; keep the previous published snapshot")

    october = {(period, method): make_october_analogues(
        days, review_year, today, period, method)
        for period in ("all", "10", "7")
        for method in ("temperature", "profile", "regime")}
    precipitation_october = {(period, method): make_precip_october(
        precip_days, review_year, today, period, method)
        for period in ("all", "10", "7")
        for method in ("amount", "episodes", "rhythm")}

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    for source in (ROOT / "public").iterdir():
        if source.is_file():
            shutil.copy2(source, SITE / source.name)
    snapshot_time = datetime.now(RIGA).strftime("%d.%m.%Y %H:%M")
    html = (SITE / "index.html").read_text(encoding="utf-8")
    html = html.replace("<title>Weather Scanner · Rīga LU</title>",
                        "<title>Analog Forecasting | Rīgas LU temperatūras un nokrišņu analogi</title>")
    html = html.replace("<body>", "<body>\n"
        "  <script>window.WEATHER_STATIC_SNAPSHOT = true;</script>\n"
        f'  <div class="snapshot-banner">ANALOG FORECASTING · DATU IZGRIEZUMS ATJAUNOTS {snapshot_time} '
        '(RĪGA). MĒRĪJUMI MAINĀS PĒC NĀKAMĀS PUBLICĒŠANAS.</div>')
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / "style.css").write_text(
        (SITE / "style.css").read_text(encoding="utf-8") +
        "\n.snapshot-banner{padding:10px 18px;text-align:center;background:#173342;"
        "color:#aee8dc;font:11px 'DM Mono',monospace;letter-spacing:.08em;}\n",
        encoding="utf-8")
    (SITE / ".nojekyll").touch()
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://dboka.github.io/Analog_Forecasting/sitemap.xml\n",
        encoding="utf-8")
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://dboka.github.io/Analog_Forecasting/</loc></url></urlset>\n',
        encoding="utf-8")

    status = {"station": "Rīga LU", "stationId": RIGA_STATION_ID,
              "element": "HTDRY", "today": today.isoformat(),
              "reviewMonth": review_month, "snapshotAt": snapshot_time,
              "inputHash": input_hash,
              "snapshotFirstPrecipDate": min(precipitation_forecasts).isoformat()}
    save_json("status.json", status)
    save_json(f"month/{review_month}.json", month)
    for day, value in temperature_forecasts.items():
        save_json(f"forecast/{day.isoformat()}.json", value)
    for day, value in precipitation_forecasts.items():
        save_json(f"precipitation/forecast/{day.isoformat()}.json", value)
    for (period, method), value in october.items():
        save_json(f"october/{period}/{method}.json", value)
    for (period, method), value in precipitation_october.items():
        save_json(f"precipitation/october/{period}/{method}.json", value)
    result = {"site": str(SITE), "snapshotDate": today.isoformat(),
              "temperatureForecasts": len(temperature_forecasts),
              "precipitationForecasts": len(precipitation_forecasts),
              "octoberVariants": len(october) + len(precipitation_october)}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    build()
