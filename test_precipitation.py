import json
import unittest
from datetime import date, timedelta

from model import build_day_index, local_day_bounds
from precipitation import (WET_DAY_MM, backtest_precipitation, make_precip_forecast,
                           make_precip_october, monthly_scores)
from sync_precipitation import parse_hour, validate_metadata


class MetadataConnection:
    def __init__(self, unit="mm", interval="01:00"):
        self.unit, self.interval = unit, interval

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query):
        if "FROM CLIDATA.ELEMENTS WHERE" in query:
            self.rows = [("Precipitation amount, hourly sum", "Hourly precipitation", self.unit, 0, 250)]
        elif "FROM CLIDATA.ST_ELEMENTS" in query:
            self.rows = [(self.interval,)]
        else:
            self.rows = [("T", "Trace precipitation")]

    def fetchone(self):
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


def add_day(observations, day, values):
    start, end = local_day_bounds(day)
    if end - start != 24:
        raise ValueError("Test day must have 24 hours")
    observations.update({start + hour: value for hour, value in enumerate(values)})


class PrecipitationQCTest(unittest.TestCase):
    def test_metadata_requires_verified_hourly_sum_unit_and_interval(self):
        self.assertEqual(validate_metadata(MetadataConnection())["unit"], "mm")
        for unit, interval in (("cm", "01:00"), ("mm", "24:00")):
            with self.subTest(unit=unit, interval=interval), self.assertRaises(ValueError):
                validate_metadata(MetadataConnection(unit, interval))

    def test_explicit_zero_differs_from_missing_and_flags_are_excluded(self):
        self.assertEqual(parse_hour(None, None, None), (None, "missing"))
        self.assertEqual(parse_hour(0, None, None), (0, None))
        self.assertEqual(parse_hour(.2, "T", None), (None, "valueFlag"))
        self.assertEqual(parse_hour(.2, None, "E  P"), (None, "qualityFlag"))
        self.assertEqual(parse_hour(.2, None, " R"), (None, "qualityFlag"))
        self.assertEqual(parse_hour(-9999, None, None), (None, "range"))
        self.assertEqual(parse_hour(251, None, None), (None, "range"))
        self.assertEqual(parse_hour(.2, None, "   P  CP"), (.2, None))

    def test_incomplete_day_is_never_zero_filled(self):
        observations = {}
        add_day(observations, date(2026, 10, 1), [0] * 24)
        add_day(observations, date(2026, 10, 2), [0] * 24)
        del observations[local_day_bounds(date(2026, 10, 2))[0] + 9]
        days, pairs = build_day_index({"RIGASLU": observations})
        self.assertEqual([record.day for record in days], [date(2026, 10, 1)])
        self.assertEqual(pairs, [])


