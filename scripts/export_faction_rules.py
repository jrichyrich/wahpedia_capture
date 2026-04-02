import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
RULES_SCHEMA_VERSION = 1
RULES_PARSER_VERSION = "2026-03-30-army-rules-v1"
STOP_SECTION_TITLES = {"Crusade Rules", "Boarding Actions"}
GENERIC_SECTION_TITLES = {
    "Introduction",
    "Army Rules",
    "Detachment Rule",
    "Enhancements",
    "Stratagems",
    "Restrictions",
}
PHASE_ORDER = ("command", "movement", "shooting", "charge", "fight", "any", "opponent")
KEYWORD_LABELS = {"WHEN", "TARGET", "EFFECT", "RESTRICTIONS", "CP"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_space(value).lower()).strip("-") or "item"


def unique_slug(base: str, seen: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in seen:
        candidate = f"{base}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Wahapedia faction-level rules into structured JSON.")
    parser.add_argument("--output-slug", action="append", default=[], help="Faction output slug to export.")
    parser.add_argument("--out-dir", default="out/faction_rules", help="Directory where faction rules JSON files will be written.")
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay between requests.")
    parser.add_argument("--workers", type=int, default=1, help="Reserved for future use; current exporter fetches serially.")
    return parser.parse_args()


def load_reference_datasheet_urls(output_slug: str) -> list[str]:
    manifest_path = ROOT / "out" / "source" / f"{output_slug}-links.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            urls = [normalize_space(item.get("href")) for item in data if normalize_space(item.get("href"))]
            if urls:
                return urls

    bundle_path = ROOT / "out" / "json" / output_slug / "index.json"
    if not bundle_path.exists():
        raise FileNotFoundError(f"Could not resolve source URLs for output slug: {output_slug}")

    cards = json.loads(bundle_path.read_text(encoding="utf-8"))
    urls = [
        normalize_space(card.get("source", {}).get("url"))
        for card in cards
        if normalize_space(card.get("source", {}).get("url"))
    ]
    if not urls:
        raise ValueError(f"No source URLs found for output slug: {output_slug}")
    return urls


def infer_url_candidates(output_slug: str, reference_urls: list[str]) -> list[str]:
    parsed = urlparse(reference_urls[0])
    scheme = "http" if parsed.netloc.endswith("wahapedia.ru") else parsed.scheme
    parts = [part for part in parsed.path.split("/") if part]
    if "factions" not in parts:
        raise ValueError(f"Could not infer faction URL from {reference_urls[0]}")

    factions_index = parts.index("factions")
    base_parts = parts[:factions_index + 2]
    parent_slug = parts[factions_index + 1]
    base_url = f"{scheme}://{parsed.netloc}/{'/'.join(base_parts)}"
    direct_url = f"{scheme}://{parsed.netloc}/{'/'.join(parts[:factions_index + 1] + [output_slug])}"
    nested_url = f"{base_url}/{output_slug}"

    ordered = []
    if output_slug != parent_slug:
        ordered.extend([nested_url, direct_url, base_url])
    else:
        ordered.extend([base_url, direct_url])

    deduped = []
    seen = set()
    for candidate in ordered:
        normalized = candidate.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(candidate)
    return deduped


def fetch_html(url: str) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            response.raise_for_status()
            return response.url, response.text
        except requests.RequestException as error:
            last_error = error
            if attempt == 3:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def fetch_faction_page(output_slug: str) -> tuple[str, str]:
    reference_urls = load_reference_datasheet_urls(output_slug)
    last_error: Exception | None = None
    for candidate in infer_url_candidates(output_slug, reference_urls):
        try:
            resolved_url, html = fetch_html(candidate)
            soup = BeautifulSoup(html, "html.parser")
            if soup.find("h2", string=lambda value: normalize_space(value) == "Introduction"):
                return resolved_url, html
        except Exception as error:  # pragma: no cover - network failures are integration concerns
            last_error = error
            continue
    if last_error:
        raise last_error
    raise RuntimeError(f"Unable to resolve faction page for {output_slug}")


