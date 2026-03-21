import argparse
import concurrent.futures
import copy
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from datasheet_schema import (
        EXPORT_SCHEMA_VERSION,
        PARSER_VERSION,
        canonical_source_id,
        default_quality,
        export_manifest_record,
        exported_section_titles,
        normalize_source_url,
        stable_json_hash,
        text_content_hash,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from datasheet_schema import (
        EXPORT_SCHEMA_VERSION,
        PARSER_VERSION,
        canonical_source_id,
        default_quality,
        export_manifest_record,
        exported_section_titles,
        normalize_source_url,
        stable_json_hash,
        text_content_hash,
    )


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def normalize_wahapedia_url(url: str) -> str:
    return normalize_source_url(url)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Wahapedia datasheets into structured JSON."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--url",
        help="Single datasheet URL to export.",
    )
    group.add_argument(
        "--output-slug",
        help="Existing capture slug to read from out/source/<slug>-links.json.",
    )
    parser.add_argument(
        "--card-slug",
        action="append",
        default=[],
        help="Limit export to one or more card slugs. Repeat as needed.",
    )
    parser.add_argument(
        "--manifest-path",
        help="Optional explicit manifest path. Defaults to out/source/<output-slug>-links.json.",
    )
    parser.add_argument(
        "--out-dir",
        default="out/json",
        help="Directory where per-card JSON files and bundle index.json will be written.",
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
        help="Number of concurrent workers to use while fetching datasheets.",
    )
    parser.add_argument(
        "--rewrite-existing",
        action="store_true",
        help="Rewrite existing exported JSON under the current export schema/parser version without fetching remote HTML.",
    )
    parser.add_argument(
        "--sync-duplicates",
        action="store_true",
        help="Synchronize duplicate canonical-source exports so shared-core content matches across output slugs.",
    )
    return parser.parse_args()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slugify_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def slug_from_url(url: str) -> str:
    url = normalize_wahapedia_url(url)
    return url.rstrip("/").split("/")[-1]


def faction_from_url(url: str) -> str:
    url = normalize_wahapedia_url(url)
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "factions" not in parts:
        raise ValueError(f"Could not determine faction slug from URL: {url}")
    return parts[parts.index("factions") + 1]


def direct_children(element: Tag) -> list[Tag]:
    return [child for child in element.children if isinstance(child, Tag)]


def collect_column_sections(
    column: Tag,
    *,
    start_after_first_table: bool = False,
) -> list[tuple[str, list[Tag]]]:
    sections: list[tuple[str, list[Tag]]] = []
    current_title: str | None = None
    current_nodes: list[Tag] = []
    seen_table = not start_after_first_table

    def flush_current() -> None:
        nonlocal current_title, current_nodes
        if current_title is not None:
            sections.append((current_title, list(current_nodes)))
        current_nodes = []

    for child in direct_children(column):
        classes = child.get("class", [])
        if child.name == "table":
            if not seen_table:
                seen_table = True
                continue
            if current_title:
                current_nodes.append(child)
            continue
        if not seen_table:
            continue
        if "dsLineHor" in classes:
            continue
        if "dsHeader" in classes:
            flush_current()
            current_title = normalize_space(child.get_text(" ", strip=True))
            continue
        if current_title:
            current_nodes.append(child)

    flush_current()
    return sections


def split_title_and_base_size(value: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)(?:\s*\((.+)\))?$", normalize_space(value))
    if not match:
        return normalize_space(value), None
    return normalize_space(match.group(1)), normalize_space(match.group(2))


def fetch_html(url: str) -> tuple[str, str]:
    url = normalize_wahapedia_url(url)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            response.raise_for_status()
            return url, response.text
        except requests.RequestException as error:
            last_error = error
            if attempt == 3:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def fetch_soup(url: str) -> BeautifulSoup:
    _, html = fetch_html(url)
    return BeautifulSoup(html, "html.parser")


def find_datasheet_card(soup: BeautifulSoup) -> Tag:
    card = soup.select_one("div.dsOuterFrame.datasheet")
    if not card:
        raise ValueError("Datasheet markup not found")
    return card


