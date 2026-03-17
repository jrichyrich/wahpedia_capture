import argparse
import concurrent.futures
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def normalize_wahapedia_url(url: str) -> str:
    return (url or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Wahapedia datasheets into structured JSON."
    )
    group = parser.add_mutually_exclusive_group(required=True)
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


def split_title_and_base_size(value: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)(?:\s*\((.+)\))?$", normalize_space(value))
    if not match:
        return normalize_space(value), None
    return normalize_space(match.group(1)), normalize_space(match.group(2))


def fetch_soup(url: str) -> BeautifulSoup:
    url = normalize_wahapedia_url(url)
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


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


def parse_option_group_entries(block: Tag) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    for list_wrap in block.find_all("ul", recursive=False):
        for item in list_wrap.find_all("li", recursive=False):
            prompt_parts = []
            for child in item.contents:
                if isinstance(child, Tag) and child.name == "ul":
                    continue
                prompt_parts.append(str(child))

            prompt = normalize_space(BeautifulSoup("".join(prompt_parts), "html.parser").get_text(" ", strip=True))
            choices = []
            nested = item.find("ul", recursive=False)
            if nested:
                choices = [
                    normalize_space(option.get_text(" ", strip=True))
                    for option in nested.find_all("li", recursive=False)
                    if normalize_space(option.get_text(" ", strip=True))
                ]

            if (prompt or choices) and not (prompt == "None" and not choices):
                entries.append(
                    {
                        "type": "option_group",
                        "label": prompt,
                        "items": choices,
                    }
                )

    for comment in block.select(".dsOptionsComment"):
        text = normalize_space(comment.get_text(" ", strip=True))
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


def parse_section_block(section_title: str, block: Tag) -> list[dict[str, object]]:
    if block.select_one(".PriceTag"):
        return [parse_points_block(block)]

    text = normalize_space(block.get_text(" ", strip=True))
    if not text:
        return []

    if section_title == "WARGEAR OPTIONS":
        option_entries = parse_option_group_entries(block)
        if option_entries:
            return option_entries

    tagged_match = re.match(r"^([A-Z ]+):\s*(.+)$", text)
    if tagged_match and tagged_match.group(1) in {"CORE", "FACTION"}:
        return [
            {
                "type": "tagged_list",
                "label": tagged_match.group(1),
                "items": [normalize_space(tagged_match.group(2))],
            }
        ]

    list_items = [normalize_space(item.get_text(" ", strip=True)) for item in block.select("ul > li")]
    entry_type = "rule" if section_title == "ABILITIES" else "statement"
    labeled_statements = parse_top_level_bold_segments(block, entry_type=entry_type)

    if list_items or labeled_statements:
        entries: list[dict[str, object]] = []
        if list_items:
            entries.append({"type": "list", "items": list_items})
        entries.extend(labeled_statements)
        if not entries:
            entries.append({"type": "text", "text": text})
        return entries

    entries = []
    for fragment in split_block_on_dividers(block):
        bold_entries = parse_top_level_bold_segments(fragment, entry_type=entry_type)
        if bold_entries:
            entries.extend(bold_entries)
            continue

        body = normalize_space(fragment.get_text(" ", strip=True))
        if body:
            entries.append({"type": "text", "text": body})

    return entries