def fragment_for(nodes: list[Tag]) -> Tag:
    html = "".join(str(node) for node in nodes if isinstance(node, Tag))
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser")
    return soup.div


def heading_text(tag: Tag | None) -> str:
    return normalize_space(tag.get_text(" ", strip=True)) if isinstance(tag, Tag) else ""


def top_level_sections_from_intro(soup: BeautifulSoup) -> list[tuple[str, list[Tag]]]:
    intro = soup.find("h2", string=lambda value: normalize_space(value) == "Introduction")
    if not intro:
        return []

    sections: list[tuple[str, list[Tag]]] = []
    current_title: str | None = None
    current_nodes: list[Tag] = []

    for sibling in intro.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name == "h2":
            title = normalize_space(sibling.get_text(" ", strip=True))
            if title in STOP_SECTION_TITLES:
                break
            if current_title is not None:
                sections.append((current_title, current_nodes))
            current_title = title
            current_nodes = []
            continue
        if current_title is None:
            continue
        current_nodes.append(sibling)

    if current_title is not None:
        sections.append((current_title, current_nodes))
    return sections


def minimal_text_from_tag(tag: Tag) -> str:
    return normalize_space(tag.get_text(" ", strip=True))


def text_between(start: Tag, stop_heading_predicate) -> str:
    parts: list[str] = []
    for element in start.next_elements:
        if element is start:
            continue
        if isinstance(element, Tag) and stop_heading_predicate(element):
            break
        if isinstance(element, NavigableString):
            text = normalize_space(element)
            if text:
                parts.append(text)
    return normalize_space(" ".join(parts))


def section_blocks_by_h3(fragment: Tag, *, source_url: str) -> list[dict[str, str]]:
    return section_rule_blocks(fragment, source_url=source_url)


def section_rule_blocks(
    fragment: Tag,
    *,
    source_url: str,
    start_after: Tag | None = None,
    stop_before: Tag | None = None,
) -> list[dict[str, str]]:
    blocks = []
    seen_ids: set[str] = set()
    started = start_after is None
    for heading in fragment.find_all(["h2", "h3", "h4"]):
        if heading is start_after:
            started = True
            continue
        if heading is stop_before:
            break
        if not started or heading.name not in {"h3", "h4"}:
            continue
        title = normalize_space(heading.get_text(" ", strip=True))
        if not title or title == "KEYWORDS" or "D6" in title or title in GENERIC_SECTION_TITLES:
            continue
        if title in {"Space Marine Chapters", "Deathwatch"}:
            continue
        body = text_between(
            heading,
            lambda tag: tag.name in {"h3", "h4"} and tag is not heading,
        )
        if not body:
            continue
        blocks.append(
            {
                "id": unique_slug(slugify(title), seen_ids),
                "name": title,
                "body": body,
                "sourceUrl": source_url,
            }
        )
    return blocks


def section_fragment_between(fragment: Tag, heading_text: str, stop_titles: set[str]) -> Tag | None:
    heading = fragment.find(
        lambda tag: isinstance(tag, Tag) and tag.name in {"h2", "h3", "h4"} and normalize_space(tag.get_text(" ", strip=True)) == heading_text
    )
    if not heading:
        return None

    nodes: list[str] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h2", "h3", "h4"}:
            title = normalize_space(sibling.get_text(" ", strip=True))
            if title in stop_titles:
                break
        if isinstance(sibling, Tag):
            nodes.append(str(sibling))
    if not nodes:
        return None
    soup = BeautifulSoup(f"<div>{''.join(nodes)}</div>", "html.parser")
    return soup.div


def extract_keyword_hints(text: str) -> list[str]:
    hints: list[str] = []
    seen = set()
    for match in re.finditer(r"\b[A-Z][A-Z0-9'-]*(?:\s+[A-Z][A-Z0-9'-]*)*\b", text or ""):
        value = normalize_space(match.group(0))
        if not value or value in KEYWORD_LABELS or len(value) < 3:
            continue
        if value not in seen:
            seen.add(value)
            hints.append(value)
    return hints


