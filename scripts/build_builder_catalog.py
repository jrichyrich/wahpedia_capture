import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 2
STATS_ORDER = ("M", "T", "Sv", "W", "Ld", "OC")
SECTION_EXCLUDES = {"ABILITIES", "UNIT COMPOSITION"}
POINTS_LABEL_HINTS = ("model", "models")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_source_root() -> Path:
    return repo_root() / "out" / "json"


def default_output_root() -> Path:
    return repo_root() / "out" / "builder"


def default_docs_data_root() -> Path:
    return repo_root() / "docs" / "builder" / "data"


def slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "option"


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_label_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def parse_points_value(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else None


def parse_model_count_label(label: str) -> int | None:
    numbers = [int(number) for number in re.findall(r"\d+", label or "")]
    if not numbers:
        return None

    lowered = normalize_label_key(label)
    if " and " in lowered and len(numbers) >= 2:
        return sum(numbers)

    leading = re.match(r"^\s*(\d+)\b", label or "")
    if leading:
        return int(leading.group(1))

    if len(numbers) == 1:
        return numbers[0]

    return None


def parse_model_range(line: str) -> dict[str, object] | None:
    match = re.match(r"^\s*(\d+)(?:-(\d+))?\b", line or "")
    if not match:
        return None
    minimum = int(match.group(1))
    maximum = int(match.group(2) or match.group(1))
    return {
        "label": line,
        "minModels": minimum,
        "maxModels": maximum,
    }


def infer_upgrade_model_count(
    label: str,
    model_count_options: list[dict[str, object]],
) -> int | None:
    label_key = normalize_label_key(label)
    if not label_key:
        return None

    for option in model_count_options:
        option_key = normalize_label_key(str(option.get("label", "")))
        if label_key and label_key in option_key:
            maximum = option.get("maxModels")
            return int(maximum) if isinstance(maximum, int) else None

    if re.match(r"^[a-z][a-z0-9' -]+$", label.strip(), re.IGNORECASE):
        return 1
    return None


def parse_points_row(
    label: str,
    raw_points: object,
    model_count_options: list[dict[str, object]],
) -> dict[str, object]:
    points = parse_points_value(raw_points)
    normalized_label = normalize_space(label)
    lowered = normalize_label_key(normalized_label)
    selection_kind = "manual"
    model_count = None

    if points is None:
        selection_kind = "manual"
    elif any(hint in lowered for hint in POINTS_LABEL_HINTS):
        selection_kind = "models"
        model_count = parse_model_count_label(normalized_label)
    elif " and " in lowered:
        selection_kind = "mixed"
        model_count = parse_model_count_label(normalized_label)
    elif re.match(r"^\s*\d+\b", normalized_label):
        selection_kind = "models"
        model_count = parse_model_count_label(normalized_label)
    elif str(raw_points).strip().startswith("+"):
        selection_kind = "upgrade"
        model_count = infer_upgrade_model_count(normalized_label, model_count_options)
    else:
        inferred_count = infer_upgrade_model_count(normalized_label, model_count_options)
        if inferred_count is not None:
            selection_kind = "upgrade"
            model_count = inferred_count

    return {
        "label": normalized_label,
        "points": points,
        "modelCount": model_count,
        "selectionKind": selection_kind,
    }


def normalize_weapon(raw_weapon: dict[str, object], skill_key: str) -> dict[str, object]:
    return {
        "name": raw_weapon.get("name"),
        "range": raw_weapon.get("range"),
        "a": raw_weapon.get("a"),
        "skill": raw_weapon.get(skill_key),
        "skillType": skill_key.upper(),
        "s": raw_weapon.get("s"),
        "ap": raw_weapon.get("ap"),
        "d": raw_weapon.get("d"),
        "abilities": list(raw_weapon.get("abilities", [])),
    }


def normalize_entry(entry: dict[str, object]) -> dict[str, object]:
    entry_type = entry.get("type")
    normalized = {"type": entry_type}
    if entry_type == "list":
        normalized["items"] = list(entry.get("items", []))
    elif entry_type == "tagged_list":
        normalized["label"] = entry.get("label")
        normalized["items"] = list(entry.get("items", []))
    elif entry_type == "statement":
        normalized["label"] = entry.get("label")
        normalized["text"] = entry.get("text")
    elif entry_type == "rule":
        normalized["name"] = entry.get("name")
        normalized["text"] = entry.get("text")
    elif entry_type == "text":
        normalized["text"] = entry.get("text")
    elif entry_type == "points":
        normalized["rows"] = [
            {
                "label": row.get("label"),
                "points": parse_points_value(row.get("points")),
            }
            for row in entry.get("rows", [])
        ]
    return normalized


def normalize_render_block(section: dict[str, object]) -> dict[str, object]:
    title = str(section.get("title", ""))
    return {
        "title": title,
        "displayStyle": "damaged" if title.upper().startswith("DAMAGED:") else "section",
        "entries": [normalize_entry(entry) for entry in section.get("entries", [])],
    }


def build_composition(unit_composition: list[dict[str, object]]) -> dict[str, object]:
    raw_lines: list[str] = []
    statements: list[dict[str, object]] = []
    model_count_options: list[dict[str, object]] = []
    points_options: list[dict[str, object]] = []
    option_ids: Counter[str] = Counter()
    selection_mode = "parsed"

    for entry in unit_composition:
        entry_type = entry.get("type")
        if entry_type == "list":
            items = list(entry.get("items", []))
            raw_lines.extend(items)
            for item in items:
                parsed = parse_model_range(str(item))
                if parsed:
                    model_count_options.append(parsed)
        elif entry_type == "statement":
            label = entry.get("label")
            text = entry.get("text")
            line = f"{label}: {text}" if label else str(text or "")
            if line:
                raw_lines.append(line)
            statements.append({"label": label, "text": text})
        elif entry_type == "points":
            for row in entry.get("rows", []):
                option = parse_points_row(
                    label=str(row.get("label", "Option")),
                    raw_points=row.get("points"),
                    model_count_options=model_count_options,
                )
                if option["selectionKind"] == "manual" or option["points"] is None:
                    selection_mode = "manual"
                option_id = slugify(str(option["label"]))
                option_ids[option_id] += 1
                if option_ids[option_id] > 1:
                    option_id = f"{option_id}-{option_ids[option_id]}"
                option["id"] = option_id
                points_options.append(option)

    if not points_options:
        selection_mode = "manual"

    return {
        "rawLines": raw_lines,
        "statements": statements,
        "modelCountOptions": model_count_options,
        "pointsOptions": points_options,
        "selectionMode": selection_mode,
    }


def unit_id_from_card(card: dict[str, object]) -> str:
    source = card.get("source", {})
    datasheet_slug = source.get("datasheet_slug")
    if datasheet_slug:
        return str(datasheet_slug).lower()
    name = str(card.get("name", ""))
    return slugify(name)


def normalize_card(faction_slug: str, card: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    characteristics = card.get("characteristics", {})
    abilities = card.get("abilities", {})
    composition = build_composition(card.get("unit_composition", []))
    source = card.get("source", {})

    normalized = {
        "unitId": unit_id_from_card(card),
        "name": card.get("name"),
        "factionSlug": faction_slug,
        "source": {
            "url": source.get("url"),
            "sourceFactionSlug": source.get("faction_slug"),
            "datasheetSlug": source.get("datasheet_slug"),
            "outputSlug": source.get("output_slug") or faction_slug,
        },
        "baseSize": card.get("base_size"),
        "stats": {
            "M": characteristics.get("M"),
            "T": characteristics.get("T"),
            "Sv": characteristics.get("Sv"),
            "W": characteristics.get("W"),
            "Ld": characteristics.get("Ld"),
            "OC": characteristics.get("OC"),
            "invulnerableSave": characteristics.get("Invulnerable Save"),
        },
        "weapons": {
            "ranged": [
                normalize_weapon(weapon, "bs")
                for weapon in card.get("weapons", {}).get("ranged_weapons", [])
            ],
            "melee": [
                normalize_weapon(weapon, "ws")
                for weapon in card.get("weapons", {}).get("melee_weapons", [])
            ],
        },
        "abilities": {
            "core": list(abilities.get("core", [])),
            "faction": list(abilities.get("faction", [])),
            "datasheet": list(abilities.get("datasheet", [])),
            "other": list(abilities.get("other", [])),
        },
        "composition": {
            "rawLines": composition["rawLines"],
            "statements": composition["statements"],
            "modelCountOptions": composition["modelCountOptions"],
        },
        "pointsOptions": composition["pointsOptions"],
        "selectionMode": composition["selectionMode"],
        "quality": {
            "missingStats": [],
            "hasMissingStats": False,
            "hasManualSelectionLabels": composition["selectionMode"] == "manual",
        },
        "keywords": list(card.get("keywords", [])),
        "factionKeywords": list(card.get("faction_keywords", [])),
        "renderBlocks": [
            normalize_render_block(section)
            for section in card.get("sections", [])
            if str(section.get("title", "")).upper() not in SECTION_EXCLUDES
        ],
    }

    normalized["quality"]["missingStats"] = [
        stat for stat in STATS_ORDER if not normalized["stats"].get(stat)
    ]
    normalized["quality"]["hasMissingStats"] = bool(normalized["quality"]["missingStats"])

    diagnostics = {
        "unitId": normalized["unitId"],
        "name": normalized["name"],
        "missingStats": list(normalized["quality"]["missingStats"]),
        "manualSelection": normalized["selectionMode"] == "manual",
    }
    return normalized, diagnostics


def build_faction_catalog(faction_slug: str, cards: list[dict[str, object]], output_path: Path) -> dict[str, object]:
    units: list[dict[str, object]] = []
    missing_stats: list[dict[str, object]] = []
    manual_units: list[dict[str, object]] = []

    for card in cards:
        unit, diagnostics = normalize_card(faction_slug, card)
        units.append(unit)
        if diagnostics["missingStats"]:
            missing_stats.append(
                {
                    "unitId": diagnostics["unitId"],
                    "name": diagnostics["name"],
                    "missingStats": diagnostics["missingStats"],
                }
            )
        if diagnostics["manualSelection"]:
            manual_units.append(
                {
                    "unitId": diagnostics["unitId"],
                    "name": diagnostics["name"],
                }
            )

    units.sort(key=lambda unit: str(unit.get("name", "")))
    catalog = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "faction": {
            "slug": faction_slug,
            "name": slug_to_title(faction_slug),
            "unitCount": len(units),
        },
        "build": {
            "sourceIndexCount": len(cards),
            "catalogUnitCount": len(units),
            "missingStats": missing_stats,
            "manualSelectionUnits": manual_units,
        },
        "units": units,
    }
    output_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def write_report(output_root: Path, manifest: dict[str, object]) -> None:
    report_dir = output_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = report_dir / "build-report.json"
    report_md_path = report_dir / "build-report.md"

    report_json_path.write_text(json.dumps(manifest["report"], indent=2), encoding="utf-8")

    lines = [
        "# Builder Catalog Build Report",
        "",
        f"- Generated at: {manifest['generatedAt']}",
        f"- Source root: `{manifest['sourceRoot']}`",
        f"- Factions imported: {len(manifest['factions'])}",
        f"- Total units: {manifest['report']['totals']['unitCount']}",
        f"- Units with missing stats: {manifest['report']['totals']['missingStatsCount']}",
        f"- Manual selection units: {manifest['report']['totals']['manualSelectionCount']}",
        "",
        "## Factions",
        "",
    ]

    for faction in manifest["factions"]:
        lines.extend(
            [
                f"### {faction['name']}",
                "",
                f"- Catalog: `{faction['catalogFile']}`",
                f"- Units: {faction['unitCount']}",
                f"- Missing stats: {faction['missingStatsCount']}",
                f"- Manual selection units: {faction['manualSelectionCount']}",
                "",
            ]
        )

    report_md_path.write_text("\n".join(lines), encoding="utf-8")


def publish_docs_data(output_root: Path, docs_data_root: Path) -> None:
    if docs_data_root.exists():
        shutil.rmtree(docs_data_root)
    docs_data_root.mkdir(parents=True, exist_ok=True)
    for child in output_root.iterdir():
        destination = docs_data_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def build_all(source_root: Path, output_root: Path, factions: list[str] | None = None, clean: bool = False) -> dict[str, object]:
    source_root = Path(source_root)
    output_root = Path(output_root)
    if not source_root.exists():
        raise FileNotFoundError(f"Source root not found: {source_root}")

    if clean and output_root.exists():
        shutil.rmtree(output_root)

    catalog_dir = output_root / "catalogs"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    available_factions = sorted(path.name for path in source_root.iterdir() if path.is_dir())
    target_factions = factions or available_factions

    manifest_factions = []
    report_factions = []
    total_units = 0
    total_missing_stats = 0
    total_manual_selection = 0

    for faction_slug in target_factions:
        index_path = source_root / faction_slug / "index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"Faction index not found: {index_path}")
        cards = json.loads(index_path.read_text(encoding="utf-8"))
        output_catalog_path = catalog_dir / f"{faction_slug}.json"
        catalog = build_faction_catalog(faction_slug, cards, output_catalog_path)
        build_info = catalog["build"]

        manifest_factions.append(
            {
                "slug": faction_slug,
                "name": catalog["faction"]["name"],
                "unitCount": catalog["faction"]["unitCount"],
                "catalogFile": f"catalogs/{faction_slug}.json",
                "missingStatsCount": len(build_info["missingStats"]),
                "manualSelectionCount": len(build_info["manualSelectionUnits"]),
            }
        )
        report_factions.append(
            {
                "slug": faction_slug,
                "name": catalog["faction"]["name"],
                "unitCount": catalog["faction"]["unitCount"],
                "missingStats": build_info["missingStats"],
                "manualSelectionUnits": build_info["manualSelectionUnits"],
            }
        )
        total_units += catalog["faction"]["unitCount"]
        total_missing_stats += len(build_info["missingStats"])
        total_manual_selection += len(build_info["manualSelectionUnits"])

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "sourceRoot": str(source_root.resolve()),
        "catalogRoot": "catalogs",
        "reportFile": "reports/build-report.json",
        "factions": manifest_factions,
        "report": {
            "totals": {
                "factionCount": len(manifest_factions),
                "unitCount": total_units,
                "missingStatsCount": total_missing_stats,
                "manualSelectionCount": total_manual_selection,
            },
            "factions": report_factions,
        },
    }

    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_report(output_root, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build roster-oriented builder catalogs from exported faction JSON bundles."
    )
    parser.add_argument("--source-root", default=str(default_source_root()))
    parser.add_argument("--output-root", default=str(default_output_root()))
    parser.add_argument("--docs-data-root", default=str(default_docs_data_root()))
    parser.add_argument("--faction", action="append", dest="factions")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_all(
        source_root=Path(args.source_root),
        output_root=Path(args.output_root),
        factions=args.factions,
        clean=args.clean,
    )
    publish_docs_data(Path(args.output_root), Path(args.docs_data_root))
    totals = manifest["report"]["totals"]
    print(
        f"Built {totals['unitCount']} units across {totals['factionCount']} factions into {args.output_root}"
    )


if __name__ == "__main__":
    main()
