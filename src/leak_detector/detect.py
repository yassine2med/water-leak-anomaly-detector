"""Load hourly meter readings and flag overnight flow anomalies."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class Reading:
    """Water used by one meter during one hour, in gallons."""

    timestamp: datetime
    meter: str
    gallons: float


@dataclass(frozen=True)
class NightSummary:
    """Flow for one meter during the night window of one date."""

    meter: str
    day: date
    minimum: float
    mean: float
    hours: int


@dataclass(frozen=True)
class Finding:
    """One flagged night."""

    meter: str
    day: date
    kind: str
    detail: str


def load_readings(path: str | Path) -> list[Reading]:
    """Read a CSV with columns timestamp, meter, gallons. Raise ValueError on bad rows."""
    readings: list[Reading] = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"timestamp", "meter", "gallons"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing columns: {', '.join(sorted(missing))}")
        for number, row in enumerate(reader, start=2):
            try:
                gallons = float(row["gallons"])
                stamp = datetime.fromisoformat(row["timestamp"])
            except ValueError as exc:
                raise ValueError(f"line {number}: {exc}") from exc
            if gallons < 0:
                raise ValueError(f"line {number}: negative gallons")
            readings.append(Reading(stamp, row["meter"].strip(), gallons))
    return readings


def nightly_summary(readings: list[Reading], night_start: int = 1, night_end: int = 5) -> list[NightSummary]:
    """Summarize each meter and date over hours night_start up to, not including, night_end.

    Only nights with every hour present are returned.
    """
    if not 0 <= night_start < night_end <= 24:
        raise ValueError("night window must satisfy 0 <= start < end <= 24")
    wanted = night_end - night_start
    groups: dict[tuple[str, date], list[float]] = defaultdict(list)
    for item in readings:
        if night_start <= item.timestamp.hour < night_end:
            groups[(item.meter, item.timestamp.date())].append(item.gallons)
    summaries = [
        NightSummary(meter, day, min(values), statistics.fmean(values), len(values))
        for (meter, day), values in groups.items()
        if len(values) == wanted
    ]
    return sorted(summaries, key=lambda s: (s.meter, s.day))


def detect(summaries: list[NightSummary], min_flow: float = 5.0, ratio: float = 3.0) -> list[Finding]:
    """Flag nights that look like a leak.

    constant_flow: the lowest night hour is at or above min_flow gallons, so water
    never stopped. surge: the night mean is more than ratio times the meter's
    median night mean (needs at least 3 nights).
    """
    findings: list[Finding] = []
    by_meter: dict[str, list[NightSummary]] = defaultdict(list)
    for item in summaries:
        by_meter[item.meter].append(item)
    for meter, nights in by_meter.items():
        baseline = statistics.median(n.mean for n in nights) if len(nights) >= 3 else None
        for night in nights:
            if night.minimum >= min_flow:
                findings.append(Finding(meter, night.day, "constant_flow",
                                        f"lowest night hour {night.minimum:.1f} gal, never stopped"))
            if baseline and baseline > 0 and night.mean > ratio * baseline:
                findings.append(Finding(meter, night.day, "surge",
                                        f"night mean {night.mean:.1f} gal vs median {baseline:.1f}"))
    return sorted(findings, key=lambda f: (f.meter, f.day, f.kind))
