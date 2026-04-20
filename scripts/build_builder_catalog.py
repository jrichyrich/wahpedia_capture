import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from datasheet_schema import EXPORT_SCHEMA_VERSION, PARSER_VERSION
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from datasheet_schema import EXPORT_SCHEMA_VERSION, PARSER_VERSION


SCHEMA_VERSION = 6
FACTION_RULES_SCHEMA_VERSION = 1
STATS_ORDER = ("M", "T", "Sv", "W", "Ld", "OC")
SECTION_EXCLUDES = {"ABILITIES", "UNIT COMPOSITION", "WARGEAR OPTIONS"}
POINTS_LABEL_HINTS = ("model", "models")
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
NUMBER_PATTERN = r"(?:\d+|" + "|".join(NUMBER_WORDS.keys()) + r")"


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


def default_source_cards_root() -> Path:
    return repo_root() / "out" / "factions"


def default_faction_rules_root() -> Path:
    return repo_root() / "out" / "faction_rules"


def slug_to_title(slug: str) -> str:
    if slug == "t-au-empire":
        return "T'au Empire"
    return slug.replace("-", " ").title()


def parent_faction_slug(cards: list[dict[str, object]], faction_slug: str) -> str:
    source_slugs: set[str] = set()
    for card in cards:
        source = card.get("source", {}) if isinstance(card, dict) else {}
        source_slug = str(
            source.get("faction_slug")
            or source.get("factionSlug")
            or source.get("output_slug")
            or source.get("outputSlug")
            or ""
        ).strip()
        if source_slug:
            source_slugs.add(source_slug)

    if len(source_slugs) != 1:
        return ""

    source_slug = next(iter(source_slugs))
    if source_slug == faction_slug:
        return ""
    return source_slug


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "option"


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_label_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def empty_rules() -> dict[str, object]:
    return {
        "armyRules": [],
        "detachments": [],
    }


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def support_metadata_from_unit(unit: dict[str, object]) -> dict[str, object]:
    quality = unit.get("quality", {}) if isinstance(unit, dict) else {}
    support_reasons: list[str] = []
    if quality.get("hasMissingStats"):
        support_reasons.append("missing_stats")
    if quality.get("hasManualSelectionLabels"):
        support_reasons.append("manual_selection_labels")
    if quality.get("hasManualWargearOptions"):
        support_reasons.append("manual_wargear")

    return {
        "supportLevel": "partial" if support_reasons else "full",
        "supportReasons": support_reasons,
        "previewSupport": "configured-only",
    }


def load_export_manifest(source_root: Path) -> dict[str, object]:
    manifest_path = Path(source_root) / "export-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Export manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
        raise ValueError(f"Export manifest has unexpected shape: {manifest_path}")
    return manifest


def filter_export_manifest_records(
    records: list[dict[str, object]],
    target_factions: list[str],
) -> list[dict[str, object]]:
    target = set(target_factions)
    return [
        record
        for record in records
        if str(record.get("outputSlug") or "") in target
    ]


def validate_export_contract(
    source_root: Path,
    target_factions: list[str],
) -> dict[tuple[str, str], dict[str, object]]:
    manifest = load_export_manifest(source_root)
    if manifest.get("exportSchemaVersion") != EXPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Export manifest schema version mismatch: expected {EXPORT_SCHEMA_VERSION}, got {manifest.get('exportSchemaVersion')}"
        )
    if manifest.get("parserVersion") != PARSER_VERSION:
        raise ValueError(
            f"Export manifest parser version mismatch: expected {PARSER_VERSION}, got {manifest.get('parserVersion')}"
        )

    records = filter_export_manifest_records(manifest.get("records", []), target_factions)
    stale_records = [
        record
        for record in records
        if record.get("exportSchemaVersion") != EXPORT_SCHEMA_VERSION
        or record.get("parserVersion") != PARSER_VERSION
    ]
    if stale_records:
        sample = stale_records[0]
        raise ValueError(
            "Stale exported datasheet detected: "
            f"{sample.get('outputSlug')}/{sample.get('datasheetSlug')} "
            f"(schema={sample.get('exportSchemaVersion')}, parser={sample.get('parserVersion')})"
        )

    drift_by_source: dict[str, dict[str, list[str]]] = {}
    for record in records:
        canonical_source_id = str(record.get("canonicalSourceId") or "").strip()
        shared_core_hash = str(record.get("sharedCoreHash") or "").strip()
        if not canonical_source_id or not shared_core_hash:
            continue
        entries = drift_by_source.setdefault(canonical_source_id, {})
        entries.setdefault(shared_core_hash, []).append(
            f"{record.get('outputSlug')}/{record.get('datasheetSlug')}"
        )

    drift_sources = [
        (canonical_source_id, variants)
        for canonical_source_id, variants in drift_by_source.items()
        if len(variants) > 1
    ]
    if drift_sources:
        canonical_source_id, variants = sorted(drift_sources, key=lambda item: item[0])[0]
        variant_labels = [
            ", ".join(sorted(entries))
            for _, entries in sorted(variants.items(), key=lambda item: item[0])
        ]
        raise ValueError(
            "Duplicate canonical-source drift detected for "
            f"{canonical_source_id}: " + " | ".join(variant_labels)
        )

    return {
        (str(record.get("outputSlug") or ""), str(record.get("datasheetSlug") or "")): record
        for record in records
    }


def validate_card_export_metadata(
    card: dict[str, object],
    faction_slug: str,
    record_lookup: dict[tuple[str, str], dict[str, object]],
    index_path: Path,
) -> None:
    if card.get("exportSchemaVersion") != EXPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Card export schema version mismatch in {index_path}: expected {EXPORT_SCHEMA_VERSION}, got {card.get('exportSchemaVersion')}"
        )
    if card.get("parserVersion") != PARSER_VERSION:
        raise ValueError(
            f"Card parser version mismatch in {index_path}: expected {PARSER_VERSION}, got {card.get('parserVersion')}"
        )
    source = card.get("source", {})
    output_slug = str(source.get("output_slug") or faction_slug)
    datasheet_slug = str(source.get("datasheet_slug") or "")
    record = record_lookup.get((output_slug, datasheet_slug))
    if not record:
        raise ValueError(
            f"Card missing export-manifest record in {index_path}: {output_slug}/{datasheet_slug}"
        )
    if source.get("canonicalSourceId") != record.get("canonicalSourceId"):
        raise ValueError(
            f"Canonical source mismatch in {index_path}: {output_slug}/{datasheet_slug}"
        )


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
    elif entry_type == "option_group":
        normalized["label"] = entry.get("label")
        normalized["items"] = list(entry.get("items", []))
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


