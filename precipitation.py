"""Experimental RIGASLU HPRAB analogues. All inputs are QC-accepted hourly sums."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from model import RIGA, RIGA_STATION_ID, build_day_index, full_local_day, local_day_bounds, season_distance

WET_HOUR_MM = 0.1
WET_DAY_MM = 1.0
METHODS = {"amount", "episodes", "rhythm"}


def _rmse(left, right):
    return math.sqrt(mean((a - b) ** 2 for a, b in zip(left, right)))


def _wet_runs(values, breaks=()):
    lengths, run = [], 0
    for index, value in enumerate(values):
        if index in breaks and run:
            lengths.append(run)
            run = 0
        if value >= WET_HOUR_MM:
            run += 1
        elif run:
            lengths.append(run)
            run = 0
    if run:
        lengths.append(run)
    return lengths


def _longest_dry(values, calendar_days):
    longest = run = 0
    previous_day = None
    for value, day in zip(values, calendar_days):
        if previous_day is not None and day != previous_day + 1:
            run = 0
        run = 0 if value >= WET_DAY_MM else run + 1
        longest = max(longest, run)
        previous_day = day
    return longest


def monthly_scores(target_days, candidate_days, comparison_days):
    """Three independent scores, none of which reads after the comparison cutoff."""
    target_totals = [sum(target_days[day]) for day in comparison_days]
    candidate_totals = [sum(candidate_days[day]) for day in comparison_days]
    n = len(comparison_days)
    daily_mae = mean(abs(a - b) for a, b in zip(target_totals, candidate_totals))
    daily_rmse = _rmse(target_totals, candidate_totals)
    total_delta = abs(sum(target_totals) - sum(candidate_totals)) / n
    amount = .4 * daily_mae + .4 * daily_rmse + .2 * total_delta

    target_hours = [value for day in comparison_days for value in target_days[day]]
    candidate_hours = [value for day in comparison_days for value in candidate_days[day]]
    breaks = {index * 24 for index in range(1, n)
              if comparison_days[index] != comparison_days[index - 1] + 1}
    wet_mismatch = mean((a >= WET_HOUR_MM) != (b >= WET_HOUR_MM)
                        for a, b in zip(target_hours, candidate_hours))
    target_runs, candidate_runs = _wet_runs(target_hours, breaks), _wet_runs(candidate_hours, breaks)
    episode_count_delta = abs(len(target_runs) - len(candidate_runs)) / n
    mean_run_delta = abs((mean(target_runs) if target_runs else 0) -
                         (mean(candidate_runs) if candidate_runs else 0)) / 24
    episodes = .7 * wet_mismatch + .2 * episode_count_delta + .1 * mean_run_delta

    target_wet = [value >= WET_DAY_MM for value in target_totals]
    candidate_wet = [value >= WET_DAY_MM for value in candidate_totals]
    day_mismatch = mean(a != b for a, b in zip(target_wet, candidate_wet))
    transitions = [(a, b) for a, b in zip(comparison_days, comparison_days[1:]) if b == a + 1]
    transition_mismatch = (mean((target_wet[comparison_days.index(a)] != target_wet[comparison_days.index(b)]) !=
                                (candidate_wet[comparison_days.index(a)] != candidate_wet[comparison_days.index(b)])
                                for a, b in transitions) if transitions else None)
    dry_run_delta = abs(_longest_dry(target_totals, comparison_days) -
                        _longest_dry(candidate_totals, comparison_days)) / n
    rhythm_terms = [(.55, day_mismatch), (.20, dry_run_delta)]
    if transition_mismatch is not None:
        rhythm_terms.append((.25, transition_mismatch))
    rhythm = sum(weight * value for weight, value in rhythm_terms) / sum(weight for weight, _ in rhythm_terms)
    return {"amount": amount, "episodes": episodes, "rhythm": rhythm}, {
        "dailyMaeMm": daily_mae, "dailyRmseMm": daily_rmse,
        "monthlyDifferencePerDayMm": total_delta, "wetHourMismatch": wet_mismatch,
        "episodeCountDifferencePerDay": episode_count_delta, "meanEpisodeLengthDifferenceHours": mean_run_delta * 24,
        "wetDayMismatch": day_mismatch, "transitionMismatch": transition_mismatch,
        "transitionPairs": len(transitions),
        "longestDryRunDifferenceDays": dry_run_delta * n}


def make_precip_october(days, target_year, today, period="all", method="amount"):
    if period not in {"all", "10", "7"} or method not in METHODS:
        raise ValueError("Periods ir all, 10 vai 7; metode ir amount, episodes vai rhythm.")
    cutoff = min(today - timedelta(days=1), date(target_year, 10, 31))
    target_days = {record.day.day: record.values for record in days
                   if record.station == RIGA_STATION_ID and record.day.year == target_year
                   and record.day.month == 10 and record.day <= cutoff and len(record.values) == 24}
    if not target_days:
        raise ValueError("Mērķa oktobrī vēl nav pilnu Rīgas LU HPRAB dienu.")
    end_day = max(target_days)
    start_day = 1 if period == "all" else max(1, end_day - int(period) + 1)
    comparison_days = [day for day in range(start_day, end_day + 1) if day in target_days]
    historic = {}
    for record in days:
        if (record.station == RIGA_STATION_ID and record.day.month == 10
                and record.day.year < target_year and len(record.values) == 24):
            historic.setdefault(record.day.year, {})[record.day.day] = record.values
    candidates = []
    for year, year_days in historic.items():
        if any(day not in year_days for day in comparison_days):
            continue
        scores, parts = monthly_scores(target_days, year_days, comparison_days)
        candidates.append((scores[method], year, year_days, scores, parts))
    candidates.sort(key=lambda row: (row[0], row[1]))
    matches = []
    for score, year, year_days, scores, parts in candidates[:5]:
        continuation = [list(year_days[day]) if day in year_days else None
                        for day in range(end_day + 1, 32)]
        matches.append({"year": year, "stationId": RIGA_STATION_ID, "element": "HPRAB",
                        "score": round(score, 3),
                        "methodScores": {key: round(value, 3) for key, value in scores.items()},
                        "components": {key: round(value, 3) if value is not None else None
                                       for key, value in parts.items()},
                        "comparisonDays": [list(year_days[day]) for day in comparison_days],
                        "continuationDays": continuation,
                        "completeContinuationDays": sum(day is not None for day in continuation)})
    return {"targetYear": target_year, "stationId": RIGA_STATION_ID,
            "element": "HPRAB", "unit": "mm", "period": period, "method": method,
            "startDay": start_day, "endDay": end_day, "comparisonDays": comparison_days,
            "candidateYears": len(candidates),
            "targetDays": [list(target_days[day]) if day in target_days else None
                           for day in range(1, end_day + 1)], "matches": matches}


def _forecast_score(target, candidate, target_day, candidate_day):
    shape = _rmse([math.log1p(value) for value in target],
                  [math.log1p(value) for value in candidate])
    wet_mismatch = mean((a >= WET_HOUR_MM) != (b >= WET_HOUR_MM)
                        for a, b in zip(target, candidate))
    total_delta = abs(sum(target) - sum(candidate)) / 24
    return .5 * shape + .3 * wet_mismatch + .2 * total_delta + .08 * season_distance(target_day, candidate_day) / 60


def _quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def make_precip_forecast(observations, days, pairs, forecast_day, today, *, limit=8):
    if forecast_day > today:
        raise ValueError("Nākotnes diena vēl nav pieejama.")
    input_day = forecast_day - timedelta(days=1)
    target = full_local_day(observations, input_day)
    if target is None:
        raise ValueError("Iepriekšējās Rīgas LU dienas 24 HPRAB stundas nav pilnas.")
    eligible = []
    for pair in pairs:
        if (pair.station == RIGA_STATION_ID and pair.day <= input_day - timedelta(days=8)
                and season_distance(input_day, pair.day) <= 60):
            eligible.append((_forecast_score(target, pair.values, input_day, pair.day), pair))
    eligible.sort(key=lambda item: (item[0], item[1].day))
    selected = []
    for score, pair in eligible:
        if all(abs((pair.day - previous.day).days) >= 5 for _, previous in selected):
            selected.append((score, pair))
        if len(selected) == limit:
            break
    if len(selected) < 3:
        raise ValueError("Nav pietiekami daudz pilnu HPRAB 24+24h pāru.")
    weights = [1 / (score + .3) ** 2 for score, _ in selected]
    weight_sum = sum(weights)
    hourly_amount = [sum(weight * pair.next_values[hour] for weight, (_, pair) in zip(weights, selected)) / weight_sum
                     for hour in range(24)]
    hourly_probability = [sum(weight for weight, (_, pair) in zip(weights, selected)
                              if pair.next_values[hour] >= WET_HOUR_MM) / weight_sum for hour in range(24)]
    totals = [sum(pair.next_values) for _, pair in selected]
    daily_probability = sum(weight for weight, total in zip(weights, totals) if total >= WET_DAY_MM) / weight_sum
    future_start, future_end = local_day_bounds(forecast_day)
    if future_end - future_start != 24:
        raise ValueError("Vasaras laika pārejas dienai 24h nokrišņu prognoze nav pieejama.")
    input_start, _ = local_day_bounds(input_day)
    actual = [observations.get(future_start + hour) if forecast_day <= today else None for hour in range(24)]
    return {"inputDate": input_day.isoformat(), "forecastDate": forecast_day.isoformat(),
            "stationId": RIGA_STATION_ID, "element": "HPRAB", "unit": "mm",
            "input": [[(input_start + hour) * 3600000, value] for hour, value in enumerate(target)],
            "hourlyAmount": [[(future_start + hour) * 3600000, round(value, 3)]
                             for hour, value in enumerate(hourly_amount)],
            "hourlyProbability": [[(future_start + hour) * 3600000, round(value, 3)]
                                  for hour, value in enumerate(hourly_probability)],
            "actual": [[(future_start + hour) * 3600000, value] for hour, value in enumerate(actual)],
            "dailyRainProbability": round(daily_probability, 3),
            "expectedTotalMm": round(sum(hourly_amount), 2),
            "totalScenariosMm": {"p10": round(_quantile(totals, .1), 2),
                                 "p50": round(_quantile(totals, .5), 2),
                                 "p90": round(_quantile(totals, .9), 2)},
            "observedHours": sum(value is not None for value in actual),
            "observedTotalMm": round(sum(value for value in actual if value is not None), 2),
            "candidatePairs": len(eligible),
            "matches": [{"date": pair.day.isoformat(), "score": round(score, 3),
                         "inputTotalMm": round(sum(pair.values), 2),
                         "continuationTotalMm": round(sum(pair.next_values), 2),
                         "continuation": list(pair.next_values)} for score, pair in selected]}


def backtest_precipitation(observations, days, pairs, year=2025, month=10):
    """Replay prior dates; today's actual is used only to score the saved output."""
    errors, rain_brier, zero_errors, seasonal_brier = [], [], [], []
    for record in days:
        day = record.day
        if day.year != year or day.month != month:
            continue
        try:
            result = make_precip_forecast(observations, days, pairs, day, day)
        except ValueError:
            continue
        actual = sum(record.values)
        errors.append(abs(result["expectedTotalMm"] - actual))
        rain_brier.append((result["dailyRainProbability"] - (actual >= WET_DAY_MM)) ** 2)
        zero_errors.append(actual)
        input_day = day - timedelta(days=1)
        eligible = [pair for pair in pairs if pair.station == RIGA_STATION_ID
                    and pair.day <= input_day - timedelta(days=8)
                    and season_distance(input_day, pair.day) <= 60]
        baseline_probability = mean(sum(pair.next_values) >= WET_DAY_MM for pair in eligible)
        seasonal_brier.append((baseline_probability - (actual >= WET_DAY_MM)) ** 2)
    return {"year": year, "month": month, "days": len(errors),
            "dailyTotalMaeMm": round(mean(errors), 2) if errors else None,
            "dailyRainBrier": round(mean(rain_brier), 3) if rain_brier else None,
            "zeroAmountBaselineMaeMm": round(mean(zero_errors), 2) if zero_errors else None,
            "seasonalFrequencyBaselineBrier": round(mean(seasonal_brier), 3) if seasonal_brier else None}
