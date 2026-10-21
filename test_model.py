import json
import unittest
from datetime import date, timedelta

from model import (analogue_score, build_day_index, find_analogues, full_local_day,
                   hourly_day_normal,
                   local_day_bounds, make_forecast, make_month_overview,
                   make_october_analogues,
                   score_components, season_distance)
from sync_clidata import fetch_observations


def add_day(data, day, values):
    start, end = local_day_bounds(day)
    if end - start != 24:
        raise ValueError("test date crosses DST")
    data.update({start + hour: values[hour] for hour in range(24)})


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, *_): pass
    def __iter__(self): return iter(self.rows)


class Connection:
    def __init__(self, rows): self.rows = rows
    def cursor(self): return Cursor(self.rows)


def oracle_row(day, value, flag=None):
    vals = [None] * 31
    flags = [None] * 31
    vals[day - 1] = value
    flags[day - 1] = flag
    return ["2020", "10", "12:00"] + vals + flags


class QualityControlTest(unittest.TestCase):
    def test_rejects_flags_bad_values_and_conflicting_hours(self):
        rows = [oracle_row(1, 9.1), oracle_row(2, 9.2, "X"),
                oracle_row(3, 90), oracle_row(4, 8), oracle_row(4, 7)]
        data, qc = fetch_observations("RIGASLU", connection=Connection(rows))
        self.assertEqual(len(data), 1)
        self.assertEqual(qc["flaggedCells"], 1)
        self.assertEqual(qc["outOfRangeCells"], 1)
        self.assertEqual(qc["conflictingHours"], 1)

    def test_day_requires_all_24_accepted_hours(self):
        day = date(2020, 10, 12)
        values = {}
        add_day(values, day, [5.0] * 24)
        self.assertEqual(len(full_local_day(values, day)), 24)
        del values[local_day_bounds(day)[0] + 8]
        self.assertIsNone(full_local_day(values, day))
        self.assertIsNone(full_local_day(values, date(2026, 3, 29)))