def parse_left_column_sections(card: Tag) -> list[dict[str, object]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return []

    children = direct_children(columns_wrap)
    if not children:
        return []

    left_column = children[0]
    sections = []
    current_title: str | None = None
    current_nodes: list[str] = []
    seen_table = False

    def flush_current() -> None:
        nonlocal current_title, current_nodes
        if not current_title:
            current_nodes = []
            return
        block = BeautifulSoup("".join(current_nodes), "html.parser")
        entries = parse_section_block(current_title, block)
        sections.append({"title": current_title, "entries": entries})
        current_nodes = []

    for child in left_column.contents:
        if isinstance(child, Tag) and child.name == "table":
            seen_table = True
            continue
        if not seen_table or not isinstance(child, Tag):
            continue

        classes = child.get("class", [])
        if "dsLineHor" in classes:
            continue
        if "dsHeader" in classes:
            flush_current()
            current_title = normalize_space(child.get_text(" ", strip=True))
            continue
        if current_title:
            current_nodes.append(str(child))

    flush_current()
    return [section for section in sections if section.get("entries")]


def parse_right_column_sections(card: Tag) -> list[dict[str, object]]:
    columns_wrap = card.select_one("div.ds2col")
    if not columns_wrap:
        return []

    children = direct_children(columns_wrap)
    if len(children) < 2:
        return []

    right_column = children[1]
    sections = []
    current_section: dict[str, object] | None = None

    for child in direct_children(right_column):
        classes = child.get("class", [])
        if "dsHeader" in classes:
            current_section = {
                "title": normalize_space(child.get_text(" ", strip=True)),
                "entries": [],
            }
            sections.append(current_section)
            continue

        if "dsAbility" not in classes:
            continue

        if current_section is None:
            current_section = {"title": "UNTITLED", "entries": []}
            sections.append(current_section)

        current_section["entries"].extend(parse_section_block(current_section["title"], child))

    return sections


def parse_sections(card: Tag) -> list[dict[str, object]]:
    return parse_left_column_sections(card) + parse_right_column_sections(card)


def parse_keywords(card: Tag) -> dict[str, list[str]]:
    keywords_wrap = card.select_one("div.ds2colKW")
    if not keywords_wrap:
        return {"keywords": [], "faction_keywords": []}

    children = direct_children(keywords_wrap)
    if len(children) < 2:
        return {"keywords": [], "faction_keywords": []}

    left_text = normalize_space(children[0].get_text(" ", strip=True))
    right_text = normalize_space(children[1].get_text(" ", strip=True))

    def split_keywords(text: str, prefix: str) -> list[str]:
        value = normalize_space(text.replace(prefix, "", 1))
        return [normalize_space(item) for item in re.split(r"\s*,\s*", value) if normalize_space(item)]

    return {
        "keywords": split_keywords(left_text, "KEYWORDS:"),
        "faction_keywords": split_keywords(right_text, "FACTION KEYWORDS:"),
    }


def build_section_lookup(sections: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {slugify_key(str(section["title"])): section for section in sections}


def parse_datasheet(url: str) -> dict[str, object]:
    url = normalize_wahapedia_url(url)
    soup = fetch_soup(url)
    card = soup.select_one("div.dsOuterFrame.datasheet")
    if not card:
        raise ValueError(f"Datasheet markup not found for {url}")

    raw_title = normalize_space(card.select_one("div.dsH2Header").get_text(" ", strip=True))
    name, base_size = split_title_and_base_size(raw_title)
    sections = parse_sections(card)
    section_lookup = build_section_lookup(sections)

    ability_entries = section_lookup.get("abilities", {}).get("entries", [])
    unit_composition_entries = section_lookup.get("unit_composition", {}).get("entries", [])

    faction_slug = faction_from_url(url)
    datasheet_slug = slug_from_url(url)

    payload = {
        "source": {
            "url": url,
            "faction_slug": faction_slug,
            "datasheet_slug": datasheet_slug,
        },
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
        "keywords": parse_keywords(card)["keywords"],
        "faction_keywords": parse_keywords(card)["faction_keywords"],
        "sections": sections,
    }

    return payload


def load_manifest(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Manifest must be a JSON list: {path}")
    return data


def manifest_items(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.url:
        return [{"href": args.url, "name": ""}]

    manifest_path = (
        Path(args.manifest_path)
        if args.manifest_path
        else Path("out") / "source" / f"{args.output_slug}-links.json"
    )
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


def main() -> int:
    args = parse_args()
    items = filtered_items(manifest_items(args), args.card_slug)
    if not items:
        raise SystemExit("No datasheets matched the requested filters.")

    bundle = []
    out_root = Path(args.out_dir)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