def section_entries(card: dict[str, object], title: str) -> list[dict[str, object]]:
    target = title.upper()
    for section in card.get("sections", []):
        if str(section.get("title", "")).upper() == target:
            return list(section.get("entries", []))
    return []


def normalize_wargear_choice(label: str) -> dict[str, object]:
    value = normalize_space(label)
    value = re.sub(r"\*+$", "", value).strip()
    value = re.sub(r"\.$", "", value).strip()
    return {
        "id": slugify(value),
        "label": value,
    }


def normalize_inline_choice(label: str) -> dict[str, object]:
    value = normalize_space(label)
    value = re.split(r"\.\s+(?:This|That|Those|These)\b", value, maxsplit=1)[0]
    return normalize_wargear_choice(value)


def normalize_wrapper_choice(label: str) -> dict[str, object]:
    value = normalize_space(label)
    value = re.sub(r"^(?:Replace|Be equipped with|Be equipped|Equipped with)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:its|their)\s+.+?\s+with\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:with)\s+", "", value, flags=re.IGNORECASE)
    return normalize_inline_choice(value)


def parse_number_token(value: str | None) -> int | None:
    normalized = normalize_space(value).lower()
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    return NUMBER_WORDS.get(normalized)


def parse_model_count_availability(text: str) -> tuple[dict[str, object] | None, str]:
    value = normalize_space(text)
    patterns = [
        (
            rf"^If this unit contains only ({NUMBER_PATTERN}) models?(?:,|:)\s*(.*)$",
            lambda match: {
                "kind": "modelCountRange",
                "minModels": parse_number_token(match.group(1)),
                "maxModels": parse_number_token(match.group(1)),
            },
        ),
        (
            rf"^If this unit contains ({NUMBER_PATTERN}) models?(?:,|:)\s*(.*)$",
            lambda match: {
                "kind": "modelCountRange",
                "minModels": parse_number_token(match.group(1)),
                "maxModels": parse_number_token(match.group(1)),
            },
        ),
        (
            rf"^If this unit contains ({NUMBER_PATTERN}) or fewer models?(?:,|:)\s*(.*)$",
            lambda match: {
                "kind": "modelCountRange",
                "minModels": None,
                "maxModels": parse_number_token(match.group(1)),
            },
        ),
        (
            rf"^If this unit contains ({NUMBER_PATTERN}) or more models?(?:,|:)\s*(.*)$",
            lambda match: {
                "kind": "modelCountRange",
                "minModels": parse_number_token(match.group(1)),
                "maxModels": None,
            },
        ),
    ]
    for pattern, builder in patterns:
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if match:
            return builder(match), normalize_space(match.group(2))
    return None, value


def singularize_actor(label: str) -> str:
    value = normalize_space(label)
    if not value:
        return value
    value = re.sub(r"^\d+\s+", "", value)
    if value.lower().endswith("troopers"):
        return value[:-1]
    if value.lower().endswith("marines"):
        return value[:-1]
    if value.lower().endswith("guardians"):
        return value[:-1]
    if value.lower().endswith("reapers"):
        return value[:-1]
    if value.lower().endswith("reavers"):
        return value[:-1]
    if value.lower().endswith("models"):
        return "model"
    return value[:-1] if value.lower().endswith("s") and not value.lower().endswith("ss") else value


def infer_pool_basis(target: str | None, eligibility_text: str | None) -> str | None:
    if eligibility_text:
        match = re.search(r"equipped with (?:an? |one )?(.+?)(?: \(.*?\))?$", eligibility_text, flags=re.IGNORECASE)
        if match:
            return normalize_space(match.group(1))
    if target:
        numbered = re.match(rf"^(?:{NUMBER_PATTERN})\s+(.+)$", target, flags=re.IGNORECASE)
        if numbered:
            return normalize_space(numbered.group(1))
        return normalize_space(re.sub(r"^(?:one|two|their|his|her)\s+", "", target, flags=re.IGNORECASE))
    return None


def infer_pool_key(actor: str | None, target: str | None, eligibility_text: str | None) -> str | None:
    actor_value = singularize_actor(actor or "")
    pool_basis = infer_pool_basis(target, eligibility_text)
    if not actor_value or not pool_basis:
        return None
    return slugify(f"{actor_value}-{pool_basis}")