def phase_tags_from_when(text: str) -> list[str]:
    lowered = normalize_space(text).lower()
    tags: list[str] = []
    if "any phase" in lowered:
        tags.append("any")
    for phase in ("command", "movement", "shooting", "charge", "fight"):
        if phase in lowered:
            tags.append(phase)
    if "opponent" in lowered:
        tags.append("opponent")
    if not tags:
        tags.append("any")
    ordered = []
    seen = set()
    for phase in PHASE_ORDER:
        if phase in tags and phase not in seen:
            seen.add(phase)
            ordered.append(phase)
    return ordered


def parse_enhancements(section_fragment: Tag | None) -> list[dict[str, object]]:
    if not section_fragment:
        return []
    enhancements: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for table in section_fragment.find_all("table"):
        full_text = normalize_space(table.get_text(" ", strip=True))
        if not full_text:
            continue
        match = re.match(r"^(?P<name>.+?)\s+(?P<points>\d+)\s*pts\b(?P<body>.*)$", full_text)
        if not match:
            continue
        name = normalize_space(match.group("name"))
        body = normalize_space(match.group("body"))
        eligibility_match = re.search(r"([^.]*model only\.)", body, flags=re.IGNORECASE)
        enhancements.append(
            {
                "id": unique_slug(slugify(name), seen_ids),
                "name": name,
                "points": int(match.group("points")),
                "body": body,
                "eligibilityText": normalize_space(eligibility_match.group(1)) if eligibility_match else "",
                "keywordHints": extract_keyword_hints(eligibility_match.group(1) if eligibility_match else body),
            }
        )
    return enhancements


def minimal_matching_descendants(root: Tag, predicate) -> list[Tag]:
    matches = []
    for tag in root.find_all(["div", "table"], recursive=True):
        if not predicate(tag):
            continue
        if any(predicate(descendant) for descendant in tag.find_all(["div", "table"], recursive=True)):
            continue
        matches.append(tag)
    return matches


def parse_labeled_text(full_text: str, label: str, next_labels: list[str]) -> str:
    pattern = rf"{label}:\s*(.*?)(?=(?:{'|'.join(next_labels)}):|$)"
    match = re.search(pattern, full_text, flags=re.IGNORECASE)
    return normalize_space(match.group(1)) if match else ""