def parse_characteristics(card: Tag) -> dict[str, str]:
    data = {}
    wrap = card.select_one("div.dsProfileBaseWrap")
    if not wrap:
        return data

    for item in wrap.select("div[class*='dsCharWrap']"):
        name = item.select_one("div.dsCharName")
        value = item.select_one("div.dsCharValue")
        if not name or not value:
            continue
        data[normalize_space(name.get_text())] = normalize_space(value.get_text())

    invul = card.select_one("div.dsInvulWrap div.dsCharInvulValue")
    if invul:
        data["Invulnerable Save"] = normalize_space(invul.get_text())

    return data


def extract_weapon_name(cell: Tag) -> str:
    wrapper = cell.find("span", recursive=False) or cell
    parts = []
    for child in wrapper.contents:
        if isinstance(child, NavigableString):
            text = normalize_space(str(child))
            if text:
                parts.append(text)
            continue

        if child.has_attr("data-tooltip-content") or child.select_one("[data-tooltip-content]"):
            break

        text = normalize_space(child.get_text(" ", strip=True))
        if text:
            parts.append(text)

    value = normalize_space(" ".join(parts))
    if value:
        return value
    return normalize_space(cell.get_text(" ", strip=True))


def extract_tooltip_texts(cell: Tag) -> list[str]:
    return unique(
        normalize_space(element.get_text(" ", strip=True))
        for element in cell.select("[data-tooltip-content]")
        if normalize_space(element.get_text(" ", strip=True))
    )