class PrecipitationOctoberTest(unittest.TestCase):
    def setUp(self):
        self.observations = {}
        self.other = {}
        for day in range(1, 8):
            target = [0.0] * 24
            if day % 2:
                target[6:9] = [.5, 1.0, .5]
            add_day(self.observations, date(2026, 10, day), target)
            add_day(self.observations, date(2020, 10, day), target)
            add_day(self.observations, date(2021, 10, day), [0.0] * 24)
            add_day(self.other, date(2019, 10, day), target)
        add_day(self.observations, date(2020, 10, 8), [2] * 24)

    def result(self, method="amount"):
        days, _ = build_day_index({"RIGASLU": self.observations, "RIBA99PA": self.other})
        return make_precip_october(days, 2026, date(2026, 10, 8), "all", method)

    def test_three_methods_api_and_continuation_is_display_only(self):
        for index, method in enumerate(("amount", "episodes", "rhythm"), 1):
            before = self.result(method)
            json.dumps(before)
            self.assertEqual(before["candidateYears"], 2)
            self.assertEqual(before["matches"][0]["year"], 2020)
            self.assertEqual(before["matches"][0]["score"], 0)
            self.assertEqual(before["matches"][0]["stationId"], "RIGASLU")
            self.assertEqual(len(before["targetDays"]), 7)
            self.assertEqual(len(before["matches"][0]["comparisonDays"]), 7)
            self.assertEqual(len(before["matches"][0]["continuationDays"]), 24)
            add_day(self.observations, date(2020, 10, 8), [2 + index] * 24)
            add_day(self.observations, date(2026, 10, 8), [9] * 24)
            after = self.result(method)
            self.assertEqual(after["endDay"], 7)
            self.assertEqual([(match["year"], match["score"]) for match in before["matches"]],
                             [(match["year"], match["score"]) for match in after["matches"]])
            self.assertNotEqual(before["matches"][0]["continuationDays"][0],
                                after["matches"][0]["continuationDays"][0])

    def test_missing_target_day_excludes_it_without_cross_gap_transition(self):
        del self.observations[local_day_bounds(date(2026, 10, 4))[0] + 3]
        result = self.result("rhythm")
        self.assertNotIn(4, result["comparisonDays"])
        self.assertIsNone(result["targetDays"][3])
        self.assertEqual(result["candidateYears"], 2)
        self.assertEqual(result["matches"][0]["components"]["transitionPairs"], 4)
        with self.assertRaises(ValueError):
            self.result("invalid")

    def test_pattern_scores_distinguish_hourly_episodes_from_total(self):
        target = {1: [0] * 8 + [1] * 2 + [0] * 14}
        shifted = {1: [0] * 12 + [1] * 2 + [0] * 10}
        scores, parts = monthly_scores(target, shifted, [1])
        self.assertEqual(scores["amount"], 0)
        self.assertGreater(scores["episodes"], 0)
        self.assertEqual(scores["rhythm"], 0)
        self.assertEqual(parts["dailyMaeMm"], 0)


class PrecipitationForecastTest(unittest.TestCase):
    def setUp(self):
        self.observations = {}
        self.other = {}
        for day in (1, 6, 11):
            add_day(self.observations, date(2026, 10, day), [0] * 24)
            add_day(self.observations, date(2026, 10, day + 1), [day / 10] * 24)
            add_day(self.other, date(2026, 10, day), [0] * 24)
            add_day(self.other, date(2026, 10, day + 1), [100] * 24)
        add_day(self.observations, date(2026, 10, 20), [0] * 24)

    def result(self):
        days, pairs = build_day_index({"RIGASLU": self.observations, "RIBA99PA": self.other})
        return make_precip_forecast(self.observations, days, pairs,
                                    date(2026, 10, 21), date(2026, 10, 21))

    def test_future_actual_and_other_station_never_select_analogues(self):
        before = self.result()
        self.assertEqual(len(before["matches"]), 3)
        self.assertEqual(before["observedHours"], 0)
        self.assertTrue(all(match["continuationTotalMm"] < 30 for match in before["matches"]))
        add_day(self.observations, date(2026, 10, 21), [50] * 24)
        after = self.result()
        self.assertEqual(after["observedHours"], 24)
        self.assertEqual(before["matches"], after["matches"])
        self.assertEqual(before["hourlyAmount"], after["hourlyAmount"])
        self.assertEqual(before["dailyRainProbability"], after["dailyRainProbability"])
        self.assertEqual(before["totalScenariosMm"], after["totalScenariosMm"])
        self.assertEqual(before["actual"][0][1], None)
        self.assertEqual(after["actual"][0][1], 50)

    def test_backtest_uses_historical_day_only_for_scoring(self):
        add_day(self.observations, date(2026, 10, 21), [0] * 24)
        days, pairs = build_day_index({"RIGASLU": self.observations})
        result = backtest_precipitation(self.observations, days, pairs, 2026, 10)
        self.assertGreaterEqual(result["days"], 1)
        self.assertIsNotNone(result["dailyTotalMaeMm"])
        self.assertIsNotNone(result["dailyRainBrier"])
        self.assertIsNotNone(result["seasonalFrequencyBaselineBrier"])


if __name__ == "__main__":
    unittest.main()
