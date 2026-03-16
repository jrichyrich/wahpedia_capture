import argparse
import concurrent.futures
import json
import time
from pathlib import Path

from export_datasheet_json import (
    faction_from_url,
    filtered_items,
    load_manifest,
    normalize_wahapedia_url,
    parse_datasheet,
    slug_from_url,
)


EXPECTED_CHARACTERISTICS = {"M", "T", "Sv", "W", "Ld", "OC"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate datasheet JSON exports across one or more faction manifests."
    )
    parser.add_argument(
        "--output-slug",
        action="append",
        default=[],
        help="Faction output slug to validate. Repeat as needed. Defaults to all manifests.",
    )
    parser.add_argument(
        "--manifest-path",
        action="append",
        default=[],
        help="Explicit manifest path to validate. Repeat as needed.",
    )
    parser.add_argument(
        "--card-slug",
        action="append",
        default=[],
        help="Limit validation to specific datasheet slugs. Repeat as needed.",
    )
    parser.add_argument(
        "--max-cards-per-faction",
        type=int,
        help="Optional cap for faster spot checks.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Optional delay in seconds between requests.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent workers to use per manifest.",
    )
    parser.add_argument(
        "--report-path",
        default="out/validation/datasheet-export-report.json",
        help="Where to write the validation report JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any failures or warnings are found.",
    )
    return parser.parse_args()


def discover_manifests(args: argparse.Namespace) -> list[Path]:
    manifests = [Path(path) for path in args.manifest_path]
    if args.output_slug:
        manifests.extend(
            Path("out") / "source" / f"{output_slug}-links.json"
            for output_slug in args.output_slug
        )

    if manifests:
        return manifests

    return sorted(Path("out/source").glob("*-links.json"))


def limit_items(items: list[dict[str, str]], max_cards_per_faction: int | None) -> list[dict[str, str]]:
    if max_cards_per_faction is None:
        return items
    return items[:max_cards_per_faction]


def validate_payload(payload: dict[str, object]) -> list[str]:
    warnings = []
    characteristics = payload.get("characteristics", {})
    if not isinstance(characteristics, dict):
        warnings.append("characteristics not parsed as an object")
    else:
        missing_characteristics = sorted(EXPECTED_CHARACTERISTICS.difference(characteristics))
        if missing_characteristics:
            warnings.append(
                "missing core characteristics: " + ", ".join(missing_characteristics)
            )

    sections = payload.get("sections", [])
    if not isinstance(sections, list) or not sections:
        warnings.append("no right-column sections parsed")
    else:
        section_titles = {section.get("title") for section in sections}
        if "ABILITIES" not in section_titles:
            warnings.append("ABILITIES section missing")
        if "UNIT COMPOSITION" not in section_titles:
            warnings.append("UNIT COMPOSITION section missing")

    if not payload.get("keywords"):
        warnings.append("keywords missing")
    if not payload.get("faction_keywords"):
        warnings.append("faction keywords missing")

    abilities = payload.get("abilities", {})
    if not isinstance(abilities, dict):
        warnings.append("abilities not parsed as an object")

    if not payload.get("name"):
        warnings.append("name missing")
    if not payload.get("source", {}).get("datasheet_slug"):
        warnings.append("source datasheet slug missing")

    return warnings


