"""Command line entry: python -m leak_detector READINGS.csv"""

import argparse
import sys

from .detect import detect, load_readings, nightly_summary


def main(argv: list[str] | None = None) -> int:
    """Print findings; return 1 when any exist, 0 when none, 2 on bad input."""
    parser = argparse.ArgumentParser(prog="leak_detector", description="Flag overnight water flow that suggests a leak.")
    parser.add_argument("file")
    parser.add_argument("--night-start", type=int, default=1, help="first night hour (default 1)")
    parser.add_argument("--night-end", type=int, default=5, help="hour the night window ends, exclusive (default 5)")
    parser.add_argument("--min-flow", type=float, default=5.0, help="gallons per hour that count as constant flow (default 5)")
    parser.add_argument("--ratio", type=float, default=3.0, help="surge multiple of the median night (default 3)")
    parser.add_argument("--meter", help="only this meter")
    args = parser.parse_args(argv)
    try:
        readings = load_readings(args.file)
        if args.meter:
            readings = [r for r in readings if r.meter == args.meter]
        summaries = nightly_summary(readings, args.night_start, args.night_end)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = detect(summaries, args.min_flow, args.ratio)
    print(f"{len(summaries)} nights checked, {len(findings)} flagged")
    for f in findings:
        print(f"{f.meter:<12} {f.day}  {f.kind:<13} {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
