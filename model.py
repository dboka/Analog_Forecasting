"""24h temperature analogues from Rīga LU HTDRY observations only."""

from __future__ import annotations

import math
import calendar
import numpy as np
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

RIGA = ZoneInfo("Europe/Riga")
RIGA_STATION_ID = "RIGASLU"
HOUR = 3600


@dataclass(frozen=True)
class DayRecord:
    station: str
    day: date
    values: tuple[float, ...]


@dataclass(frozen=True)
class PairRecord:
    station: str
    day: date
    values: tuple[float, ...]
    next_values: tuple[float, ...]


def local_day_bounds(day):
    start = datetime(day.year, day.month, day.day, tzinfo=RIGA)
    end = start + timedelta(days=1)
    return int(start.timestamp() // HOUR), int(end.timestamp() // HOUR)


def full_local_day(data, day):
    start, end = local_day_bounds(day)
    if end - start != 24:  # DST dates cannot fit the 24h trial.
        return None
    points = tuple(data.get(hour) for hour in range(start, end))
    return points if all(value is not None for value in points) else None


def build_day_index(station_data):
    """Keep only complete 24-hour local days; pairs stay within one station."""
    days = []
    pairs = []
    for station, data in station_data.items():
        if not data:
            continue
        first = datetime.fromtimestamp(min(data) * HOUR, timezone.utc).astimezone(RIGA).date()
        last = datetime.fromtimestamp(max(data) * HOUR, timezone.utc).astimezone(RIGA).date()
        complete = {}
        day = first
        while day <= last:
            values = full_local_day(data, day)
            if values is not None:
                complete[day] = values
                days.append(DayRecord(station, day, values))
            day += timedelta(days=1)
        for day, values in complete.items():
            continuation = complete.get(day + timedelta(days=1))
            if continuation is not None:
                pairs.append(PairRecord(station, day, values, continuation))
    return days, pairs


def season_distance(a, b):
    # Fixed leap-year reference avoids asymmetric February/December ranks.
    reference_a = date(2000, a.month, a.day) if a.month != 2 or a.day != 29 else date(2000, 2, 29)
    reference_b = date(2000, b.month, b.day) if b.month != 2 or b.day != 29 else date(2000, 2, 29)
    difference = abs(reference_a.timetuple().tm_yday - reference_b.timetuple().tm_yday)
    return min(difference, 366 - difference)


def rmse(a, b):
    return math.sqrt(mean((x - y) ** 2 for x, y in zip(a, b)))


def analogue_score(target, candidate, season_days):
    return score_components(target, candidate, season_days)["combinedScore"]


def score_components(target, candidate, season_days):
    """Four interpretable terms and the unchanged production matching score."""
    absolute = rmse(target, candidate)
    target_mean, candidate_mean = mean(target), mean(candidate)
    shape = rmse([x - target_mean for x in target], [x - candidate_mean for x in candidate])
    changes = rmse([target[i + 1] - target[i] for i in range(23)],
                   [candidate[i + 1] - candidate[i] for i in range(23)])
    seasonal_penalty = .35 * season_days / 60
    return {"absoluteRmse": absolute, "shapeRmse": shape,
            "hourlyChangeRmse": changes, "seasonalPenalty": seasonal_penalty,
            "combinedScore": .48 * absolute + .37 * shape + .15 * changes + seasonal_penalty}


def _ranked_selection(riga_data, target_day, pairs, n=8):
    target = full_local_day(riga_data, target_day)
    if target is None:
        raise ValueError("Iepriekšējās Rīgas dienas 24 HTDRY mērījumi nav pilni.")
    last_candidate = target_day - timedelta(days=8)
    eligible = []
    seasons = []
    station_ids = set()
    for pair in pairs:
        if pair.station != RIGA_STATION_ID:
            continue
        if pair.day > last_candidate:
            continue
        season = season_distance(pair.day, target_day)
        if season > 60:
            continue
        station_ids.add(pair.station)
        eligible.append(pair)
        seasons.append(season)
    if not eligible:
        raise ValueError("Vēsturē nav pilnu HTDRY 24+24h pāru šajā sezonā.")
    curves = np.asarray([pair.values for pair in eligible], dtype=np.float64)
    target_array = np.asarray(target, dtype=np.float64)
    absolute = np.sqrt(np.mean((curves - target_array) ** 2, axis=1))
    shape = np.sqrt(np.mean(((curves - curves.mean(axis=1, keepdims=True)) -
                             (target_array - target_array.mean())) ** 2, axis=1))
    changes = np.sqrt(np.mean((np.diff(curves, axis=1) - np.diff(target_array)) ** 2, axis=1))
    penalty = .35 * np.asarray(seasons) / 60
    combined = .48 * absolute + .37 * shape + .15 * changes + penalty
    candidates = sorted(range(len(eligible)),
                        key=lambda index: (float(combined[index]), eligible[index].day, eligible[index].station))
    chosen = []
    for index in candidates:
        pair = eligible[index]
        # Nearby dates from the same station should not fill all 8 slots.
        if all(abs((pair.day - other.day).days) >= 5 for _, other, _ in chosen):
            components = {"absoluteRmse": float(absolute[index]), "shapeRmse": float(shape[index]),
                          "hourlyChangeRmse": float(changes[index]),
                          "seasonalPenalty": float(penalty[index]), "combinedScore": float(combined[index])}
            chosen.append((float(combined[index]), pair, components))
            if len(chosen) == n:
                break
    if len(chosen) < 3:
        raise ValueError("Vēsturē nav pietiekami daudz pilnu HTDRY 24+24h pāru.")
    return target, chosen, len(candidates), len(station_ids)


def find_analogues(riga_data, target_day, pairs, n=8):
    """Return the selected Rīga LU 24+24h pairs."""
    target, chosen, count, station_count = _ranked_selection(riga_data, target_day, pairs, n)
    return target, [(score, pair) for score, pair, _ in chosen], count, station_count


def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def find_observed_day_match(days, actual, forecast_day, station_names, min_observed=6):
    observed = [(hour, value) for hour, value in enumerate(actual) if value is not None]
    if len(observed) < min_observed:
        return None
    cutoff = forecast_day - timedelta(days=8)
    eligible = [record for record in days
                if record.station == RIGA_STATION_ID and record.day <= cutoff]
    if not eligible:
        return None
    indices = [hour for hour, _ in observed]
    temperatures = np.asarray([value for _, value in observed], dtype=np.float64)
    curves = np.asarray([record.values for record in eligible], dtype=np.float64)
    errors = np.sqrt(np.mean((curves[:, indices] - temperatures) ** 2, axis=1))
    best_index = int(np.argmin(errors))
    error, record = float(errors[best_index]), eligible[best_index]
    return {"date": record.day.isoformat(), "stationId": record.station,
            "station": station_names.get(record.station, record.station),
            "source": "HTDRY", "rmse": round(error, 2),
            "observedHours": len(observed), "values": record.values}


def hourly_day_normal(days, forecast_day):
    """Mean of each local hour on this calendar date in earlier complete Rīga LU years."""
    samples = [record for record in days
               if record.station == RIGA_STATION_ID
               and record.day.year < forecast_day.year
               and record.day.month == forecast_day.month
               and record.day.day == forecast_day.day
               and len(record.values) == 24]
    if not samples:
        return None, []
    values = [round(mean(record.values[hour] for record in samples), 2)
              for hour in range(24)]
    return values, sorted(record.day.year for record in samples)


def daily_profile_similarity(target_days, candidate_days, comparison_days):
    """Compare each local day's shape and interpretable within-day features."""
    terms = {key: [] for key in ("shapeRmse", "nightChangeMae", "morningChangeMae",
                                  "amplitudeMae", "jumpMae", "peakHourMae")}
    for day in comparison_days:
        target, candidate = target_days[day], candidate_days[day]
        target_mean, candidate_mean = mean(target), mean(candidate)
        target_changes = [target[i + 1] - target[i] for i in range(23)]
        candidate_changes = [candidate[i + 1] - candidate[i] for i in range(23)]
        terms["shapeRmse"].append(rmse(
            [value - target_mean for value in target],
            [value - candidate_mean for value in candidate]))
        terms["nightChangeMae"].append(abs((target[6] - target[0]) -
                                            (candidate[6] - candidate[0])))
        terms["morningChangeMae"].append(abs((target[12] - target[6]) -
                                              (candidate[12] - candidate[6])))
        terms["amplitudeMae"].append(abs((max(target) - min(target)) -
                                          (max(candidate) - min(candidate))))
        terms["jumpMae"].append((abs(max(target_changes) - max(candidate_changes)) +
                                  abs(min(target_changes) - min(candidate_changes))) / 2)
        terms["peakHourMae"].append(abs(target.index(max(target)) -
                                         candidate.index(max(candidate))))
    parts = {key: mean(values) for key, values in terms.items()}
    score = (.40 * parts["shapeRmse"] + .12 * parts["nightChangeMae"] +
             .12 * parts["morningChangeMae"] + .14 * parts["amplitudeMae"] +
             .14 * parts["jumpMae"] + .08 * .25 * parts["peakHourMae"])
    return score, parts


def multi_day_similarity(target_days, candidate_days, comparison_days):
    """Compare daily mean trajectories, contiguous warming/cooling and amplitude."""
    target_means = [mean(target_days[day]) for day in comparison_days]
    candidate_means = [mean(candidate_days[day]) for day in comparison_days]
    target_center, candidate_center = mean(target_means), mean(candidate_means)
    level_shape = rmse([value - target_center for value in target_means],
                       [value - candidate_center for value in candidate_means])
    target_changes, candidate_changes = [], []
    target_three, candidate_three = [], []
    for i in range(1, len(comparison_days)):
        if comparison_days[i] - comparison_days[i - 1] == 1:
            target_changes.append(target_means[i] - target_means[i - 1])
            candidate_changes.append(candidate_means[i] - candidate_means[i - 1])
    for i in range(2, len(comparison_days)):
        if comparison_days[i] - comparison_days[i - 2] == 2:
            target_three.append(target_means[i] - target_means[i - 2])
            candidate_three.append(candidate_means[i] - candidate_means[i - 2])
    change_rmse = rmse(target_changes, candidate_changes) if target_changes else None
    three_day_rmse = rmse(target_three, candidate_three) if target_three else None
    amplitude_mae = mean(abs((max(target_days[day]) - min(target_days[day])) -
                             (max(candidate_days[day]) - min(candidate_days[day])))
                         for day in comparison_days)
    weighted = [(.20, level_shape), (.15, amplitude_mae)]
    if change_rmse is not None:
        weighted.append((.40, change_rmse))
    if three_day_rmse is not None:
        weighted.append((.25, three_day_rmse))
    score = sum(weight * value for weight, value in weighted) / sum(weight for weight, _ in weighted)
    return score, {"dailyMeanShapeRmse": level_shape, "dailyChangeRmse": change_rmse,
                   "threeDayChangeRmse": three_day_rmse, "amplitudeMae": amplitude_mae,
                   "consecutiveTransitions": len(target_changes), "threeDayWindows": len(target_three)}


def make_october_analogues(days, target_year, today, period="all", method="temperature"):
    """Rank same-hour October histories; later days are display-only continuations."""
    if period not in {"all", "10", "7"}:
        raise ValueError("Periods ir all, 10 vai 7.")
    if method not in {"temperature", "profile", "regime"}:
        raise ValueError("Metode ir temperature, profile vai regime.")
    cutoff = min(today - timedelta(days=1), date(target_year, 10, 31))
    target_days = {record.day.day: record.values for record in days
                   if record.station == RIGA_STATION_ID
                   and record.day.year == target_year and record.day.month == 10
                   and record.day <= cutoff and len(record.values) == 24}
    if not target_days:
        raise ValueError("Mērķa oktobrī vēl nav pilnas Rīgas LU HTDRY dienas.")
    end_day = max(target_days)
    start_day = 1 if period == "all" else max(1, end_day - int(period) + 1)
    comparison_days = [day for day in range(start_day, end_day + 1) if day in target_days]
    target = [value for day in comparison_days for value in target_days[day]]
    target_mean = mean(target)
    historic = {}
    for record in days:
        if (record.station == RIGA_STATION_ID and record.day.month == 10
                and record.day.year < target_year and len(record.values) == 24):
            historic.setdefault(record.day.year, {})[record.day.day] = record.values
    candidates = []
    for year, year_days in historic.items():
        if any(day not in year_days for day in comparison_days):
            continue
        candidate = [value for day in comparison_days for value in year_days[day]]
        candidate_mean = mean(candidate)
        mae = mean(abs(a - b) for a, b in zip(target, candidate))
        absolute_rmse = rmse(target, candidate)
        shape_rmse = rmse([value - target_mean for value in target],
                          [value - candidate_mean for value in candidate])
        temperature_score = .3 * mae + .4 * absolute_rmse + .3 * shape_rmse
        profile_score, profile_parts = daily_profile_similarity(
            target_days, year_days, comparison_days)
        regime_score, regime_parts = multi_day_similarity(
            target_days, year_days, comparison_days)
        scores = {"temperature": temperature_score, "profile": profile_score,
                  "regime": regime_score}
        candidates.append((scores[method], year, mae, absolute_rmse, shape_rmse,
                           candidate, year_days, scores, profile_parts, regime_parts))
    candidates.sort(key=lambda row: (row[0], row[1]))
    matches = []
    for (score, year, mae, absolute_rmse, shape_rmse, candidate, year_days,
         scores, profile_parts, regime_parts) in candidates[:5]:
        continuation = [list(year_days[day]) if day in year_days else None
                        for day in range(end_day + 1, 32)]
        matches.append({
            "year": year, "stationId": RIGA_STATION_ID, "element": "HTDRY",
            "score": round(score, 3), "mae": round(mae, 2),
            "rmse": round(absolute_rmse, 2), "shapeRmse": round(shape_rmse, 2),
            "methodScores": {key: round(value, 3) for key, value in scores.items()},
            "profile": {key: round(value, 2) for key, value in profile_parts.items()},
            "regime": {key: round(value, 2) if isinstance(value, float) else value
                       for key, value in regime_parts.items()},
            "comparisonValues": candidate,
            "continuationDays": continuation,
            "completeContinuationDays": sum(values is not None for values in continuation),
        })
    return {"targetYear": target_year, "stationId": RIGA_STATION_ID,
            "element": "HTDRY", "period": period, "method": method,
            "startDay": start_day,
            "endDay": end_day, "comparisonDays": comparison_days,
            "comparisonHours": len(target),
            "candidateYears": len(candidates),
            "targetDays": [list(target_days[day]) if day in target_days else None
                           for day in range(1, end_day + 1)],
            "matches": matches}


def make_forecast(riga_data, target_day, days, pairs, station_names):
    target, selected, candidate_count, station_count = _ranked_selection(riga_data, target_day, pairs)
    matches = [(score, pair) for score, pair, _ in selected]
    start, _ = local_day_bounds(target_day)
    forecast_day = target_day + timedelta(days=1)
    future_start, future_end = local_day_bounds(forecast_day)
    if future_end - future_start != 24:
        raise ValueError("Vasaras laika pārejas dienai 24h izmēģinājums nav pieejams.")

    weights = [1 / (score + 0.35) ** 2 for score, _ in matches]
    total_weight = sum(weights)
    forecast, lower, upper, best = [], [], [], []
    for hour in range(24):
        shifted = [target[-1] + pair.next_values[hour] - pair.values[-1] for _, pair in matches]
        forecast.append(round(sum(value * weight for value, weight in zip(shifted, weights)) / total_weight, 2))
        lower.append(round(percentile(shifted, 0.1), 2))
        upper.append(round(percentile(shifted, 0.9), 2))
        best.append(round(shifted[0], 2))

    actual = [riga_data.get(future_start + hour) for hour in range(24)]
    normal_values, normal_years = hourly_day_normal(days, forecast_day)
    observed_match = find_observed_day_match(days, actual, forecast_day, station_names)
    observed_pairs = [(f, a) for f, a in zip(forecast, actual) if a is not None]
    return {
        "targetDate": target_day.isoformat(), "forecastDate": forecast_day.isoformat(),
        "input": [[(start + i) * 3600000, value] for i, value in enumerate(target)],
        "forecast": [[(future_start + i) * 3600000, value] for i, value in enumerate(forecast)],
        "normal": [[(future_start + i) * 3600000, value] for i, value in enumerate(normal_values)]
                  if normal_values is not None else [],
        "normalSampleDays": len(normal_years), "normalYears": normal_years,
        "lower": lower, "upper": upper, "bestAnalogue": best,
        "actual": [[(future_start + i) * 3600000, value] for i, value in enumerate(actual)],
        "observedDayMatch": observed_match,
        "matches": [{"date": pair.day.isoformat(), "stationId": pair.station,
                     "station": station_names.get(pair.station, pair.station),
                     "source": "HTDRY", "score": round(score, 2),
                     "rawRmse": round(components["absoluteRmse"], 2),
                     "anchorShift": round(target[-1] - pair.values[-1], 2),
                     "continuation": [round(target[-1] + value - pair.values[-1], 2)
                                      for value in pair.next_values],
                     "nextMean": round(mean(pair.next_values), 2)}
                    for score, pair, components in selected],
        "candidates": candidate_count, "candidateStations": station_count,
        "stationCount": station_count,
        "mae": round(mean(abs(f - a) for f, a in observed_pairs), 2) if observed_pairs else None,
        "rmse": round(rmse([f for f, _ in observed_pairs], [a for _, a in observed_pairs]), 2)
                if observed_pairs else None,
        "actualCount": len(observed_pairs),
        "currentActual": next((value for value in reversed(actual) if value is not None), None),
    }


def make_month_overview(riga_data, year, month, today, days, pairs, station_names):
    """Replay each past day from its preceding 24h; summarize only observed hours."""
    entries = []
    absolute_errors = []
    square_errors = []
    complete_days = 0
    for day_number in range(1, calendar.monthrange(year, month)[1] + 1):
        forecast_day = date(year, month, day_number)
        input_day = forecast_day - timedelta(days=1)
        entry = {"date": forecast_day.isoformat(), "inputDate": input_day.isoformat()}
        if forecast_day > today:
            entry["status"] = "future"
        else:
            try:
                result = make_forecast(riga_data, input_day, days, pairs, station_names)
            except ValueError as error:
                entry.update(status="unavailable", reason=str(error))
            else:
                count = result["actualCount"]
                entry.update(status="complete" if count == 24 else "partial" if count else "unobserved",
                             actualCount=count, mae=result["mae"], rmse=result["rmse"])
                if count == 24:
                    complete_days += 1
                    for forecast_point, actual_point in zip(result["forecast"], result["actual"]):
                        difference = forecast_point[1] - actual_point[1]
                        absolute_errors.append(abs(difference))
                        square_errors.append(difference * difference)
        entries.append(entry)
    return {"month": f"{year:04d}-{month:02d}", "stationId": RIGA_STATION_ID,
            "element": "HTDRY", "days": entries, "completeDays": complete_days,
            "mae": round(mean(absolute_errors), 2) if absolute_errors else None,
            "rmse": round(math.sqrt(mean(square_errors)), 2) if square_errors else None}
