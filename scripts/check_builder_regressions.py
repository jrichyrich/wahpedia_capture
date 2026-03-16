import argparse
import json
import tempfile
from pathlib import Path

from build_builder_catalog import build_all, default_source_root


EXPECTED_WARNING_BASELINE = {
    "missingStatsCount": 0,
    "manualSelectionCount": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild builder catalogs in a temp directory and fail if warning counts regress."
    )
    parser.add_argument("--source-root", default=str(default_source_root()))
    parser.add_argument(
        "--expected-missing-stats",
        type=int,
        default=EXPECTED_WARNING_BASELINE["missingStatsCount"],
    )
    parser.add_argument(
        "--expected-manual-selection",
        type=int,
        default=EXPECTED_WARNING_BASELINE["manualSelectionCount"],
    )
    return parser.parse_args()


def source_index_counts(source_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for faction_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        index_path = faction_dir / "index.json"
        if not index_path.exists():
            continue
        counts[faction_dir.name] = len(json.loads(index_path.read_text(encoding="utf-8")))
    return counts


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root)
    expected_counts = source_index_counts(source_root)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir) / "builder"
        manifest = build_all(source_root=source_root, output_root=output_root, clean=True)

    failures: list[str] = []
    totals = manifest["report"]["totals"]

    if totals["missingStatsCount"] > args.expected_missing_stats:
        failures.append(
            f"missingStatsCount regressed: {totals['missingStatsCount']} > {args.expected_missing_stats}"
        )
    if totals["manualSelectionCount"] > args.expected_manual_selection:
        failures.append(
            f"manualSelectionCount regressed: {totals['manualSelectionCount']} > {args.expected_manual_selection}"
        )

    manifest_counts = {entry["slug"]: entry["unitCount"] for entry in manifest["factions"]}
    if manifest_counts != expected_counts:
        failures.append(
            f"catalog unit counts do not match source indexes: expected {expected_counts}, got {manifest_counts}"
        )

    if failures:
        print("Builder regression check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        "Builder regression check passed: "
        f"{totals['unitCount']} units across {totals['factionCount']} factions, "
        f"{totals['missingStatsCount']} missing-stat units, "
        f"{totals['manualSelectionCount']} manual-selection units."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