def parse_wargear_prompt(text: str, items: list[str] | None = None) -> dict[str, object]:
    items = list(items or [])
    text = normalize_space(text)
    availability, text = parse_model_count_availability(text)
    if text.lower() in {"none", "none."}:
        return {
            "target": None,
            "actor": None,
            "action": None,
            "selectionMode": "manual",
            "choices": [],
            "allocationLimit": None,
            "pickCount": None,
            "requireDistinct": False,
            "poolKey": None,
            "poolLimit": None,
            "eligibilityText": None,
            "consumesPool": 1,
            "availability": availability,
        }
    text = re.sub(r"\s+replaced one of the following", " replaced with one of the following", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+can be replace with\s+", " can be replaced with ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+can replaced with\s+", " can be replaced with ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+replaced with equipped with\s+", " replaced with ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+replaced with with\s+", " replaced with ", text, flags=re.IGNORECASE)
    text = re.sub(r"(have their .+?) can be replaced with", r"\1 replaced with", text, flags=re.IGNORECASE)
    result = {
        "target": None,
        "actor": None,
        "action": None,
        "selectionMode": "manual",
        "choices": [],
        "allocationLimit": None,
        "pickCount": None,
        "requireDistinct": False,
        "poolKey": None,
        "poolLimit": None,
        "eligibilityText": None,
        "consumesPool": 1,
        "availability": availability,
    }

    hybrid_multi_match = re.match(
        rf"^(.*?)(?: can be replaced with| can replace (?:its|their))\s+({NUMBER_PATTERN}\s+.+?), or two different (?:weapons|options) from the following list(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if hybrid_multi_match:
        target = normalize_space(hybrid_multi_match.group(1))
        fixed_choice = normalize_inline_choice(hybrid_multi_match.group(2))
        fixed_choice["pickCost"] = 2
        result.update(
            {
                "target": target,
                "action": "replace",
                "selectionMode": "multi",
                "choices": [fixed_choice, *[normalize_wargear_choice(item) for item in items if normalize_space(item)]],
                "pickCount": 2,
                "requireDistinct": True,
            }
        )
        return result

    multi_match = re.match(
        r"^(.*?)(?: can be replaced with| can replace (?:its|their)| can be equipped with) two different (?:weapons|options) from the following list(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if multi_match:
        target = normalize_space(multi_match.group(1))
        lowered = text.lower()
        action = "replace" if "replaced with" in lowered or "can replace " in lowered else "equip"
        result.update(
            {
                "target": target,
                "action": action,
                "selectionMode": "multi",
                "choices": [normalize_wargear_choice(item) for item in items if normalize_space(item)],
                "pickCount": 2,
                "requireDistinct": True,
            }
        )
        return result

    capped_multi_match = re.match(
        rf"^(.*?) can be equipped with up to ({NUMBER_PATTERN}) of the following(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if capped_multi_match:
        pick_count = parse_number_token(capped_multi_match.group(2))
        result.update(
            {
                "target": normalize_space(capped_multi_match.group(1)),
                "action": "equip",
                "selectionMode": "multi",
                "choices": [normalize_wargear_choice(item) for item in items if normalize_space(item)],
                "pickCount": pick_count,
                "requireDistinct": False,
            }
        )
        return result

    wrapper_choice_match = re.match(
        r"^(.*?) can do one of the following(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if wrapper_choice_match and items:
        result.update(
            {
                "target": singularize_actor(wrapper_choice_match.group(1)),
                "action": None,
                "selectionMode": "single",
                "choices": [normalize_wrapper_choice(item) for item in items if normalize_space(item)],
            }
        )
        return result

    capped_inline_equip_match = re.match(
        rf"^(?:This model|It) can be equipped with up to ({NUMBER_PATTERN}) (.+?)(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if capped_inline_equip_match:
        max_count = parse_number_token(capped_inline_equip_match.group(1))
        choice_label = singularize_actor(capped_inline_equip_match.group(2))
        result.update(
            {
                "target": "this model",
                "actor": "this model",
                "action": "equip",
                "selectionMode": "allocation",
                "choices": [normalize_inline_choice(f"1 {choice_label}")],
                "allocationLimit": {"kind": "static", "max": max_count},
            }
        )
        return result

    any_of_multi_match = re.match(
        r"^(?:This model|It) can be equipped with any of the following(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if any_of_multi_match and items:
        choices = [normalize_wargear_choice(item) for item in items if normalize_space(item)]
        result.update(
            {
                "target": "this model",
                "actor": "this model",
                "action": "equip",
                "selectionMode": "multi",
                "choices": choices,
                "pickCount": len(choices),
                "requireDistinct": True,
            }
        )
        return result

    capped_allocation_items_match = re.match(
        rf"^Any number of (models|.+?) can (?:each )?be equipped with up to ({NUMBER_PATTERN}) of the following, (?:but cannot take duplicates|and can take duplicates)(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if capped_allocation_items_match and items:
        max_count = parse_number_token(capped_allocation_items_match.group(2))
        result.update(
            {
                "target": normalize_space(capped_allocation_items_match.group(1)),
                "actor": normalize_space(f"Any number of {capped_allocation_items_match.group(1)}"),
                "action": "equip",
                "selectionMode": "allocation",
                "choices": [normalize_wargear_choice(item) for item in items if normalize_space(item)],
                "allocationLimit": {"kind": "modelCount", "multiplier": max_count},
            }
        )
        return result

    capped_allocation_inline_match = re.match(
        rf"^Any number of (models|.+?) can (?:each )?be equipped with up to ({NUMBER_PATTERN}) (.+?)(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if capped_allocation_inline_match:
        max_count = parse_number_token(capped_allocation_inline_match.group(2))
        choice_label = singularize_actor(capped_allocation_inline_match.group(3))
        result.update(
            {
                "target": normalize_space(capped_allocation_inline_match.group(1)),
                "actor": normalize_space(f"Any number of {capped_allocation_inline_match.group(1)}"),
                "action": "equip",
                "selectionMode": "allocation",
                "choices": [normalize_inline_choice(f"1 {choice_label}")],
                "allocationLimit": {"kind": "modelCount", "multiplier": max_count},
            }
        )
        return result

    fixed_equip_match = re.match(
        r"^(.*?) can be equipped with (.+?)(?: \(.*?\))?(?:\*|:|\.)*$",
        text,
        flags=re.IGNORECASE,
    )
    if fixed_equip_match:
        actor = normalize_space(fixed_equip_match.group(1))
        choice_label = normalize_space(fixed_equip_match.group(2))
        if " equipped with " not in actor.lower():
            actor_key = normalize_label_key(actor)
            target = "unit" if actor_key in {"it", "this unit", "the unit", "unit"} else actor
            result.update(
                {
                    "target": target,
                    "actor": "unit" if target == "unit" else actor,
                    "action": "equip",
                    "selectionMode": "allocation",
                    "choices": [normalize_wargear_choice(choice_label)],
                    "allocationLimit": {"kind": "static", "max": 1},
                }
            )
            return result

    # Each pattern is (regex, action, target_builder, choices_builder, selection_mode_builder, actor_builder, allocation_limit_builder)
    patterns = [
        # --- ALLOCATION PATTERNS (Priority) ---
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), (?:up to )?({NUMBER_PATTERN}) (.+?)(?: can each have|'s) their (.+?) replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(4)),
            lambda _match: [], # Uses items list
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), (?:up to )?({NUMBER_PATTERN}) (.+?) can each have their (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(4)),
            lambda match: [normalize_inline_choice(match.group(5))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), (?:up to )?({NUMBER_PATTERN}) models?[’'] (.+?) can each be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: f"{parse_number_token(match.group(2))} models",
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), (?:up to )?({NUMBER_PATTERN}) (.+?)(?: equipped with a .+?)? can (?:each )?be equipped with (?:one )?(.+?)(?: \(.*?\))?(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), (?:up to )?({NUMBER_PATTERN}) (.+?)[’']s (.+?) can be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(4)),
            lambda match: [normalize_inline_choice(match.group(5))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), ({NUMBER_PATTERN}) model[’']s (.+?) can be replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: f"{parse_number_token(match.group(2))} model",
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), ({NUMBER_PATTERN}) models?[’'] (.+?) can each be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: f"{parse_number_token(match.group(2))} models",
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), it can have ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "equip",
            lambda _match: "unit",
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "allocation",
            lambda _match: "unit",
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": 1},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), ({NUMBER_PATTERN}) model can be equipped with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "equip",
            lambda match: f"{parse_number_token(match.group(2))} model",
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: f"{parse_number_token(match.group(2))} model",
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), ({NUMBER_PATTERN}) (.+?) can have its (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(4)),
            lambda match: [normalize_inline_choice(match.group(5))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit), ({NUMBER_PATTERN}) (.+?) can be equipped with (?:one )?(.+?)(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "ratio", "perModels": parse_number_token(match.group(1)), "maxPerStep": parse_number_token(match.group(2))},
        ),
        (
            r"^Any number of (models|.+?) can (?:each )?have their (.+? and .+?) replaced with (.+? and .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            r"^Any number of (.+?)[’'] (.+?) can each be replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            rf"^Any number of (.+?)[’'] (.+?) can each be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            r"^Any number of (models|.+?) can (?:each )?have their (.+?) replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            rf"^Any number of (models|.+?) can (?:each )?have their (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            r"^Any number of (models|.+?) can (?:each )?replace their (.+?) with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: None,
        ),
        (
            rf"^Any number of (models|.+?) can (?:each )?replace their (.+?) with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: None,
        ),
        (
            r"^Any number of models?[’'] (.+?) can each be replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda _match: "Any number of models",
            lambda _match: None,
        ),
        (
            rf"^Any number of models?[’'] (.+?) can each be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "allocation",
            lambda _match: "Any number of models",
            lambda _match: None,
        ),
        (
            rf"^Any number of this model[’']s (.+?) can each be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "allocation",
            lambda _match: "this model",
            lambda _match: None,
        ),
        (
            r"^Any number of (models|.+?) can each replace one of their (.+?) with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: None,
        ),
        (
            rf"^Any number of (models|.+?) can each replace one of their (.+?) with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: None,
        ),
        (
            r"^Any number of (models|.+?) can (?:each )?be equipped with one of the following(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            rf"^Any number of (models|.+?) can (?:each )?be equipped with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "allocation",
            lambda match: normalize_space(f"Any number of {match.group(1)}"),
            lambda _match: {"kind": "modelCount"},
        ),
        (
            rf"^({NUMBER_PATTERN}) models? can (?:each )?have their (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda _match: "models",
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?have their (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?have their (.+?) replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?be equipped with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?be equipped with one of the following(?:\*|:|\.)*$",
            "equip",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?replace their (.+?) with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            rf"^Up to ({NUMBER_PATTERN}) (models|.+?) can (?:each )?replace their (.+?) with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(1))},
        ),
        (
            r"^Each model can have each (.+?) it is equipped with replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "allocation",
            lambda _match: "Each model",
            lambda _match: None,
        ),
        (
            r"^(?:This model|It) can (?:each )?be equipped with one of the following(?:\*|:|\.)*$",
            "equip",
            lambda _match: "model",
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            rf"^(?:This model|It) can (?:each )?be equipped with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "equip",
            lambda _match: "model",
            lambda match: [normalize_inline_choice(match.group(1))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            rf"^(?:{NUMBER_PATTERN}\s+)?(.+?)[’']s (.+?) can be replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
        (
            rf"^(?:{NUMBER_PATTERN}\s+)?(.+?)[’']s (.+?) can be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
        (
            rf"^(?:{NUMBER_PATTERN}\s+)?(.+?) equipped with (?:an? |one )(.+?) can be equipped(?: with)? ((?:{NUMBER_PATTERN}) .+?)(?: \(.*?\))?(?:\*|:|\.)*$",
            "equip",
            lambda match: singularize_actor(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
        (
            r"^(?:\d+ |One )?(.+?) not equipped with (.+?) can replace its (.+?) with (.+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(3)),
            lambda match: [normalize_inline_choice(match.group(4))],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
        (
            r"^(?:This model|It)[’']s (.+?) can be replaced with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(?:This model|It)[’']s (.+?) can be replaced with on of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            rf"^(?:This model|It)[’']s (.+?) replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            rf"^(?:This model|It)[’']s (.+?) can be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            rf"^If this unit contains ({NUMBER_PATTERN}) models, (?:one model|it) can be equipped with (?:one )?(.+?)(?:\*|:|\.)*$",
            "equip",
            lambda match: "unit",
            lambda match: [normalize_inline_choice(match.group(2))],
            lambda _match: "allocation",
            lambda match: "unit",
            lambda match: {"kind": "static", "max": 1},
        ),
        (
            rf"^If this unit contains ({NUMBER_PATTERN}) models, one model[’']s (.+?) can be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: "model",
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(2)),
            lambda match: {"kind": "static", "max": 1},
        ),
        (
            rf"^If this unit contains only ({NUMBER_PATTERN}) models, ({NUMBER_PATTERN}) (.+?)[’']s (.+?) can be replaced with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(4)),
            lambda match: [normalize_inline_choice(match.group(5))],
            lambda _match: "allocation",
            lambda match: normalize_space(match.group(3)),
            lambda match: {"kind": "static", "max": parse_number_token(match.group(2))},
        ),
        (
            r"^(.*?) can replace its (.+?) with one of the following(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
        (
            rf"^(.*?) can replace its (.+?) with ((?:{NUMBER_PATTERN}) .+?)(?:\*|:|\.)*$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda match: [normalize_inline_choice(match.group(3))],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),

        # --- SINGLE SELECTION PATTERNS (Fallbacks) ---
        (
            r"^(.*?) can be replaced with one of the following:?$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can be equipped with one of the following:?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) must be equipped with one of the following:?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can have its .* replaced with one of the following:?$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(All .*?) can each be equipped with one of the following:?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can be replaced with (?:either )?(\d+ .+?)\.?$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_wargear_choice(match.group(2))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?)[’']s (.+?) can be replaced with (?:either )?(\d+ .+?)\.?$",
            "replace",
            lambda match: normalize_space(f"{match.group(1)}'s {match.group(2)}"),
            lambda match: [normalize_wargear_choice(match.group(3))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can be equipped with (\d+ .+?)\.?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_wargear_choice(match.group(2))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(All .*?) can each have their (.+?) replaced with (\d+ .+?)\.?$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_wargear_choice(match.group(3))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(All .*?) can each be equipped with (\d+ .+?)\.?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda match: [normalize_wargear_choice(match.group(2))],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can be replaced with:?$",
            "replace",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can be equipped with:?$",
            "equip",
            lambda match: normalize_space(match.group(1)),
            lambda _match: [],
            lambda _match: "single",
            lambda _match: None,
            lambda _match: None,
        ),
        (
            r"^(.*?) can replace their (.+?) with one of the following:?$",
            "replace",
            lambda match: normalize_space(match.group(2)),
            lambda _match: [],
            lambda _match: "single",
            lambda match: singularize_actor(match.group(1)),
            lambda _match: None,
        ),
    ]

    for pattern, action, target_builder, choices_builder, selection_mode_builder, actor_builder, limit_builder in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            result["target"] = target_builder(match)
            result["actor"] = actor_builder(match)
            result["action"] = action
            result["selectionMode"] = selection_mode_builder(match)
            result["choices"] = choices_builder(match)
            result["allocationLimit"] = limit_builder(match)
            if "equipped with" in text.lower():
                equipped_with_match = re.search(
                    r"equipped with (?:an? |one )(.+?)(?: \(.*?\))?(?: can|,|\.|$)",
                    text,
                    flags=re.IGNORECASE,
                )
                if equipped_with_match:
                    result["eligibilityText"] = f"equipped with {normalize_space(equipped_with_match.group(1))}"
            actor_key = singularize_actor(result["actor"]).lower() if result["actor"] else ""
            pool_limit = result["allocationLimit"] if result["selectionMode"] == "allocation" else "modelCount"
            if actor_key in {"unit", "model", "this model"}:
                pool_limit = None
            result["poolLimit"] = pool_limit
            result["poolKey"] = infer_pool_key(result["actor"], result["target"], result["eligibilityText"])
            return result

    return result


def build_wargear(card: dict[str, object]) -> dict[str, object]:
    abilities = [
        normalize_entry(entry)
        for entry in section_entries(card, "WARGEAR ABILITIES")
    ]
    option_entries = section_entries(card, "WARGEAR OPTIONS")
    options = []
    manual_notes = []
    has_manual_options = False

    def append_option(label: str, parsed: dict[str, object], raw_items: list[str]) -> None:
        nonlocal has_manual_options
        item_choices = [normalize_wargear_choice(item) for item in raw_items if normalize_space(item)]
        choices = []
        for choice in [*(parsed["choices"] or []), *item_choices]:
            if not choice or not choice.get("id"):
                continue
            if any(existing["id"] == choice["id"] for existing in choices):
                continue
            choices.append(dict(choice))
        if normalize_space(label).lower().rstrip(".") == "none" and not choices:
            return
        option_id = slugify(f"{label}-{len(options) + 1}")
        option = {
            "id": option_id,
            "label": label,
            "target": parsed["target"],
            "actor": parsed["actor"],
            "action": parsed["action"],
            "selectionMode": parsed["selectionMode"],
            "choices": choices,
            "allocationLimit": parsed["allocationLimit"],
        }
        if parsed["pickCount"] is not None:
            option["pickCount"] = parsed["pickCount"]
        if parsed["requireDistinct"]:
            option["requireDistinct"] = True
        if parsed["availability"] is not None:
            option["availability"] = parsed["availability"]
        if parsed["poolKey"]:
            option["poolKey"] = parsed["poolKey"]
        if parsed["poolLimit"] is not None or parsed["poolKey"]:
            option["poolLimit"] = parsed["poolLimit"]
        if parsed["eligibilityText"]:
            option["eligibilityText"] = parsed["eligibilityText"]
        if parsed["consumesPool"] != 1:
            option["consumesPool"] = parsed["consumesPool"]
        if parsed["selectionMode"] == "manual":
            has_manual_options = True
        options.append(option)

    for entry in option_entries:
        entry_type = entry.get("type")
        if entry_type == "option_group":
            label = normalize_space(entry.get("label"))
            parsed = parse_wargear_prompt(label, list(entry.get("items", [])))
            appended_nested = False
            if parsed["selectionMode"] == "manual" and entry.get("items"):
                if parsed.get("availability"):
                    nested = [parse_wargear_prompt(str(item), []) for item in entry.get("items", [])]
                    nested = [item for item in nested if item["selectionMode"] != "manual" and item["choices"]]
                    if nested:
                        first = nested[0]
                        same_signature = all(
                            item["action"] == first["action"]
                            and item["target"] == first["target"]
                            and item["actor"] == first["actor"]
                            and item["selectionMode"] == first["selectionMode"]
                            and item["allocationLimit"] == first["allocationLimit"]
                            and item["pickCount"] == first["pickCount"]
                            and bool(item["requireDistinct"]) == bool(first["requireDistinct"])
                            and item["poolKey"] == first["poolKey"]
                            and item["poolLimit"] == first["poolLimit"]
                            and item["eligibilityText"] == first["eligibilityText"]
                            and item["consumesPool"] == first["consumesPool"]
                            and (item.get("availability") is None or item.get("availability") == parsed["availability"])
                            for item in nested
                        )
                        if same_signature:
                            parsed = {
                                **first,
                                "choices": [choice for item in nested for choice in item["choices"]],
                                "availability": parsed["availability"],
                            }
                        else:
                            for item, raw_label in zip(nested, entry.get("items", []), strict=False):
                                nested_parsed = {
                                    **item,
                                    "availability": parsed["availability"],
                                }
                                append_option(normalize_space(str(raw_label)), nested_parsed, [])
                            appended_nested = True
                wrapper_match = re.match(
                    rf"^For every ({NUMBER_PATTERN}) models? in (?:this unit|the unit):$",
                    label,
                    flags=re.IGNORECASE,
                )
                if wrapper_match:
                    nested = [parse_wargear_prompt(str(item), []) for item in entry.get("items", [])]
                    nested = [item for item in nested if item["selectionMode"] != "manual" and item["choices"]]
                    if nested:
                        first = nested[0]
                        same_signature = all(
                            item["action"] == first["action"]
                            and item["target"] == first["target"]
                            for item in nested
                        )
                        if same_signature:
                            parsed = {
                                **first,
                                "selectionMode": "allocation",
                                "choices": [choice for item in nested for choice in item["choices"]],
                                "allocationLimit": {
                                    "kind": "ratio",
                                    "perModels": parse_number_token(wrapper_match.group(1)),
                                    "maxPerStep": 1,
                                },
                            }
            if appended_nested:
                continue
            append_option(label, parsed, list(entry.get("items", [])))
            continue

        text = normalize_space(entry.get("text"))
        if text:
            manual_notes.append(text)

    if manual_notes:
        # Notes don't necessarily mean the unit needs manual intervention,
        # but they are worth flagging if we want to be sure everything is parsed.
        # For now, we only flag if an ACTUAL OPTION failed to parse.
        pass

    return {
        "abilities": abilities,
        "options": options,
        "manualNotes": manual_notes,
        "hasManualOptions": has_manual_options,
    }


def unit_id_from_card(card: dict[str, object]) -> str:
    source = card.get("source", {})
    datasheet_slug = source.get("datasheet_slug")
    if datasheet_slug:
        return str(datasheet_slug).lower()
    name = str(card.get("name", ""))
    return slugify(name)


def validate_render_section_coverage(
    card: dict[str, object],
    normalized: dict[str, object],
) -> list[str]:
    issues: list[str] = []
    source_sections = [
        str(section.get("title", "")).strip()
        for section in card.get("sections", [])
        if str(section.get("title", "")).strip()
    ]
    render_sections = [
        str(section.get("title", "")).strip()
        for section in normalized.get("renderSections", [])
        if str(section.get("title", "")).strip()
    ]
    if source_sections != render_sections:
        issues.append("render section order does not match exported sections")

    composition_entries = list(card.get("unit_composition", []))
    has_composition_lines = any(
        entry.get("type") in {"list", "statement", "text"} for entry in composition_entries
    )
    if has_composition_lines and not normalized.get("composition", {}).get("rawLines"):
        issues.append("unit composition lost non-points content")

    if list(card.get("keywords", [])) and not list(normalized.get("keywords", [])):
        issues.append("keywords lost during builder normalization")
    if list(card.get("faction_keywords", [])) and not list(normalized.get("factionKeywords", [])):
        issues.append("faction keywords lost during builder normalization")

    return issues


def normalize_card(faction_slug: str, card: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    characteristics = card.get("characteristics", {})
    abilities = card.get("abilities", {})
    composition = build_composition(card.get("unit_composition", []))
    wargear = build_wargear(card)
    source = card.get("source", {})

    normalized = {
        "unitId": unit_id_from_card(card),
        "name": card.get("name"),
        "factionSlug": faction_slug,
        "source": {
            "url": source.get("url"),
            "normalizedUrl": source.get("normalizedUrl"),
            "canonicalSourceId": source.get("canonicalSourceId"),
            "sourceFactionSlug": source.get("faction_slug"),
            "datasheetSlug": source.get("datasheet_slug"),
            "outputSlug": source.get("output_slug") or faction_slug,
            "fetchedAt": source.get("fetchedAt"),
            "contentHash": source.get("contentHash"),
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
        "wargear": wargear,
        "selectionMode": composition["selectionMode"],
        "quality": {
            "missingStats": [],
            "hasMissingStats": False,
            "hasManualSelectionLabels": composition["selectionMode"] == "manual",
            "hasManualWargearOptions": wargear["hasManualOptions"],
        },
        "keywords": list(card.get("keywords", [])),
        "factionKeywords": list(card.get("faction_keywords", [])),
        "renderSections": [
            normalize_render_block(section)
            for section in card.get("sections", [])
        ],
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
    normalized["support"] = support_metadata_from_unit(normalized)
    render_issues = validate_render_section_coverage(card, normalized)

    diagnostics = {
        "unitId": normalized["unitId"],
        "name": normalized["name"],
        "missingStats": list(normalized["quality"]["missingStats"]),
        "manualSelection": normalized["selectionMode"] == "manual",
        "manualWargear": wargear["hasManualOptions"],
        "renderIssues": render_issues,
    }
    return normalized, diagnostics


def load_faction_rules(
    faction_slug: str,
    faction_rules_root: Path | None,
) -> tuple[dict[str, object], list[str]]:
    rules_root = Path(faction_rules_root) if faction_rules_root else default_faction_rules_root()
    rules_path = rules_root / f"{faction_slug}.json"
    warnings: list[str] = []
    if not rules_path.exists():
        warnings.append(f"Faction rules export missing for {faction_slug}: {rules_path}")
        return empty_rules(), warnings

    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != FACTION_RULES_SCHEMA_VERSION:
        warnings.append(
            f"Faction rules schema mismatch for {faction_slug}: expected {FACTION_RULES_SCHEMA_VERSION}, got {payload.get('schemaVersion')}"
        )
        return empty_rules(), warnings

    rules = payload.get("rules")
    if not isinstance(rules, dict):
        warnings.append(f"Faction rules payload has unexpected shape for {faction_slug}: {rules_path}")
        return empty_rules(), warnings

    army_rules = rules.get("armyRules")
    detachments = rules.get("detachments")
    return {
        "armyRules": army_rules if isinstance(army_rules, list) else [],
        "detachments": detachments if isinstance(detachments, list) else [],
    }, warnings


def build_faction_catalog(
    faction_slug: str,
    cards: list[dict[str, object]],
    output_path: Path,
    *,
    faction_rules_root: Path | None = None,
) -> dict[str, object]:
    units: list[dict[str, object]] = []
    missing_stats: list[dict[str, object]] = []
    manual_units: list[dict[str, object]] = []
    manual_wargear_units: list[dict[str, object]] = []
    render_issue_units: list[dict[str, object]] = []
    support_summary = {
        "readyUnitCount": 0,
        "partialUnitCount": 0,
        "incompatibleUnitCount": 0,
        "configuredOnlyPreviewCount": 0,
        "sourceImagePreviewCount": 0,
    }
    rules, rules_warnings = load_faction_rules(faction_slug, faction_rules_root)

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
        if diagnostics["manualWargear"]:
            manual_wargear_units.append(
                {
                    "unitId": diagnostics["unitId"],
                    "name": diagnostics["name"],
                }
            )
        if diagnostics["renderIssues"]:
            render_issue_units.append(
                {
                    "unitId": diagnostics["unitId"],
                    "name": diagnostics["name"],
                    "issues": diagnostics["renderIssues"],
                }
            )

        support = unit.get("support", {}) if isinstance(unit, dict) else {}
        support_level = str(support.get("supportLevel") or "full")
        preview_support = str(support.get("previewSupport") or "configured-only")
        if support_level == "partial":
            support_summary["partialUnitCount"] += 1
        elif support_level == "incompatible":
            support_summary["incompatibleUnitCount"] += 1
        else:
            support_summary["readyUnitCount"] += 1

        if preview_support == "source-image":
            support_summary["sourceImagePreviewCount"] += 1
        else:
            support_summary["configuredOnlyPreviewCount"] += 1

    units.sort(key=lambda unit: str(unit.get("name", "")))
    source_parent_slug = parent_faction_slug(cards, faction_slug)
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
            "manualWargearUnits": manual_wargear_units,
            "renderIssueUnits": render_issue_units,
            "rulesWarnings": rules_warnings,
            "supportSummary": support_summary,
        },
        "rules": rules,
        "units": units,
    }
    if source_parent_slug:
        catalog["faction"]["parentSlug"] = source_parent_slug
        catalog["faction"]["parentName"] = slug_to_title(source_parent_slug)
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
        f"- Units with manual wargear: {manifest['report']['totals']['manualWargearCount']}",
        f"- Units with render issues: {manifest['report']['totals']['renderIssueCount']}",
        f"- Factions with rules warnings: {manifest['report']['totals']['rulesWarningFactionCount']}",
        f"- Ready units: {manifest['report']['totals']['readyUnitCount']}",
        f"- Partial-support units: {manifest['report']['totals']['partialUnitCount']}",
        f"- Configured-only preview units: {manifest['report']['totals']['configuredOnlyPreviewCount']}",
        f"- Source cards copied: {manifest['report']['totals']['sourceCardCopiedCount']}",
        f"- Source cards missing: {manifest['report']['totals']['sourceCardMissingCount']}",
        "",
        "## Factions",
        "",
    ]

    for faction in manifest["factions"]:
        parent_name = faction.get("parentName")
        lines.extend(
            [
                f"### {faction['name']}",
                "",
                f"- Catalog: `{faction['catalogFile']}`",
                *( [f"- Subset of: {parent_name}"] if parent_name else [] ),
                f"- Units: {faction['unitCount']}",
                f"- Missing stats: {faction['missingStatsCount']}",
                f"- Manual selection units: {faction['manualSelectionCount']}",
                f"- Manual wargear units: {faction['manualWargearCount']}",
                f"- Render issue units: {faction['renderIssueCount']}",
                f"- Rules warnings: {faction['rulesWarningCount']}",
                f"- Ready units: {faction['supportSummary']['readyUnitCount']}",
                f"- Partial-support units: {faction['supportSummary']['partialUnitCount']}",
                f"- Configured-only preview units: {faction['supportSummary']['configuredOnlyPreviewCount']}",
                f"- Source cards copied: {faction['sourceCardCopiedCount']}",
                f"- Source cards missing: {faction['sourceCardMissingCount']}",
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


def collect_source_card_report(
    source_cards_root: Path,
    catalogs: list[dict[str, object]],
) -> dict[str, object]:
    copied_count = 0
    missing_count = 0
    faction_reports: dict[str, dict[str, object]] = {}

    for catalog in catalogs:
        faction_slug = str(catalog["faction"]["slug"])
        copied_units = 0
        missing_units: list[dict[str, str]] = []

        for unit in catalog.get("units", []):
            source = unit.get("source", {}) if isinstance(unit, dict) else {}
            output_slug = str(source.get("outputSlug") or faction_slug)
            datasheet_slug = str(source.get("datasheetSlug") or "").strip()
            if not datasheet_slug:
                missing_count += 1
                missing_units.append(
                    {
                        "name": str(unit.get("name", unit.get("unitId", "Unknown unit"))),
                        "reason": "missing-datasheet-slug",
                        "outputSlug": output_slug,
                        "datasheetSlug": datasheet_slug,
                    }
                )
                continue

            candidate_path = source_cards_root / output_slug / f"{datasheet_slug}.png"
            if not candidate_path.exists():
                missing_count += 1
                missing_units.append(
                    {
                        "name": str(unit.get("name", datasheet_slug)),
                        "reason": f"missing-file:{candidate_path}",
                        "outputSlug": output_slug,
                        "datasheetSlug": datasheet_slug,
                    }
                )
                continue

            copied_count += 1
            copied_units += 1

        faction_reports[faction_slug] = {
            "copiedCount": copied_units,
            "missingCount": len(missing_units),
            "missingUnits": missing_units,
        }

    return {
        "copiedCount": copied_count,
        "missingCount": missing_count,
        "factions": faction_reports,
    }


def publish_source_cards(docs_data_root: Path, source_cards_root: Path) -> None:
    catalogs_dir = docs_data_root / "catalogs"
    if not catalogs_dir.exists():
        return

    destination_root = docs_data_root / "source-cards"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    for catalog_path in sorted(catalogs_dir.glob("*.json")):
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        faction_slug = str(catalog["faction"]["slug"])
        destination_dir = destination_root / faction_slug
        destination_dir.mkdir(parents=True, exist_ok=True)

        for unit in catalog.get("units", []):
            source = unit.get("source", {}) if isinstance(unit, dict) else {}
            output_slug = str(source.get("outputSlug") or faction_slug)
            datasheet_slug = str(source.get("datasheetSlug") or "").strip()
            if not datasheet_slug:
                continue
            candidate_path = source_cards_root / output_slug / f"{datasheet_slug}.png"
            if not candidate_path.exists():
                continue
            shutil.copy2(candidate_path, destination_dir / candidate_path.name)


def build_all(
    source_root: Path,
    output_root: Path,
    factions: list[str] | None = None,
    clean: bool = False,
    source_cards_root: Path | None = None,
    faction_rules_root: Path | None = None,
) -> dict[str, object]:
    source_root = Path(source_root)
    output_root = Path(output_root)
    source_cards_root = Path(source_cards_root) if source_cards_root else default_source_cards_root()
    faction_rules_root = Path(faction_rules_root) if faction_rules_root else default_faction_rules_root()
    if not source_root.exists():
        raise FileNotFoundError(f"Source root not found: {source_root}")

    if clean and output_root.exists():
        shutil.rmtree(output_root)

    catalog_dir = output_root / "catalogs"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    available_factions = sorted(path.name for path in source_root.iterdir() if path.is_dir())
    target_factions = factions or available_factions
    record_lookup = validate_export_contract(source_root, target_factions)

    manifest_factions = []
    report_factions = []
    built_catalogs = []
    total_units = 0
    total_missing_stats = 0
    total_manual_selection = 0
    total_manual_wargear = 0
    total_render_issues = 0
    rules_warning_faction_count = 0
    total_ready_units = 0
    total_partial_units = 0
    total_incompatible_units = 0
    total_configured_only_preview = 0
    total_source_image_preview = 0

    for faction_slug in target_factions:
        index_path = source_root / faction_slug / "index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"Faction index not found: {index_path}")
        cards = json.loads(index_path.read_text(encoding="utf-8"))
        for card in cards:
            validate_card_export_metadata(card, faction_slug, record_lookup, index_path)
        output_catalog_path = catalog_dir / f"{faction_slug}.json"
        catalog = build_faction_catalog(
            faction_slug,
            cards,
            output_catalog_path,
            faction_rules_root=faction_rules_root,
        )
        built_catalogs.append(catalog)
        build_info = catalog["build"]
        rules_warning_count = len(build_info.get("rulesWarnings", []))
        if rules_warning_count:
            rules_warning_faction_count += 1

        manifest_factions.append(
            {
                "slug": faction_slug,
                "name": catalog["faction"]["name"],
                "unitCount": catalog["faction"]["unitCount"],
                "catalogFile": f"catalogs/{faction_slug}.json",
                "missingStatsCount": len(build_info["missingStats"]),
                "manualSelectionCount": len(build_info["manualSelectionUnits"]),
                "manualWargearCount": len(build_info["manualWargearUnits"]),
                "renderIssueCount": len(build_info["renderIssueUnits"]),
                "rulesWarningCount": rules_warning_count,
                **(
                    {
                        "parentSlug": catalog["faction"].get("parentSlug"),
                        "parentName": catalog["faction"].get("parentName"),
                    }
                    if catalog["faction"].get("parentSlug")
                    else {}
                ),
            }
        )
        report_factions.append(
            {
                "slug": faction_slug,
                "name": catalog["faction"]["name"],
                "unitCount": catalog["faction"]["unitCount"],
                "missingStats": build_info["missingStats"],
                "manualSelectionUnits": build_info["manualSelectionUnits"],
                "manualWargearUnits": build_info["manualWargearUnits"],
                "renderIssueUnits": build_info["renderIssueUnits"],
                "rulesWarnings": build_info.get("rulesWarnings", []),
            }
        )
        total_units += catalog["faction"]["unitCount"]
        total_missing_stats += len(build_info["missingStats"])
        total_manual_selection += len(build_info["manualSelectionUnits"])
        total_manual_wargear += len(build_info["manualWargearUnits"])
        total_render_issues += len(build_info["renderIssueUnits"])

    source_card_report = collect_source_card_report(source_cards_root, built_catalogs)

    for catalog in built_catalogs:
        faction_slug = str(catalog["faction"]["slug"])
        missing_source_keys = {
            f"{str(item.get('outputSlug') or faction_slug)}::{str(item.get('datasheetSlug') or '').strip()}"
            for item in source_card_report["factions"].get(faction_slug, {}).get("missingUnits", [])
            if str(item.get("datasheetSlug") or "").strip()
        }
        ready_count = 0
        partial_count = 0
        incompatible_count = 0
        configured_only_count = 0
        source_image_count = 0

        for unit in catalog.get("units", []):
            support = dict(unit.get("support", {})) if isinstance(unit, dict) else {}
            support_reasons = unique_strings(list(support.get("supportReasons", [])))
            source = unit.get("source", {}) if isinstance(unit, dict) else {}
            source_key = f"{str(source.get('outputSlug') or faction_slug)}::{str(source.get('datasheetSlug') or '').strip()}"
            has_source_image = bool(str(source.get("datasheetSlug") or "").strip()) and source_key not in missing_source_keys
            if has_source_image:
                support["previewSupport"] = "source-image"
                source_image_count += 1
            else:
                support["previewSupport"] = "configured-only"
                configured_only_count += 1
                support_reasons.append("source_image_missing")

            support_level = str(support.get("supportLevel") or "full")
            if support_level == "full" and support_reasons:
                support_level = "partial"
            support["supportLevel"] = support_level
            support["supportReasons"] = unique_strings(support_reasons)
            unit["support"] = support

            if support_level == "partial":
                partial_count += 1
            elif support_level == "incompatible":
                incompatible_count += 1
            else:
                ready_count += 1

        catalog["build"]["supportSummary"] = {
            "readyUnitCount": ready_count,
            "partialUnitCount": partial_count,
            "incompatibleUnitCount": incompatible_count,
            "configuredOnlyPreviewCount": configured_only_count,
            "sourceImagePreviewCount": source_image_count,
        }

        catalog_path = catalog_dir / f"{faction_slug}.json"
        catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    for faction in manifest_factions:
        source_info = source_card_report["factions"].get(faction["slug"], {})
        faction["sourceCardCopiedCount"] = source_info.get("copiedCount", 0)
        faction["sourceCardMissingCount"] = source_info.get("missingCount", 0)
        catalog = next((item for item in built_catalogs if item["faction"]["slug"] == faction["slug"]), None)
        support_summary = catalog.get("build", {}).get("supportSummary", {}) if catalog else {}
        faction["supportSummary"] = support_summary
        total_ready_units += int(support_summary.get("readyUnitCount", 0) or 0)
        total_partial_units += int(support_summary.get("partialUnitCount", 0) or 0)
        total_incompatible_units += int(support_summary.get("incompatibleUnitCount", 0) or 0)
        total_configured_only_preview += int(support_summary.get("configuredOnlyPreviewCount", 0) or 0)
        total_source_image_preview += int(support_summary.get("sourceImagePreviewCount", 0) or 0)

    for faction in report_factions:
        source_info = source_card_report["factions"].get(faction["slug"], {})
        faction["sourceCardCopiedCount"] = source_info.get("copiedCount", 0)
        faction["sourceCardMissingCount"] = source_info.get("missingCount", 0)
        faction["missingSourceCards"] = source_info.get("missingUnits", [])
        catalog = next((item for item in built_catalogs if item["faction"]["slug"] == faction["slug"]), None)
        faction["supportSummary"] = catalog.get("build", {}).get("supportSummary", {}) if catalog else {}

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "sourceRoot": str(source_root.resolve()),
        "sourceCardsRoot": str(source_cards_root.resolve()),
        "catalogRoot": "catalogs",
        "sourceCardsRootRelative": "source-cards",
        "reportFile": "reports/build-report.json",
        "factions": manifest_factions,
        "report": {
            "totals": {
                "factionCount": len(manifest_factions),
                "unitCount": total_units,
                "missingStatsCount": total_missing_stats,
                "manualSelectionCount": total_manual_selection,
                "manualWargearCount": total_manual_wargear,
                "renderIssueCount": total_render_issues,
                "rulesWarningFactionCount": rules_warning_faction_count,
                "sourceCardCopiedCount": source_card_report["copiedCount"],
                "sourceCardMissingCount": source_card_report["missingCount"],
                "readyUnitCount": total_ready_units,
                "partialUnitCount": total_partial_units,
                "incompatibleUnitCount": total_incompatible_units,
                "configuredOnlyPreviewCount": total_configured_only_preview,
                "sourceImagePreviewCount": total_source_image_preview,
            },
            "factions": report_factions,
        },
    }

    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_report(output_root, manifest)
    if total_render_issues:
        first_issue = next(
            (
                unit
                for faction in report_factions
                for unit in faction.get("renderIssueUnits", [])
            ),
            None,
        )
        detail = ""
        if first_issue:
            detail = f" First issue: {first_issue['name']} ({'; '.join(first_issue['issues'])})."
        raise ValueError(
            f"Builder render completeness validation failed for {total_render_issues} units.{detail}"
        )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build roster-oriented builder catalogs from exported faction JSON bundles."
    )
    parser.add_argument("--source-root", default=str(default_source_root()))
    parser.add_argument("--output-root", default=str(default_output_root()))
    parser.add_argument("--docs-data-root", default=str(default_docs_data_root()))
    parser.add_argument("--source-cards-root", default=str(default_source_cards_root()))
    parser.add_argument("--faction-rules-root", default=str(default_faction_rules_root()))
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
        source_cards_root=Path(args.source_cards_root),
        faction_rules_root=Path(args.faction_rules_root),
    )
    publish_docs_data(Path(args.output_root), Path(args.docs_data_root))
    publish_source_cards(Path(args.docs_data_root), Path(args.source_cards_root))
    totals = manifest["report"]["totals"]
    print(
        f"Built {totals['unitCount']} units across {totals['factionCount']} factions into {args.output_root}"
    )


if __name__ == "__main__":
    main()