def parse_weapons(card: Tag) -> dict[str, list[dict[str, object]]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return {}

    children = direct_children(columns_wrap)
    if not children:
        return {}

    left_column = children[0]
    table = left_column.select_one("table.wTable")
    if not table:
        return {}

    weapons: dict[str, list[dict[str, object]]] = {}
    current_section = None
    current_headers: list[str] = []

    for row in table.select("tr"):
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue

        header_label = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
        header_cells = cells[2:] if len(cells) > 2 else []
        if header_label and row.select_one("td .dsHeader"):
            current_section = normalize_space(header_label).lower().replace(" ", "_")
            current_headers = [
                slugify_key(cell.get_text(" ", strip=True)) for cell in header_cells
            ]
            weapons.setdefault(current_section, [])
            continue

        if not current_section or len(cells) < 2 + len(current_headers):
            continue

        values = [
            normalize_space(cell.get_text(" ", strip=True))
            for cell in cells[2 : 2 + len(current_headers)]
        ]
        if not any(values):
            continue

        name_cell = cells[1]
        weapon = {
            "name": extract_weapon_name(name_cell),
            "abilities": extract_tooltip_texts(name_cell),
        }
        for header, value in zip(current_headers, values):
            weapon[header] = value

        weapons[current_section].append(weapon)

    return weapons


def split_block_on_dividers(block: Tag) -> list[Tag]:
    fragments = []
    current = []

    for child in block.contents:
        if isinstance(child, Tag) and "dsLineHor" in child.get("class", []):
            if current:
                fragments.append(BeautifulSoup("".join(str(node) for node in current), "html.parser"))
                current = []
            continue
        current.append(child)

    if current:
        fragments.append(BeautifulSoup("".join(str(node) for node in current), "html.parser"))

    return fragments


def parse_points_block(block: Tag) -> dict[str, object]:
    rows = []
    for row in block.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        rows.append(
            {
                "label": normalize_space(cells[0].get_text(" ", strip=True)),
                "points": normalize_space(cells[1].get_text(" ", strip=True)),
            }
        )
    return {"type": "points", "rows": rows}


def parse_option_group_item(item: Tag) -> dict[str, object] | None:
    prompt_parts = []
    for child in item.contents:
        if isinstance(child, Tag) and child.name == "ul":
            continue
        prompt_parts.append(str(child))

    prompt = normalize_space(
        BeautifulSoup("".join(prompt_parts), "html.parser").get_text(" ", strip=True)
    )
    nested = item.find("ul", recursive=False)
    choices = []
    if nested:
        choices = [
            normalize_space(option.get_text(" ", strip=True))
            for option in nested.find_all("li", recursive=False)
            if normalize_space(option.get_text(" ", strip=True))
        ]

    if not (prompt or choices) or (prompt == "None" and not choices):
        return None
    return {
        "type": "option_group",
        "label": prompt,
        "items": choices,
    }


def parse_option_group_entries(block: Tag) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    for child in block.contents:
        if not isinstance(child, Tag):
            continue
        if child.name == "ul":
            for item in child.find_all("li", recursive=False):
                option_group = parse_option_group_item(item)
                if option_group:
                    entries.append(option_group)
            continue

        if "dsOptionsComment" in child.get("class", []):
            text = normalize_space(child.get_text(" ", strip=True))
            if text:
                entries.append({"type": "text", "text": text})

    return entries


def parse_top_level_bold_segments(
    block: Tag, entry_type: str = "statement"
) -> list[dict[str, object]]:
    entries = []
    current_label = None
    current_parts: list[str] = []

    for child in block.contents:
        if isinstance(child, Tag) and child.name == "b":
            if current_label is not None:
                fragment = BeautifulSoup("".join(current_parts), "html.parser")
                text = normalize_space(fragment.get_text(" ", strip=True))
                if text:
                    item = {"type": entry_type, "text": text}
                    item["name" if entry_type == "rule" else "label"] = current_label
                    entries.append(item)
            current_label = normalize_space(child.get_text(" ", strip=True)).rstrip(":")
            current_parts = []
            continue

        if current_label is not None:
            current_parts.append(str(child))

    if current_label is not None:
        fragment = BeautifulSoup("".join(current_parts), "html.parser")
        text = normalize_space(fragment.get_text(" ", strip=True))
        if text:
            item = {"type": entry_type, "text": text}
            item["name" if entry_type == "rule" else "label"] = current_label
            entries.append(item)

    return entries


def parse_tagged_list_entry(fragment: Tag) -> dict[str, object] | None:
    prefix_parts: list[str] = []
    value_parts: list[str] = []
    first_bold: Tag | None = None

    for child in fragment.contents:
        if isinstance(child, NavigableString):
            text = normalize_space(str(child))
            if not text:
                continue
            if first_bold is None:
                prefix_parts.append(text)
            else:
                value_parts.append(text)
            continue

        if child.name == "b" and first_bold is None:
            first_bold = child
            continue

        text = normalize_space(child.get_text(" ", strip=True))
        if not text:
            continue
        if first_bold is None:
            prefix_parts.append(text)
        else:
            value_parts.append(text)

    label = normalize_space(" ".join(prefix_parts))
    if not first_bold or not label.endswith(":"):
        return None

    normalized_label = label[:-1].strip().upper()
    if normalized_label not in {"CORE", "FACTION"}:
        return None

    value = normalize_space(
        " ".join(
            part
            for part in [normalize_space(first_bold.get_text(" ", strip=True)), *value_parts]
            if part
        )
    )
    if not value:
        return None
    return {
        "type": "tagged_list",
        "label": normalized_label,
        "items": [value],
    }


def parse_inline_fragment(fragment: Tag, section_title: str) -> list[dict[str, object]]:
    target = fragment
    meaningful_children = []
    for child in fragment.contents:
        if isinstance(child, Tag):
            meaningful_children.append(child)
        elif normalize_space(str(child)):
            meaningful_children.append(child)
    if len(meaningful_children) == 1 and isinstance(meaningful_children[0], Tag):
        target = meaningful_children[0]

    text = normalize_space(target.get_text(" ", strip=True))
    if not text:
        return []

    tagged_entry = parse_tagged_list_entry(target)
    if tagged_entry:
        return [tagged_entry]

    entry_type = "rule" if section_title == "ABILITIES" else "statement"
    labeled_entries = parse_top_level_bold_segments(target, entry_type=entry_type)
    if labeled_entries:
        return labeled_entries
    return [{"type": "text", "text": text}]


def has_structural_children(node: Tag) -> bool:
    for child in node.contents:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class", [])
        if child.name == "ul":
            return True
        if child.name == "table" and child.select_one(".PriceTag"):
            return True
        if "dsLineHor" in classes or "dsOptionsComment" in classes:
            return True
    return False


def parse_ordered_entries(block: Tag, section_title: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    inline_parts: list[str] = []

    def flush_inline() -> None:
        nonlocal inline_parts
        if not inline_parts:
            return
        fragment = BeautifulSoup("".join(inline_parts), "html.parser")
        entries.extend(parse_inline_fragment(fragment, section_title))
        inline_parts = []

    for child in block.contents:
        if isinstance(child, NavigableString):
            if normalize_space(str(child)):
                inline_parts.append(str(child))
            continue

        classes = child.get("class", [])
        if child.name == "ul":
            flush_inline()
            if section_title == "WARGEAR OPTIONS":
                for item in child.find_all("li", recursive=False):
                    option_group = parse_option_group_item(item)
                    if option_group:
                        entries.append(option_group)
            else:
                items = [
                    normalize_space(item.get_text(" ", strip=True))
                    for item in child.find_all("li", recursive=False)
                    if normalize_space(item.get_text(" ", strip=True))
                ]
                if items:
                    entries.append({"type": "list", "items": items})
            continue

        if child.name == "table" and child.select_one(".PriceTag"):
            flush_inline()
            entries.append(parse_points_block(child))
            continue

        if "dsOptionsComment" in classes:
            flush_inline()
            text = normalize_space(child.get_text(" ", strip=True))
            if text:
                entries.append({"type": "text", "text": text})
            continue

        if "dsLineHor" in classes:
            flush_inline()
            continue

        if has_structural_children(child):
            flush_inline()
            entries.extend(parse_ordered_entries(child, section_title))
            continue

        if child.name in {"div", "p"}:
            flush_inline()
            entries.extend(parse_inline_fragment(child, section_title))
            continue

        inline_parts.append(str(child))

    flush_inline()
    return entries


def parse_section_block(section_title: str, block: Tag) -> list[dict[str, object]]:
    text = normalize_space(block.get_text(" ", strip=True))
    if not text:
        return []

    if section_title == "WARGEAR OPTIONS":
        option_entries = parse_option_group_entries(block)
        if option_entries:
            return option_entries

    ordered_entries = parse_ordered_entries(block, section_title)
    if ordered_entries:
        return ordered_entries
    return [{"type": "text", "text": text}]


def parse_left_column_sections(card: Tag) -> list[dict[str, object]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return []

    children = direct_children(columns_wrap)
    if not children:
        return []

    sections = []
    for title, nodes in collect_column_sections(children[0], start_after_first_table=True):
        block = BeautifulSoup("".join(str(node) for node in nodes), "html.parser")
        entries = parse_section_block(title, block)
        if entries:
            sections.append({"title": title, "entries": entries})
    return sections


def parse_right_column_sections(card: Tag) -> list[dict[str, object]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return []

    children = direct_children(columns_wrap)
    if len(children) < 2:
        return []

    sections = []
    for title, nodes in collect_column_sections(children[1]):
        block = BeautifulSoup("".join(str(node) for node in nodes), "html.parser")
        entries = parse_section_block(title, block)
        if entries:
            sections.append({"title": title, "entries": entries})
    return sections


def parse_sections(card: Tag) -> list[dict[str, object]]:
    return parse_left_column_sections(card) + parse_right_column_sections(card)


def section_has_meaningful_content(nodes: list[Tag]) -> bool:
    for node in nodes:
        if node.name == "table" and node.select_one(".PriceTag"):
            return True
        if node.select_one("ul"):
            return True
        if normalize_space(node.get_text(" ", strip=True)):
            return True
    return False


def section_titles_in_markup(card: Tag) -> list[str]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return []

    children = direct_children(columns_wrap)
    if not children:
        return []

    titles: list[str] = []
    for title, nodes in collect_column_sections(children[0], start_after_first_table=True):
        if section_has_meaningful_content(nodes):
            titles.append(title)
    if len(children) > 1:
        for title, nodes in collect_column_sections(children[1]):
            if section_has_meaningful_content(nodes):
                titles.append(title)
    return titles


def raw_right_column_section_nodes(card: Tag) -> dict[str, list[Tag]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return {}

    children = direct_children(columns_wrap)
    if len(children) < 2:
        return {}

    return {title: nodes for title, nodes in collect_column_sections(children[1])}


def keyword_column_count(card: Tag) -> int:
    keywords_wrap = card.select_one("div.ds2colKW")
    if not keywords_wrap:
        return 0
    return len(direct_children(keywords_wrap))


def section_has_non_points_markup(nodes: list[Tag]) -> bool:
    for node in nodes:
        if node.name == "table" and node.select_one(".PriceTag"):
            continue
        if node.select_one("ul") or node.select_one("b"):
            return True
        if normalize_space(node.get_text(" ", strip=True)):
            return True
    return False


def parse_keywords(card: Tag) -> dict[str, list[str]]:
    keywords_wrap = card.select_one("div.ds2colKW")
    if not keywords_wrap:
        return {"keywords": [], "faction_keywords": []}

    children = direct_children(keywords_wrap)
    if not children:
        return {"keywords": [], "faction_keywords": []}

    left_text = normalize_space(children[0].get_text(" ", strip=True))
    right_text = normalize_space(children[1].get_text(" ", strip=True)) if len(children) > 1 else ""

    def split_keywords(text: str, prefix: str) -> list[str]:
        value = normalize_space(text.replace(prefix, "", 1))
        return [normalize_space(item) for item in re.split(r"\s*,\s*", value) if normalize_space(item)]

    return {
        "keywords": split_keywords(left_text, "KEYWORDS:"),
        "faction_keywords": split_keywords(right_text, "FACTION KEYWORDS:"),
    }


def build_section_lookup(sections: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {slugify_key(str(section["title"])): section for section in sections}


def parse_datasheet_from_soup(
    url: str,
    soup: BeautifulSoup,
    fetched_at: str | None = None,
    source_content_hash: str | None = None,
) -> dict[str, object]:
    url = normalize_wahapedia_url(url)
    card = find_datasheet_card(soup)
    raw_title = normalize_space(card.select_one("div.dsH2Header").get_text(" ", strip=True))
    name, base_size = split_title_and_base_size(raw_title)
    sections = parse_sections(card)
    section_lookup = build_section_lookup(sections)
    raw_right_sections = raw_right_column_section_nodes(card)

    ability_entries = section_lookup.get("abilities", {}).get("entries", [])
    unit_composition_entries = section_lookup.get("unit_composition", {}).get("entries", [])
    keywords = parse_keywords(card)
    quality_warnings: list[str] = []

    if (
        section_has_non_points_markup(raw_right_sections.get("UNIT COMPOSITION", []))
        and not any(
            entry.get("type") in {"list", "statement", "text"}
            for entry in unit_composition_entries
        )
    ):
        quality_warnings.append("unit-composition-non-points-missing")

    if keyword_column_count(card) == 1 and not keywords["keywords"]:
        quality_warnings.append("keywords-single-column-missing")

    faction_slug = faction_from_url(url)
    datasheet_slug = slug_from_url(url)
    normalized_url = normalize_wahapedia_url(url)
    source = {
        "url": url,
        "normalizedUrl": normalized_url,
        "canonicalSourceId": canonical_source_id(normalized_url),
        "faction_slug": faction_slug,
        "datasheet_slug": datasheet_slug,
        "fetchedAt": fetched_at or utc_now(),
        "contentHash": source_content_hash or text_content_hash(str(card)),
    }

    payload = {
        "exportSchemaVersion": EXPORT_SCHEMA_VERSION,
        "parserVersion": PARSER_VERSION,
        "source": source,
        "name": name,
        "base_size": base_size,
        "characteristics": parse_characteristics(card),
        "weapons": parse_weapons(card),
        "abilities": {
            "core": [
                item
                for entry in ability_entries
                if entry.get("type") == "tagged_list" and entry.get("label") == "CORE"
                for item in entry.get("items", [])
            ],
            "faction": [
                item
                for entry in ability_entries
                if entry.get("type") == "tagged_list" and entry.get("label") == "FACTION"
                for item in entry.get("items", [])
            ],
            "datasheet": [
                entry for entry in ability_entries if entry.get("type") == "rule"
            ],
            "other": [
                entry
                for entry in ability_entries
                if entry.get("type") not in {"tagged_list", "rule"}
            ],
        },
        "unit_composition": unit_composition_entries,
        "keywords": keywords["keywords"],
        "faction_keywords": keywords["faction_keywords"],
        "sections": sections,
    }
    payload["quality"] = default_quality(
        raw_titles=section_titles_in_markup(card),
        exported_titles_list=exported_section_titles(payload),
        warnings=quality_warnings,
    )
    payload["quality"]["keywordColumnCount"] = keyword_column_count(card)

    return payload


def parse_datasheet(url: str) -> dict[str, object]:
    url, html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    return parse_datasheet_from_soup(
        url,
        soup,
        fetched_at=utc_now(),
        source_content_hash=text_content_hash(html),
    )


def load_manifest(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Manifest must be a JSON list: {path}")
    return data


def derive_manifest_items_from_bundle(path: Path) -> list[dict[str, str]]:
    cards = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cards, list):
        raise ValueError(f"Bundle must be a JSON list: {path}")
    items = []
    for card in cards:
        source = card.get("source", {}) if isinstance(card, dict) else {}
        url = normalize_wahapedia_url(str(source.get("url") or ""))
        if not url:
            continue
        items.append({"href": url, "name": str(card.get("name") or "")})
    if not items:
        raise ValueError(f"No source URLs found in bundle: {path}")
    return items


def manifest_items(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.url:
        return [{"href": args.url, "name": ""}]

    manifest_path = (
        Path(args.manifest_path)
        if args.manifest_path
        else Path("out") / "source" / f"{args.output_slug}-links.json"
    )
    if not manifest_path.exists() and args.output_slug:
        bundle_path = Path(args.out_dir) / args.output_slug / "index.json"
        if bundle_path.exists():
            return derive_manifest_items_from_bundle(bundle_path)
    return load_manifest(manifest_path)


def load_existing_faction_bundle(faction_dir: Path) -> list[dict[str, object]]:
    bundle = []
    for path in sorted(faction_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        bundle.append(json.loads(path.read_text(encoding="utf-8")))
    return bundle


def filtered_items(items: list[dict[str, str]], card_slugs: list[str]) -> list[dict[str, str]]:
    if not card_slugs:
        return items

    slug_filter = {slug.strip() for slug in card_slugs if slug.strip()}
    return [item for item in items if slug_from_url(item["href"]) in slug_filter]


def load_existing_export_payloads(out_root: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for faction_dir in sorted(path for path in out_root.iterdir() if path.is_dir()):
        for path in sorted(faction_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = payload.setdefault("source", {})
            source.setdefault("output_slug", faction_dir.name)
            payloads.append(payload)
    return payloads


def load_existing_export_payload_paths(
    out_root: Path,
) -> list[tuple[Path, dict[str, object]]]:
    payloads: list[tuple[Path, dict[str, object]]] = []
    for faction_dir in sorted(path for path in out_root.iterdir() if path.is_dir()):
        for path in sorted(faction_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = payload.setdefault("source", {})
            source.setdefault("output_slug", faction_dir.name)
            payloads.append((path, payload))
    return payloads


def refresh_existing_payload(payload: dict[str, object], output_slug: str) -> dict[str, object]:
    source = payload.setdefault("source", {})
    normalized_url = normalize_wahapedia_url(str(source.get("url") or ""))
    exported_titles = exported_section_titles(payload)
    existing_quality = payload.get("quality", {}) if isinstance(payload.get("quality"), dict) else {}
    raw_titles = list(existing_quality.get("rawSectionTitles", [])) or list(exported_titles)
    warnings = list(existing_quality.get("warnings", []))

    source["normalizedUrl"] = normalized_url
    source["canonicalSourceId"] = canonical_source_id(normalized_url)
    source["output_slug"] = output_slug
    source.setdefault("faction_slug", output_slug)
    source.setdefault("datasheet_slug", slug_from_url(normalized_url))
    source.setdefault("fetchedAt", utc_now())
    source["contentHash"] = str(source.get("contentHash") or stable_json_hash(payload))

    payload["exportSchemaVersion"] = EXPORT_SCHEMA_VERSION
    payload["parserVersion"] = PARSER_VERSION
    payload["quality"] = default_quality(raw_titles, exported_titles, warnings=warnings)
    return payload


def rewrite_existing_exports(out_root: Path, output_slug: str) -> tuple[Path, Path]:
    faction_dir = out_root / output_slug
    if not faction_dir.exists():
        raise FileNotFoundError(f"Faction export directory not found: {faction_dir}")

    bundle = []
    for path in sorted(faction_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        refreshed = refresh_existing_payload(payload, output_slug)
        path.write_text(json.dumps(refreshed, indent=2), encoding="utf-8")
        bundle.append(refreshed)

    bundle_path = faction_dir / "index.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    manifest_path = write_export_manifest(out_root)
    return bundle_path, manifest_path


def sync_source_fields(
    payload: dict[str, object],
    canonical_payload: dict[str, object],
) -> dict[str, object]:
    for key in (
        "name",
        "base_size",
        "characteristics",
        "weapons",
        "abilities",
        "unit_composition",
        "keywords",
        "faction_keywords",
        "sections",
    ):
        payload[key] = copy.deepcopy(canonical_payload.get(key))
    return payload


def canonical_preference_score(payload: dict[str, object]) -> tuple[int, int, int]:
    source = payload.get("source", {}) if isinstance(payload.get("source"), dict) else {}
    normalized_url = normalize_wahapedia_url(str(source.get("normalizedUrl") or source.get("url") or ""))
    output_slug = str(source.get("output_slug") or "")
    source_faction = ""
    try:
        source_faction = faction_from_url(normalized_url) if normalized_url else ""
    except ValueError:
        source_faction = ""
    quality = payload.get("quality", {}) if isinstance(payload.get("quality"), dict) else {}
    return (
        1 if output_slug == source_faction else 0,
        len(list(quality.get("exportedSectionTitles", []))),
        len(json.dumps(payload.get("sections", []), sort_keys=True)),
    )


def sync_duplicate_canonical_exports(out_root: Path) -> tuple[int, Path]:
    payload_entries = load_existing_export_payload_paths(out_root)
    groups: dict[str, list[tuple[Path, dict[str, object]]]] = {}
    for path, payload in payload_entries:
        source = payload.get("source", {}) if isinstance(payload.get("source"), dict) else {}
        canonical_source = str(source.get("canonicalSourceId") or "").strip()
        if canonical_source:
            groups.setdefault(canonical_source, []).append((path, payload))

    rewritten_paths: set[Path] = set()
    changed_count = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        canonical_path, canonical_payload = max(
            members,
            key=lambda item: canonical_preference_score(item[1]),
        )
        canonical_core = stable_json_hash(
            {
                "name": canonical_payload.get("name"),
                "base_size": canonical_payload.get("base_size"),
                "characteristics": canonical_payload.get("characteristics"),
                "weapons": canonical_payload.get("weapons"),
                "abilities": canonical_payload.get("abilities"),
                "unit_composition": canonical_payload.get("unit_composition"),
                "keywords": canonical_payload.get("keywords"),
                "faction_keywords": canonical_payload.get("faction_keywords"),
                "sections": canonical_payload.get("sections"),
            }
        )
        for path, payload in members:
            payload_core = stable_json_hash(
                {
                    "name": payload.get("name"),
                    "base_size": payload.get("base_size"),
                    "characteristics": payload.get("characteristics"),
                    "weapons": payload.get("weapons"),
                    "abilities": payload.get("abilities"),
                    "unit_composition": payload.get("unit_composition"),
                    "keywords": payload.get("keywords"),
                    "faction_keywords": payload.get("faction_keywords"),
                    "sections": payload.get("sections"),
                }
            )
            if path == canonical_path or payload_core == canonical_core:
                continue
            output_slug = str(payload.get("source", {}).get("output_slug") or path.parent.name)
            refreshed = refresh_existing_payload(
                sync_source_fields(payload, canonical_payload),
                output_slug,
            )
            path.write_text(json.dumps(refreshed, indent=2), encoding="utf-8")
            rewritten_paths.add(path)
            changed_count += 1

    for faction_dir in sorted({path.parent for path in rewritten_paths}):
        bundle = []
        for path in sorted(faction_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            bundle.append(json.loads(path.read_text(encoding="utf-8")))
        (faction_dir / "index.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    manifest_path = write_export_manifest(out_root)
    return changed_count, manifest_path


def write_export_manifest(out_root: Path) -> Path:
    records = [
        export_manifest_record(payload)
        for payload in load_existing_export_payloads(out_root)
    ]
    records.sort(
        key=lambda record: (
            str(record.get("outputSlug") or ""),
            str(record.get("datasheetSlug") or ""),
        )
    )
    manifest = {
        "exportSchemaVersion": EXPORT_SCHEMA_VERSION,
        "parserVersion": PARSER_VERSION,
        "generatedAt": utc_now(),
        "records": records,
    }
    manifest_path = out_root / "export-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    args = parse_args()
    out_root = Path(args.out_dir)
    if not args.url and not args.output_slug and not args.sync_duplicates:
        raise SystemExit("Either --url, --output-slug, or --sync-duplicates is required.")
    if args.sync_duplicates:
        changed_count, manifest_path = sync_duplicate_canonical_exports(out_root)
        print(f"Synchronized {changed_count} duplicate exports", flush=True)
        print(f"Export manifest written to {manifest_path}", flush=True)
        return 0
    if args.rewrite_existing:
        if not args.output_slug:
            raise SystemExit("--rewrite-existing requires --output-slug.")
        bundle_path, manifest_path = rewrite_existing_exports(out_root, args.output_slug)
        print(f"Bundle written to {bundle_path}", flush=True)
        print(f"Export manifest written to {manifest_path}", flush=True)
        return 0

    items = filtered_items(manifest_items(args), args.card_slug)
    if not items:
        raise SystemExit("No datasheets matched the requested filters.")

    bundle = []

    def export_item(index: int, item: dict[str, str]) -> tuple[int, dict[str, object], Path]:
        url = item["href"]
        payload = parse_datasheet(url)
        target_slug = args.output_slug or payload["source"]["faction_slug"]
        payload["source"]["output_slug"] = target_slug
        faction_dir = out_root / target_slug
        faction_dir.mkdir(parents=True, exist_ok=True)
        destination = faction_dir / f"{payload['source']['datasheet_slug']}.json"
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return index, payload, destination

    indexed_results: list[tuple[int, dict[str, object], Path]] = []
    workers = max(1, args.workers)
    if workers == 1:
        for index, item in enumerate(items, start=1):
            indexed_results.append(export_item(index, item))
            if args.delay and index < len(items):
                time.sleep(args.delay)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(export_item, index, item): index
                for index, item in enumerate(items, start=1)
            }
            for future in concurrent.futures.as_completed(futures):
                indexed_results.append(future.result())
                if args.delay:
                    time.sleep(args.delay)

    for index, payload, destination in sorted(indexed_results, key=lambda value: value[0]):
        bundle.append(payload)
        print(f"[{index}/{len(items)}] wrote {destination}", flush=True)

    faction_dir = out_root / bundle[0]["source"]["output_slug"]
    bundle_path = faction_dir / "index.json"
    full_bundle = load_existing_faction_bundle(faction_dir)
    bundle_path.write_text(json.dumps(full_bundle, indent=2), encoding="utf-8")
    print(f"Bundle written to {bundle_path}", flush=True)
    manifest_path = write_export_manifest(out_root)
    print(f"Export manifest written to {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