class AnalogueTest(unittest.TestCase):
    def setUp(self):
        self.target = date(2026, 10, 19)
        self.riga = {}
        self.station_data = {"RIGASLU": self.riga, "RIAL99MS": {}, "RIBA99PA": {}}
        add_day(self.riga, self.target, [5 + hour * .1 for hour in range(24)])
        for day in [date(2019, 10, 10), date(2020, 10, 12),
                    date(2021, 10, 14), date(2022, 10, 16)]:
            add_day(self.riga, day, [5 + hour * .1 for hour in range(24)])
            add_day(self.riga, day + timedelta(days=1), [7 + hour * .08 for hour in range(24)])
        for station in ("RIAL99MS", "RIBA99PA"):
            day = date(2018, 10, 10)
            values = ([9.0] * 24 if station == "RIBA99PA" else
                      [5 + hour * .1 for hour in range(24)])
            add_day(self.station_data[station], day, values)
            add_day(self.station_data[station], day + timedelta(days=1), [7 + hour * .08 for hour in range(24)])
        self.days, self.pairs = build_day_index(self.station_data)
        self.names = {"RIGASLU": "Rīga LU", "RIAL99MS": "Alūksne", "RIBA99PA": "Bauska"}

    def test_only_riga_pairs_are_selected_even_with_other_stations_present(self):
        _, matches, count, stations = find_analogues(self.riga, self.target, self.pairs)
        self.assertEqual(len(matches), 4)
        self.assertEqual(count, 4)
        self.assertEqual(stations, 1)
        for _, pair in matches:
            self.assertEqual(pair.station, "RIGASLU")
            self.assertEqual(pair.values, full_local_day(self.station_data[pair.station], pair.day))
            self.assertEqual(pair.next_values, full_local_day(self.station_data[pair.station], pair.day + timedelta(days=1)))
        with self.assertRaises(ValueError):
            find_analogues(self.riga, self.target,
                           [pair for pair in self.pairs if pair.station != "RIGASLU"])

    def test_forecast_does_not_use_validation_day(self):
        forecast_day = self.target + timedelta(days=1)
        add_day(self.riga, forecast_day, [9.0] * 24)
        all_days, all_pairs = build_day_index(self.station_data)
        complete = make_forecast(self.riga, self.target, all_days, all_pairs, self.names)
        cutoff, _ = local_day_bounds(forecast_day)
        past = {hour: value for hour, value in self.riga.items() if hour < cutoff}
        days, pairs = build_day_index({**self.station_data, "RIGASLU": past})
        replay = make_forecast(past, self.target, days, pairs, self.names)
        self.assertEqual(complete["forecast"], replay["forecast"])
        self.assertEqual(complete["matches"], replay["matches"])
        self.assertEqual(replay["actualCount"], 0)
        self.assertIsNotNone(complete["observedDayMatch"])
        self.assertEqual(complete["observedDayMatch"]["stationId"], "RIGASLU")

    def test_gap_excludes_incomplete_24_plus_24_pair(self):
        station = self.riga
        day = date(2022, 10, 16)
        del station[local_day_bounds(day + timedelta(days=1))[0] + 7]
        _, pairs = build_day_index(self.station_data)
        self.assertFalse(any(pair.station == "RIGASLU" and pair.day == day for pair in pairs))

    def test_every_analogue_exposes_its_anchored_continuation(self):
        result = make_forecast(self.riga, self.target, self.days, self.pairs, self.names)
        json.dumps(result)  # The browser consumes this payload directly.
        self.assertEqual(result["bestAnalogue"], result["matches"][0]["continuation"])
        self.assertEqual(result["candidateStations"], 1)
        self.assertEqual(result["stationCount"], 1)
        for match in result["matches"]:
            self.assertEqual(match["stationId"], "RIGASLU")
            self.assertEqual(match["source"], "HTDRY")
            pair = next(pair for pair in self.pairs
                        if pair.station == match["stationId"] and pair.day.isoformat() == match["date"])
            shift = round(result["input"][-1][1] - pair.values[-1], 2)
            self.assertEqual(match["anchorShift"], shift)
            self.assertEqual(match["continuation"],
                             [round(value + shift, 2) for value in pair.next_values])
            self.assertEqual(len(match["continuation"]), 24)
            self.assertGreaterEqual(match["score"], 0)
            self.assertAlmostEqual(match["score"], analogue_score(full_local_day(self.riga, self.target), pair.values,
                                                                    season_distance(pair.day, self.target)), delta=.006)

    def test_score_components_have_interpretable_units(self):
        target = [hour * .5 for hour in range(24)]
        offset = [value + 2 for value in target]
        parts = score_components(target, offset, 30)
        self.assertAlmostEqual(parts["absoluteRmse"], 2)
        self.assertAlmostEqual(parts["shapeRmse"], 0)
        self.assertAlmostEqual(parts["hourlyChangeRmse"], 0)
        self.assertAlmostEqual(parts["seasonalPenalty"], .175)
        self.assertAlmostEqual(parts["combinedScore"], .48 * 2 + .175)
        self.assertAlmostEqual(analogue_score(target, offset, 30), parts["combinedScore"])

    def test_october_replay_uses_september_30_and_marks_future_days(self):
        input_day = date(2026, 9, 30)
        forecast_day = date(2026, 10, 1)
        add_day(self.riga, input_day, [6 + hour * .1 for hour in range(24)])
        add_day(self.riga, forecast_day, [8 + hour * .08 for hour in range(24)])
        days, pairs = build_day_index(self.station_data)
        result = make_month_overview(self.riga, 2026, 10, date(2026, 10, 2),
                                     days, pairs, self.names)
        first, second, third = result["days"][:3]
        self.assertEqual(len(result["days"]), 31)
        self.assertEqual((first["date"], first["inputDate"]), ("2026-10-01", "2026-09-30"))
        self.assertEqual((first["status"], first["actualCount"]), ("complete", 24))
        self.assertEqual(second["status"], "unobserved")
        self.assertEqual(third["status"], "future")
        self.assertEqual(result["completeDays"], 1)
        replay = make_forecast(self.riga, input_day, days, pairs, self.names)
        self.assertEqual(first["mae"], replay["mae"])

    def test_hourly_normal_uses_only_prior_full_riga_days_on_same_date(self):
        forecast_day = date(2026, 10, 20)
        add_day(self.riga, date(2020, 10, 20), [10 + hour * .1 for hour in range(24)])
        add_day(self.riga, date(2021, 10, 20), [14 + hour * .1 for hour in range(24)])
        add_day(self.riga, date(2022, 10, 20), [40] * 24)
        del self.riga[local_day_bounds(date(2022, 10, 20))[0] + 5]
        add_day(self.riga, date(2027, 10, 20), [30] * 24)
        add_day(self.station_data["RIBA99PA"], date(2017, 10, 20), [35] * 24)
        days, pairs = build_day_index(self.station_data)
        normal, years = hourly_day_normal(days, forecast_day)
        self.assertEqual(years, [2020, 2021])
        self.assertEqual(normal, [round(12 + hour * .1, 2) for hour in range(24)])
        result = make_forecast(self.riga, self.target, days, pairs, self.names)
        self.assertEqual(result["normalSampleDays"], 2)
        self.assertEqual(result["normalYears"], [2020, 2021])
        self.assertEqual(result["normal"], [[point[0], normal[hour]]
                                            for hour, point in enumerate(result["forecast"])])