def validate_manifest(
    manifest_path: Path,
    card_slugs: list[str],
    max_cards_per_faction: int | None,
    delay: float,
    workers: int,
) -> dict[str, object]:
    items = load_manifest(manifest_path)
    items = filtered_items(items, card_slugs)
    items = limit_items(items, max_cards_per_faction)

    faction_slug = manifest_path.name.removesuffix("-links.json")
    results = []
    success_count = 0
    failure_count = 0
    warning_count = 0

    print(f"\nFaction {faction_slug}: validating {len(items)} datasheets", flush=True)

    def validate_item(index: int, item: dict[str, str]) -> tuple[int, dict[str, object]]:
        url = item["href"]
        normalized_url = normalize_wahapedia_url(url)
        slug = slug_from_url(url)
        record = {
            "slug": slug,
            "url": url,
            "normalized_url": normalized_url,
            "status": "ok",
            "warnings": [],
        }

        try:
            payload = parse_datasheet(normalized_url)
            parsed_faction = faction_from_url(normalized_url)
            if parsed_faction != faction_slug:
                record["warnings"].append(
                    f"faction mismatch: manifest={faction_slug}, page={parsed_faction}"
                )
            if payload.get("source", {}).get("datasheet_slug") != slug:
                record["warnings"].append("datasheet slug mismatch in payload source")
            record["warnings"].extend(validate_payload(payload))
        except Exception as error:
            record["status"] = "error"
            record["error"] = str(error)

        return index, record

    if workers <= 1:
        indexed_results = []
        for index, item in enumerate(items, start=1):
            indexed_results.append(validate_item(index, item))
            if delay and index < len(items):
                time.sleep(delay)
    else:
        indexed_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(validate_item, index, item): index
                for index, item in enumerate(items, start=1)
            }
            for future in concurrent.futures.as_completed(futures):
                indexed_results.append(future.result())
                if delay:
                    time.sleep(delay)

    for index, record in sorted(indexed_results, key=lambda value: value[0]):
        if record["status"] == "error":
            failure_count += 1
        else:
            success_count += 1
            if record["warnings"]:
                warning_count += 1

        status_text = record["status"]
        if record["warnings"]:
            status_text += f" ({len(record['warnings'])} warnings)"
        print(f"[{index}/{len(items)}] {record['slug']}: {status_text}", flush=True)
        results.append(record)

    return {
        "manifest_path": str(manifest_path.resolve()),
        "faction_slug": faction_slug,
        "datasheet_count": len(items),
        "success_count": success_count,
        "failure_count": failure_count,
        "warning_count": warning_count,
        "results": results,
    }


def main() -> int:
    args = parse_args()
    manifests = discover_manifests(args)
    if not manifests:
        raise SystemExit("No manifests found to validate.")

    report = {
        "generated_at_epoch": time.time(),
        "manifests": [],
    }

    total_datasheets = 0
    total_success = 0
    total_failures = 0
    total_warning_records = 0

    for manifest_path in manifests:
        if not manifest_path.exists():
            report["manifests"].append(
                {
                    "manifest_path": str(manifest_path.resolve()),
                    "faction_slug": manifest_path.name.removesuffix("-links.json"),
                    "datasheet_count": 0,
                    "success_count": 0,
                    "failure_count": 1,
                    "warning_count": 0,
                    "results": [
                        {
                            "slug": None,
                            "url": None,
                            "status": "error",
                            "warnings": [],
                            "error": f"Manifest not found: {manifest_path}",
                        }
                    ],
                }
            )
            total_failures += 1
            continue

        manifest_report = validate_manifest(
            manifest_path=manifest_path,
            card_slugs=args.card_slug,
            max_cards_per_faction=args.max_cards_per_faction,
            delay=args.delay,
            workers=max(1, args.workers),
        )
        report["manifests"].append(manifest_report)
        total_datasheets += manifest_report["datasheet_count"]
        total_success += manifest_report["success_count"]
        total_failures += manifest_report["failure_count"]
        total_warning_records += manifest_report["warning_count"]

    report["summary"] = {
        "manifest_count": len(report["manifests"]),
        "datasheet_count": total_datasheets,
        "success_count": total_success,
        "failure_count": total_failures,
        "warning_count": total_warning_records,
    }

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nSummary", flush=True)
    print(f"Manifests: {report['summary']['manifest_count']}", flush=True)
    print(f"Datasheets: {report['summary']['datasheet_count']}", flush=True)
    print(f"Successes: {report['summary']['success_count']}", flush=True)
    print(f"Failures: {report['summary']['failure_count']}", flush=True)
    print(f"Warning records: {report['summary']['warning_count']}", flush=True)
    print(f"Report: {report_path.resolve()}", flush=True)

    if args.strict and (
        report["summary"]["failure_count"] > 0 or report["summary"]["warning_count"] > 0
    ):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
