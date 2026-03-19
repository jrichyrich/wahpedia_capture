import hashlib
import json
from urllib.parse import urlsplit, urlunsplit


EXPORT_SCHEMA_VERSION = 1
PARSER_VERSION = "2026-03-19-durable-normalization-v1"


def normalize_source_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    scheme = "http" if parts.scheme in {"http", "https"} else (parts.scheme or "http")
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def canonical_source_id(url: str) -> str:
    normalized = normalize_source_url(url)
    if not normalized:
        return ""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return f"wahapedia:{digest}"


def text_content_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def stable_json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def exported_section_titles(payload: dict[str, object]) -> list[str]:
    titles = []
    for section in payload.get("sections", []):
        title = str(section.get("title", "")).strip()
        if title:
            titles.append(title)
    return titles


def missing_expected_sections(raw_titles: list[str], exported_titles: list[str]) -> list[str]:
    exported = set(exported_titles)
    return [title for title in raw_titles if title not in exported]


def default_quality(
    raw_titles: list[str],
    exported_titles_list: list[str],
    warnings: list[str] | None = None,
) -> dict[str, object]:
    warning_list = list(warnings or [])
    missing = missing_expected_sections(raw_titles, exported_titles_list)
    for title in missing:
        warning_list.append(f"section-missing:{title}")
    return {
        "rawSectionTitles": raw_titles,
        "exportedSectionTitles": exported_titles_list,
        "missingExpectedSections": missing,
        "warnings": warning_list,
    }


def shared_core_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "name": payload.get("name"),
        "base_size": payload.get("base_size"),
        "characteristics": payload.get("characteristics"),
        "weapons": payload.get("weapons"),
        "abilities": payload.get("abilities"),
        "sections": payload.get("sections"),
        "unit_composition": payload.get("unit_composition"),
        "keywords": payload.get("keywords"),
        "faction_keywords": payload.get("faction_keywords"),
    }


def shared_core_hash(payload: dict[str, object]) -> str:
    return stable_json_hash(shared_core_payload(payload))


def export_manifest_record(payload: dict[str, object]) -> dict[str, object]:
    source = payload.get("source", {}) if isinstance(payload, dict) else {}
    quality = payload.get("quality", {}) if isinstance(payload, dict) else {}
    return {
        "outputSlug": source.get("output_slug"),
        "datasheetSlug": source.get("datasheet_slug"),
        "canonicalSourceId": source.get("canonicalSourceId"),
        "normalizedSourceUrl": source.get("normalizedUrl"),
        "exportSchemaVersion": payload.get("exportSchemaVersion"),
        "parserVersion": payload.get("parserVersion"),
        "sourceContentHash": source.get("contentHash"),
        "sharedCoreHash": shared_core_hash(payload),
        "exportedSectionTitles": quality.get("exportedSectionTitles", []),
        "quality": quality,
    }