class OctoberAnalogueTest(unittest.TestCase):
    def setUp(self):
        self.riga = {}
        self.other = {}
        for day in range(1, 21):
            values = [day * .5 + hour * .1 for hour in range(24)]
            add_day(self.riga, date(2026, 10, day), values)
            add_day(self.riga, date(2020, 10, day), values)
            add_day(self.riga, date(2021, 10, day), [value + 2 for value in values])
            add_day(self.riga, date(2022, 10, day),
                    [value + (3 if day <= 13 else 0) for value in values])
            if day != 5:
                add_day(self.riga, date(2023, 10, day), values)
            add_day(self.other, date(2019, 10, day), values)
        add_day(self.riga, date(2020, 10, 21), [12] * 24)
        add_day(self.riga, date(2020, 10, 23), [14] * 24)

    def result(self, period="all", method="temperature"):
        days, _ = build_day_index({"RIGASLU": self.riga, "RIBA99PA": self.other})
        return make_october_analogues(days, 2026, date(2026, 10, 21), period, method)

    def test_same_calendar_hours_riga_only_and_separate_continuation(self):
        result = self.result()
        json.dumps(result)
        self.assertEqual((result["startDay"], result["endDay"], result["comparisonHours"]),
                         (1, 20, 480))
        self.assertEqual(result["comparisonDays"], list(range(1, 21)))
        self.assertEqual(result["candidateYears"], 3)
        self.assertEqual([entry["year"] for entry in result["matches"]], [2020, 2021, 2022])
        self.assertTrue(all(entry["stationId"] == "RIGASLU" and entry["element"] == "HTDRY"
                            for entry in result["matches"]))
        best = result["matches"][0]
        self.assertEqual((best["mae"], best["rmse"], best["shapeRmse"], best["score"]),
                         (0, 0, 0, 0))
        self.assertEqual(len(best["comparisonValues"]), 480)
        self.assertEqual(len(best["continuationDays"]), 11)
        self.assertEqual(best["continuationDays"][0], [12] * 24)
        self.assertIsNone(best["continuationDays"][1])
        self.assertEqual(best["completeContinuationDays"], 2)
        offset = result["matches"][1]
        self.assertEqual((offset["mae"], offset["rmse"], offset["shapeRmse"], offset["score"]),
                         (2, 2, 0, 1.4))

    def test_period_switch_and_missing_day_are_not_interpolated(self):
        ten = self.result("10")
        seven = self.result("7")
        self.assertEqual((ten["startDay"], ten["endDay"], ten["comparisonHours"]), (11, 20, 240))
        self.assertEqual((seven["startDay"], seven["endDay"], seven["comparisonHours"]), (14, 20, 168))
        self.assertEqual(ten["candidateYears"], 4)
        self.assertEqual(seven["candidateYears"], 4)
        del self.riga[local_day_bounds(date(2026, 10, 5))[0] + 9]
        all_with_gap = self.result("all")
        self.assertEqual(all_with_gap["comparisonHours"], 19 * 24)
        self.assertNotIn(5, all_with_gap["comparisonDays"])
        self.assertIsNone(all_with_gap["targetDays"][4])
        self.assertEqual(all_with_gap["candidateYears"], 4)
        gap_regime = self.result("all", "regime")
        self.assertEqual(gap_regime["matches"][0]["regime"]["consecutiveTransitions"], 17)
        self.assertEqual(gap_regime["matches"][0]["regime"]["threeDayWindows"], 15)
        self.assertEqual(self.result("7")["comparisonHours"], 168)
        with self.assertRaises(ValueError):
            self.result("bad")

    def test_changing_continuation_never_changes_ranking(self):
        before = {method: self.result(method=method)
                  for method in ("temperature", "profile", "regime")}
        add_day(self.riga, date(2020, 10, 21), [40] * 24)
        add_day(self.riga, date(2026, 10, 21), [50] * 24)  # Today's full data must not advance the cutoff.
        for method, original in before.items():
            after = self.result(method=method)
            self.assertEqual(after["endDay"], 20)
            self.assertEqual([(entry["year"], entry["score"], entry["methodScores"])
                              for entry in original["matches"]],
                             [(entry["year"], entry["score"], entry["methodScores"])
                              for entry in after["matches"]])
            self.assertNotEqual(original["matches"][0]["continuationDays"],
                                after["matches"][0]["continuationDays"])

    def test_new_scores_and_visualization_data(self):
        for method in ("temperature", "profile", "regime"):
            result = self.result(method=method)
            self.assertEqual(result["method"], method)
            self.assertEqual(result["matches"][0]["year"], 2020)
            best = result["matches"][0]
            self.assertEqual(best["score"], 0)
            self.assertEqual(best["methodScores"][method], 0)
            self.assertTrue(all(value == 0 for value in best["profile"].values()))
            self.assertEqual(best["regime"]["consecutiveTransitions"], 19)
            self.assertEqual(best["regime"]["threeDayWindows"], 18)
            self.assertEqual(len(best["comparisonValues"]), result["comparisonHours"])
            self.assertEqual(len(best["continuationDays"]), 11)
            self.assertEqual(result["matches"][1]["methodScores"]["profile"], 0)
            self.assertEqual(result["matches"][1]["methodScores"]["regime"], 0)
        with self.assertRaises(ValueError):
            self.result(method="invalid")

    def test_temperature_and_pattern_rankings_can_disagree(self):
        records = {}
        for year in (2020, 2021, 2026):
            records[year] = {}
            for day in range(1, 8):
                target = [day * 2 + hour * .08 for hour in range(24)]
                values = ([sum(target) / 24 + .5] * 24 if year == 2020 else
                          [value + 4 for value in target] if year == 2021 else target)
                add_day(records[year], date(year, 10, day), values)
        days, _ = build_day_index({"RIGASLU": {
            timestamp: value for year in records.values() for timestamp, value in year.items()}})
        rank = lambda method: make_october_analogues(
            days, 2026, date(2026, 10, 8), "all", method)
        self.assertEqual(rank("temperature")["matches"][0]["year"], 2020)
        self.assertEqual(rank("profile")["matches"][0]["year"], 2021)
        self.assertEqual(rank("regime")["matches"][0]["year"], 2021)
        self.assertEqual(rank("profile")["matches"][0]["profile"]["shapeRmse"], 0)
        self.assertEqual(rank("regime")["matches"][0]["regime"]["dailyChangeRmse"], 0)

if __name__ == "__main__":
    unittest.main()
