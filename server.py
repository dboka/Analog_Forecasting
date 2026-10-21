"""Local only Rīga LU 24h analogue pilot. Run: python server.py"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from model import (RIGA, RIGA_STATION_ID, build_day_index, make_forecast,
                   make_month_overview, make_october_analogues)
from sync_clidata import cache_path, read_cache, sync_station
from sync_precipitation import PRECIP_CACHE, read_precip_cache, sync_precipitation
from precipitation import make_precip_october, make_precip_forecast, backtest_precipitation

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.station_names = {RIGA_STATION_ID: "Rīga LU"}
        if not cache_path(RIGA_STATION_ID).is_file():
            raise FileNotFoundError("Rīga LU HTDRY cache missing; run python sync_clidata.py --station RIGASLU")
        self.riga, _ = read_cache(RIGA_STATION_ID)
        self.days, self.pairs = build_day_index({RIGA_STATION_ID: self.riga})
        self.loaded_stations = 1
        self.last_attempt = 0.0
        self.live_error = None
        self.month_cache = {}
        self.october_cache = {}
        self.precip, self.precip_meta = read_precip_cache() if PRECIP_CACHE.is_file() else ({}, {})
        self.precip_days, self.precip_pairs = build_day_index({RIGA_STATION_ID: self.precip})
        self.precip_october_cache = {}
        self.precip_backtest_cache = None
        self.precip_error = None if self.precip else "HPRAB kešs nav pieejams; palaid python sync_precipitation.py"

    def refresh_riga(self):
        with self.lock:
            if time.time() - self.last_attempt < 600:
                return
            self.last_attempt = time.time()
            try:
                sync_station(RIGA_STATION_ID, datetime.now(RIGA).year - 1)
                self.riga, _ = read_cache(RIGA_STATION_ID)
                self.days, self.pairs = build_day_index({RIGA_STATION_ID: self.riga})
                self.month_cache.clear()
                self.october_cache.clear()
                self.live_error = None
            except Exception as error:
                self.live_error = f"CLIDATA atjaunināšana neizdevās: {type(error).__name__}"
            try:
                sync_precipitation(datetime.now(RIGA).year - 1)
                self.precip, self.precip_meta = read_precip_cache()
                self.precip_days, self.precip_pairs = build_day_index({RIGA_STATION_ID: self.precip})
                self.precip_october_cache.clear()
                self.precip_backtest_cache = None
                self.precip_error = None
            except Exception as error:
                self.precip_error = f"HPRAB atjaunināšana neizdevās: {type(error).__name__}"

    def forecast(self, forecast_day=None):
        self.refresh_riga()
        with self.lock:
            today = datetime.now(RIGA).date()
            forecast_day = forecast_day or today
            if forecast_day > today:
                raise ValueError("Nākotnes diena vēl nav pieejama.")
            input_day = forecast_day - timedelta(days=1)
            result = make_forecast(self.riga, input_day, self.days, self.pairs, self.station_names)
            result["loadedStations"] = self.loaded_stations
            result["completeDays"] = len(self.days)
            result["completePairs"] = len(self.pairs)
            result["liveError"] = self.live_error
            result["lastObservation"] = datetime.fromtimestamp(max(self.riga) * 3600, timezone.utc).isoformat()
            return result

    def month(self, year, month):
        self.refresh_riga()
        with self.lock:
            today = datetime.now(RIGA).date()
            key = (year, month, today)
            if key not in self.month_cache:
                self.month_cache[key] = make_month_overview(
                    self.riga, year, month, today, self.days, self.pairs, self.station_names)
            return self.month_cache[key]

    def october_analogues(self, period, method="temperature"):
        self.refresh_riga()
        with self.lock:
            today = datetime.now(RIGA).date()
            key = (2026, period, method, today)
            if key not in self.october_cache:
                self.october_cache[key] = make_october_analogues(
                    self.days, 2026, today, period, method)
            return self.october_cache[key]

    def precipitation_forecast(self, forecast_day=None):
        self.refresh_riga()
        with self.lock:
            if not self.precip:
                raise ValueError(self.precip_error or "HPRAB kešs nav pieejams.")
            today = datetime.now(RIGA).date()
            return make_precip_forecast(self.precip, self.precip_days, self.precip_pairs,
                                        forecast_day or today, today)

    def precipitation_october(self, period, method="amount"):
        self.refresh_riga()
        with self.lock:
            if not self.precip:
                raise ValueError(self.precip_error or "HPRAB kešs nav pieejams.")
            today = datetime.now(RIGA).date()
            key = (2026, period, method, today)
            if key not in self.precip_october_cache:
                self.precip_october_cache[key] = make_precip_october(
                    self.precip_days, 2026, today, period, method)
            return self.precip_october_cache[key]

    def precipitation_backtest(self):
        self.refresh_riga()
        with self.lock:
            if self.precip_backtest_cache is None:
                self.precip_backtest_cache = {"years": [backtest_precipitation(
                    self.precip, self.precip_days, self.precip_pairs, year, 10)
                    for year in range(2020, 2026)]}
            return self.precip_backtest_cache

    def status(self):
        with self.lock:
            today = datetime.now(RIGA).date()
            review_year = today.year if today.month >= 10 else today.year - 1
            return {"station": "Rīga LU", "stationId": "RIGASLU", "element": "HTDRY",
                    "parameter": "Stundas vidējā gaisa temperatūra",
                    "catalogStations": len(self.station_names), "loadedStations": self.loaded_stations,
                    "completeDays": len(self.days), "completePairs": len(self.pairs),
                    "today": today.isoformat(), "reviewMonth": f"{review_year}-10",
                    "liveError": self.live_error,
                    "precipitation": {"element": "HPRAB", "unit": "mm", "hours": len(self.precip),
                                      "completeDays": len(self.precip_days),
                                      "completePairs": len(self.precip_pairs), "error": self.precip_error}}

STORE = Store()


class Handler(BaseHTTPRequestHandler):
    def respond_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlsplit(self.path)
        try:
            if request.path == "/api/status":
                self.respond_json(STORE.status())
            elif request.path == "/api/forecast":
                params = parse_qs(request.query, keep_blank_values=True)
                if not params:
                    self.respond_json(STORE.forecast())
                elif set(params) == {"date"} and len(params["date"]) == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", params["date"][0]):
                    self.respond_json(STORE.forecast(date.fromisoformat(params["date"][0])))
                else:
                    raise ValueError("Norādi tikai date=YYYY-MM-DD.")
            elif request.path == "/api/month":
                params = parse_qs(request.query, keep_blank_values=True)
                if set(params) != {"month"} or len(params["month"]) != 1 or not re.fullmatch(r"\d{4}-\d{2}", params["month"][0]):
                    raise ValueError("Norādi month=YYYY-MM.")
                year, month = map(int, params["month"][0].split("-"))
                if not 1 <= month <= 12:
                    raise ValueError("Nederīgs mēnesis.")
                self.respond_json(STORE.month(year, month))
            elif request.path == "/api/october-analogues":
                params = parse_qs(request.query, keep_blank_values=True)
                if (not set(params) <= {"period", "method"} or "period" not in params
                        or any(len(values) != 1 for values in params.values())):
                    raise ValueError("Norādi period=all, 10 vai 7 un method=temperature, profile vai regime.")
                self.respond_json(STORE.october_analogues(
                    params["period"][0], params.get("method", ["temperature"])[0]))
            elif request.path == "/api/precipitation/forecast":
                params = parse_qs(request.query, keep_blank_values=True)
                if not params:
                    self.respond_json(STORE.precipitation_forecast())
                elif set(params) == {"date"} and len(params["date"]) == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", params["date"][0]):
                    self.respond_json(STORE.precipitation_forecast(date.fromisoformat(params["date"][0])))
                else:
                    raise ValueError("Norādi tikai date=YYYY-MM-DD.")
            elif request.path == "/api/precipitation/october":
                params = parse_qs(request.query, keep_blank_values=True)
                if (not set(params) <= {"period", "method"} or "period" not in params
                        or any(len(values) != 1 for values in params.values())):
                    raise ValueError("Norādi period=all, 10 vai 7 un method=amount, episodes vai rhythm.")
                self.respond_json(STORE.precipitation_october(
                    params["period"][0], params.get("method", ["amount"])[0]))
            elif request.path == "/api/precipitation/backtest":
                if request.query:
                    raise ValueError("Šis gala punkts nepieņem parametrus.")
                self.respond_json(STORE.precipitation_backtest())
            else:
                name = request.path.lstrip("/") or "index.html"
                path = (PUBLIC / name).resolve()
                if not path.is_relative_to(PUBLIC.resolve()) or not path.is_file():
                    self.send_error(404)
                    return
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except (ValueError, KeyError) as error:
            self.respond_json({"error": str(error)}, 400)
        except Exception as error:
            self.respond_json({"error": f"Server error: {type(error).__name__}: {error}"}, 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8777"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Rīgas LU temperatūras pilots: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
