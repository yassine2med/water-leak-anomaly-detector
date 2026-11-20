from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from leak_detector import Reading, detect, load_readings, nightly_summary
from leak_detector.__main__ import main

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "hourly_water.csv"


def day_readings(day: int, night_value: float, meter: str = "M1") -> list[Reading]:
    base = datetime(2026, 6, 1) + timedelta(days=day)
    return [Reading(base + timedelta(hours=h), meter, night_value if 1 <= h < 5 else 20.0) for h in range(24)]


def test_nightly_summary_uses_window_only():
    summary = nightly_summary(day_readings(0, 1.0))
    assert len(summary) == 1
    assert summary[0].minimum == 1.0 and summary[0].hours == 4


def test_incomplete_night_skipped():
    partial = [r for r in day_readings(0, 1.0) if r.timestamp.hour != 3]
    assert nightly_summary(partial) == []


def test_bad_window_rejected():
    with pytest.raises(ValueError):
        nightly_summary([], 5, 2)


def test_constant_flow_flagged():
    findings = detect(nightly_summary(day_readings(0, 8.0)))
    assert [f.kind for f in findings] == ["constant_flow"]


def test_quiet_night_not_flagged():
    assert detect(nightly_summary(day_readings(0, 0.0))) == []


def test_surge_vs_median():
    readings = []
    for d, v in enumerate([1.0, 1.0, 1.0, 1.0, 4.5]):
        readings += day_readings(d, v)
    findings = detect(nightly_summary(readings), min_flow=10.0)
    assert [(f.kind, f.day) for f in findings] == [("surge", date(2026, 6, 5))]


def test_surge_needs_three_nights():
    readings = day_readings(0, 1.0) + day_readings(1, 5.0)
    assert detect(nightly_summary(readings), min_flow=10.0) == []


def test_meters_separate():
    readings = day_readings(0, 9.0, "A") + day_readings(0, 0.0, "B")
    assert {f.meter for f in detect(nightly_summary(readings))} == {"A"}


def test_load_example():
    readings = load_readings(EXAMPLE)
    assert len(readings) == 3 * 14 * 24


def test_load_rejects_negative(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("timestamp,meter,gallons\n2026-06-01T01:00:00,M,-4\n")
    with pytest.raises(ValueError, match="negative"):
        load_readings(bad)


def test_load_rejects_missing_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("timestamp,meter\n")
    with pytest.raises(ValueError, match="missing"):
        load_readings(bad)


def test_cli_exit_codes(capsys):
    assert main([str(EXAMPLE)]) == 1
    assert "constant_flow" in capsys.readouterr().out
    assert main([str(EXAMPLE), "--meter", "Bldg-A-Main"]) == 0
    assert main(["nope.csv"]) == 2