def is_cp_line(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\s*CP", normalize_space(value), flags=re.IGNORECASE))


def looks_like_stratagem_name(value: str) -> bool:
    text = normalize_space(value)
    if not text or is_cp_line(text):
        return False
    if text in GENERIC_SECTION_TITLES or text.rstrip(":").upper() in KEYWORD_LABELS:
        return False
    if "Stratagem" in text:
        return False
    return True


def previous_named_sibling(tag: Tag) -> str:
    for sibling in tag.previous_siblings:
        if not isinstance(sibling, Tag):
            continue
        if "str10Name" in sibling.get("class", []):
            text = minimal_text_from_tag(sibling)
            if looks_like_stratagem_name(text):
                return text
        text = minimal_text_from_tag(sibling)
        if looks_like_stratagem_name(text):
            return text
    return ""


def resolve_stratagem_name(section_fragment: Tag, block: Tag, lines: list[str]) -> str:
    cp_index = next((index for index, line in enumerate(lines) if is_cp_line(line)), None)
    if cp_index is not None and cp_index > 0 and looks_like_stratagem_name(lines[cp_index - 1]):
        return normalize_space(lines[cp_index - 1])
    if lines and looks_like_stratagem_name(lines[0]):
        return normalize_space(lines[0])

    current: Tag | None = block
    while isinstance(current, Tag):
        sibling_name = previous_named_sibling(current)
        if sibling_name:
            return sibling_name
        if current is section_fragment:
            break
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None

    return normalize_space(lines[0]) if lines else ""


def parse_stratagems(section_fragment: Tag | None) -> list[dict[str, object]]:
    if not section_fragment:
        return []
    stratagems: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    candidates = minimal_matching_descendants(
        section_fragment,
        lambda tag: all(token in minimal_text_from_tag(tag) for token in ("WHEN:", "TARGET:", "EFFECT:")) and re.search(r"\b\d+CP\b", minimal_text_from_tag(tag)),
    )

    for block in candidates:
        lines = [normalize_space(line) for line in block.get_text("\n", strip=True).splitlines() if normalize_space(line)]
        if len(lines) < 4:
            continue
        name = resolve_stratagem_name(section_fragment, block, lines)
        cp_line = next((line for line in lines if re.fullmatch(r"\d+CP", line, flags=re.IGNORECASE)), "")
        kind_line = next((line for line in lines if "Stratagem" in line), "")
        if not cp_line or not kind_line:
            continue
        full_text = normalize_space(" ".join(lines))
        when = parse_labeled_text(full_text, "WHEN", ["TARGET", "EFFECT", "RESTRICTIONS"])
        target = parse_labeled_text(full_text, "TARGET", ["EFFECT", "RESTRICTIONS"])
        effect = parse_labeled_text(full_text, "EFFECT", ["RESTRICTIONS"])
        restrictions = parse_labeled_text(full_text, "RESTRICTIONS", [])
        if restrictions:
            effect = normalize_space(f"{effect} RESTRICTIONS: {restrictions}")
        kind_match = re.search(r"–\s*(.+?)\s+Stratagem", kind_line)
        stratagem = {
            "id": unique_slug(slugify(name), seen_ids),
            "name": name,
            "cp": int(cp_line.replace("CP", "").strip()),
            "kind": normalize_space(kind_match.group(1)) if kind_match else "unknown",
            "when": when,
            "target": target,
            "effect": effect,
            "phaseTags": phase_tags_from_when(when),
            "keywordHints": extract_keyword_hints(target),
        }
        stratagems.append(stratagem)
    return stratagems


def parse_restrictions(section_fragment: Tag | None) -> list[str]:
    if not section_fragment:
        return []
    list_items = [normalize_space(item.get_text(" ", strip=True)) for item in section_fragment.find_all("li")]
    values = [item for item in list_items if item]
    if values:
        return values
    paragraphs = [normalize_space(item.get_text(" ", strip=True)) for item in section_fragment.find_all(["p", "div"], recursive=False)]
    return [item for item in paragraphs if item]


def supplemental_fragment(fragment: Tag, source_url: str) -> Tag:
    supplement_heading = find_supplement_heading(fragment, source_url)
    if not supplement_heading:
        return fragment

    nodes = []
    for sibling in supplement_heading.next_siblings:
        if isinstance(sibling, Tag):
            nodes.append(sibling)
    return fragment_for(nodes) or fragment


def find_supplement_heading(fragment: Tag, source_url: str) -> Tag | None:
    parsed = urlparse(source_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if "factions" not in path_parts:
        return None
    factions_index = path_parts.index("factions")
    faction_parts = path_parts[factions_index + 1:]
    if len(faction_parts) < 2:
        return None

    output_slug = faction_parts[-1]
    expected_name = normalize_space(output_slug.replace("-", " ").title())
    return fragment.find(
        lambda tag: isinstance(tag, Tag)
        and tag.name == "h2"
        and expected_name in normalize_space(tag.get_text(" ", strip=True))
        and "Supplement" in normalize_space(tag.get_text(" ", strip=True))
    )


def find_detachment_headings(fragment: Tag) -> list[Tag]:
    headings: list[Tag] = []
    for heading in fragment.find_all("h2"):
        title = heading_text(heading)
        if not title or title in STOP_SECTION_TITLES or title in GENERIC_SECTION_TITLES:
            continue
        next_heading = heading.find_next(lambda tag: isinstance(tag, Tag) and tag.name in {"h2", "h3", "h4"} and tag is not heading)
        if heading_text(next_heading) == "Detachment Rule":
            headings.append(heading)
    return headings


def find_detachment_headings_after(start_heading: Tag) -> list[Tag]:
    headings: list[Tag] = []
    for heading in start_heading.find_all_next("h2"):
        title = heading_text(heading)
        if not title:
            continue
        if title in STOP_SECTION_TITLES or title == "Boarding Actions":
            break
        if title in GENERIC_SECTION_TITLES or "Supplement" in title:
            continue
        next_heading = heading.find_next(lambda tag: isinstance(tag, Tag) and tag.name in {"h2", "h3", "h4"} and tag is not heading)
        if heading_text(next_heading) == "Detachment Rule":
            headings.append(heading)
    return headings


def fragment_before_heading(fragment: Tag, stop_heading: Tag | None) -> Tag:
    if not stop_heading:
        return fragment
    nodes = []
    for child in fragment.children:
        if child is stop_heading:
            break
        if isinstance(child, Tag):
            nodes.append(child)
    return fragment_for(nodes) or fragment


def fragment_after_heading_until(start_heading: Tag, stop_heading: Tag | None) -> Tag:
    nodes = []
    for sibling in start_heading.next_siblings:
        if sibling is stop_heading:
            break
        if isinstance(sibling, Tag):
            nodes.append(sibling)
    return fragment_for(nodes) or fragment_for([])


def detachment_nodes_between(start_heading: Tag, next_heading: Tag | None) -> list[Tag]:
    nodes = []
    for sibling in start_heading.next_siblings:
        if sibling is next_heading:
            break
        if isinstance(sibling, Tag):
            if sibling.name == "h2" and heading_text(sibling) in STOP_SECTION_TITLES.union({"Boarding Actions"}):
                break
            nodes.append(sibling)
    return nodes


def heading_precedes(first: Tag, second: Tag) -> bool:
    return bool(second.find_previous(lambda tag: tag is first))


def parse_detachment_section(title: str, nodes: list[Tag]) -> dict[str, object] | None:
    fragment = fragment_for(nodes)
    if not fragment:
        return None
    fragment_text = normalize_space(fragment.get_text(" ", strip=True))
    if not fragment_text or "Detachment Rule" not in fragment_text or "Stratagems" not in fragment_text:
        return None

    detachment_rule_heading = fragment.find(
        lambda tag: isinstance(tag, Tag) and tag.name in {"h2", "h3"} and normalize_space(tag.get_text(" ", strip=True)) == "Detachment Rule"
    )
    rule_name_heading = None
    if detachment_rule_heading:
        rule_name_heading = detachment_rule_heading.find_next(
            lambda tag: isinstance(tag, Tag) and tag.name in {"h3", "h4"} and tag is not detachment_rule_heading
        )

    summary = []
    for node in nodes:
        if node.name in {"div", "p"} and "Columns2" not in node.get("class", []) and normalize_space(node.get_text(" ", strip=True)):
            summary.append(normalize_space(node.get_text(" ", strip=True)))
    summary_text = normalize_space(" ".join(summary))
    if rule_name_heading and summary_text.startswith(normalize_space(rule_name_heading.get_text(" ", strip=True))):
        summary_text = ""

    stop_titles = {"Enhancements", "Stratagems", "Restrictions"}
    rule_name = normalize_space(rule_name_heading.get_text(" ", strip=True)) if rule_name_heading else ""
    rule_body = text_between(
        rule_name_heading,
        lambda tag: tag.name in {"h2", "h3"} and normalize_space(tag.get_text(" ", strip=True)) in stop_titles,
    ) if rule_name_heading else ""

    enhancements_fragment = section_fragment_between(fragment, "Enhancements", {"Stratagems", "Restrictions"})
    restrictions_fragment = section_fragment_between(fragment, "Restrictions", {"Enhancements", "Stratagems"})
    stratagems_fragment = section_fragment_between(fragment, "Stratagems", set())

    return {
        "name": title,
        "summary": summary_text,
        "rule": {
            "name": rule_name or "Detachment Rule",
            "body": rule_body,
        },
        "restrictionsText": parse_restrictions(restrictions_fragment),
        "enhancements": parse_enhancements(enhancements_fragment),
        "stratagems": parse_stratagems(stratagems_fragment),
    }


def parse_faction_page_html(html: str, *, source_url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    sections = top_level_sections_from_intro(soup)
    rules = {"armyRules": [], "detachments": []}
    seen_army_ids: set[str] = set()
    seen_detachment_ids: set[str] = set()

    army_rules_section = next((nodes for title, nodes in sections if title == "Army Rules"), None)
    if not army_rules_section:
        return rules

    army_fragment = fragment_for(army_rules_section)
    supplement_heading = find_supplement_heading(army_fragment, source_url)
    if supplement_heading:
        detachment_headings = find_detachment_headings_after(supplement_heading)
        explicit_army_rules_heading = supplement_heading.find_next(
            lambda tag: isinstance(tag, Tag)
            and tag.name in {"h2", "h3"}
            and heading_text(tag) == "Army Rules"
        )
        army_rules = section_rule_blocks(
            army_fragment,
            source_url=source_url,
            start_after=explicit_army_rules_heading,
            stop_before=detachment_headings[0] if detachment_headings else None,
        ) if explicit_army_rules_heading else []
    else:
        army_fragment = supplemental_fragment(army_fragment, source_url)
        supplement_boundary = army_fragment.find(
            lambda tag: isinstance(tag, Tag)
            and tag.name == "h2"
            and "Supplement" in heading_text(tag)
        )
        detachment_headings = find_detachment_headings(army_fragment)
        if supplement_boundary:
            detachment_headings = [
                heading for heading in detachment_headings
                if heading_precedes(heading, supplement_boundary)
            ]
        army_rules = section_rule_blocks(
            army_fragment,
            source_url=source_url,
            stop_before=detachment_headings[0] if detachment_headings else None,
        )
    for rule in army_rules:
        rule["id"] = unique_slug(rule["id"], seen_army_ids)
        rules["armyRules"].append(rule)

    for index, heading in enumerate(detachment_headings):
        next_heading = detachment_headings[index + 1] if index + 1 < len(detachment_headings) else None
        detachment = parse_detachment_section(heading_text(heading), detachment_nodes_between(heading, next_heading))
        if not detachment:
            continue
        detachment["id"] = unique_slug(slugify(detachment["name"]), seen_detachment_ids)
        rules["detachments"].append(detachment)

    for title, nodes in sections:
        if title == "Army Rules" or title in GENERIC_SECTION_TITLES or title in STOP_SECTION_TITLES:
            continue
        if any(existing["name"] == title for existing in rules["detachments"]):
            continue
        detachment = parse_detachment_section(title, nodes)
        if not detachment:
            continue
        detachment["id"] = unique_slug(slugify(detachment["name"]), seen_detachment_ids)
        rules["detachments"].append(detachment)

    return rules


def export_output_slug(output_slug: str, out_dir: Path, delay: float = 0.0) -> Path:
    resolved_url, html = fetch_faction_page(output_slug)
    payload = {
        "schemaVersion": RULES_SCHEMA_VERSION,
        "parserVersion": RULES_PARSER_VERSION,
        "generatedAt": utc_now(),
        "outputSlug": output_slug,
        "sourceUrl": resolved_url,
        "rules": parse_faction_page_html(html, source_url=resolved_url),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / f"{output_slug}.json"
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if delay > 0:
        time.sleep(delay)
    return destination


def main() -> None:
    args = parse_args()
    if not args.output_slug:
        raise SystemExit("Provide at least one --output-slug.")

    out_dir = Path(args.out_dir)
    for output_slug in args.output_slug:
        destination = export_output_slug(output_slug, out_dir=out_dir, delay=max(0.0, args.delay))
        print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
