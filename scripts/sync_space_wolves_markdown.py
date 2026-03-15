import re
from collections import OrderedDict
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup, NavigableString, Tag


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SPACE_WOLVES_MD_DIR = Path(
    "/Users/jasricha/Documents/Github_Personal/warhammer_40k/wahpedia/space_wolves"
)

BASE_URL = "https://wahapedia.ru/wh40k10ed/factions/space-marines"

VARIANT_PAGES = OrderedDict(
    {
        "iron_priest.md": ["Iron-Priest-On-Thunderwolf"],
        "logan_grimnar.md": ["Logan-Grimnar-On-Stormrider"],
        "wolf_guard_battle_leader.md": [
            "Wolf-Guard-Battle-Leader-In-Terminator-Armour",
            "Wolf-Guard-Battle-Leader-On-Thunderwolf",
        ],
        "wolf_guard_pack_leader.md": [
            "Wolf-Guard-Pack-Leader-In-Terminator-Armour",
            "Wolf-Guard-Pack-Leader-With-Jump-Pack",
        ],
        "wolf_scouts.md": ["Wolf-Scouts-1"],
        "wulfen_dreadnought.md": ["Wulfen-Dreadnought-1"],
        "wulfen.md": ["Wulfen-with-Storm-Shields"],
    }
)

STANDALONE_PAGES = OrderedDict(
    {
        "wolf_guard.md": "Wolf-Guard",
    }
)

VARIANT_BLOCK_START = "<!-- GENERATED VARIANT DATASHEETS START -->"
VARIANT_BLOCK_END = "<!-- GENERATED VARIANT DATASHEETS END -->"
SOUP_CACHE: dict[str, BeautifulSoup] = {}


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"\s+\)", ")", value)
    return value.strip()


def title_case_heading(value: str) -> str:
    return value.title()


def fetch_soup(page_slug: str) -> BeautifulSoup:
    if page_slug in SOUP_CACHE:
        return SOUP_CACHE[page_slug]

    response = requests.get(f"{BASE_URL}/{page_slug}", timeout=15, verify=False)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    SOUP_CACHE[page_slug] = soup
    return soup


def extract_description(card: Tag) -> str:
    legend = card.select_one(".picLegend")
    if legend and legend.has_attr("title"):
        return clean_text(legend["title"])
    return ""


def extract_title_and_stats(card: Tag) -> tuple[str, list[tuple[str, str]]]:
    title = clean_text(card.select_one(".dsH2Header div").get_text(" ", strip=True))
    stats = []
    for stat in card.select(".dsBannerWrap .dsProfileWrap .dsCharWrap"):
        name_node = stat.select_one(".dsCharName")
        value_node = stat.select_one(".dsCharValue")
        if not name_node or not value_node:
            continue
        name = clean_text(name_node.get_text(" ", strip=True))
        value = clean_text(value_node.get_text(" ", strip=True))
        stats.append((name, value))

    invul_label = card.select_one(".dsInvulWrap .dsCharInvulText")
    invul_value = card.select_one(".dsInvulWrap .dsCharInvulValue")
    if invul_label and invul_value:
        stats.append(("Invul", clean_text(invul_value.get_text(" ", strip=True))))

    return title, stats


def extract_weapon_cell(cell: Tag) -> tuple[str, str]:
    container = cell.select_one("span") or cell
    weapon_parts = []
    keywords = []

    for item in container.contents:
        if isinstance(item, NavigableString):
            text = clean_text(str(item))
            if text:
                weapon_parts.append(text)
            continue

        if not isinstance(item, Tag):
            continue

        classes = item.get("class", [])
        if any(class_name.startswith("kwb") for class_name in classes):
            keyword_text = clean_text(" ".join(item.stripped_strings))
            if keyword_text:
                keywords.append(keyword_text.upper())
            continue

        text = clean_text(item.get_text(" ", strip=True))
        if text:
            weapon_parts.append(text)

    weapon_name = clean_text(" ".join(weapon_parts))
    keyword_text = ", ".join(f"[{item}]" for item in keywords) if keywords else "-"
    return weapon_name, keyword_text


def extract_weapon_tables(left_col: Tag) -> list[tuple[str, list[list[str]]]]:
    sections = []
    for table in left_col.select("table.wTable"):
        rows = table.select("tr")
        current_heading = ""
        section_rows = []

        for row in rows:
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue

            header_label = ""
            if len(cells) >= 2:
                header_label = clean_text(cells[1].get_text(" ", strip=True))
            if header_label in {"RANGED WEAPONS", "MELEE WEAPONS"}:
                if current_heading and section_rows:
                    sections.append((current_heading, section_rows))
                current_heading = "Ranged Weapons" if header_label == "RANGED WEAPONS" else "Melee Weapons"
                section_rows = []
                continue

            if len(cells) < 8:
                continue

            weapon, keywords = extract_weapon_cell(cells[1])
            stats = [clean_text(cell.get_text(" ", strip=True)) for cell in cells[2:8]]
            section_rows.append([weapon, *stats, keywords])

        if current_heading and section_rows:
            sections.append((current_heading, section_rows))

    return sections


def extract_wargear_options(left_col: Tag) -> tuple[list[str], str]:
    options = []
    comment = ""
    for header in left_col.select(".dsHeader"):
        label = clean_text(header.get_text(" ", strip=True))
        if label != "WARGEAR OPTIONS":
            continue

        next_node = header.find_next_sibling()
        while next_node and getattr(next_node, "name", None) == "br":
            next_node = next_node.find_next_sibling()

        if next_node and next_node.name == "ul":
            for item in next_node.find_all("li", recursive=False):
                parts = []
                for child in item.contents:
                    if isinstance(child, NavigableString):
                        text = clean_text(str(child))
                        if text:
                            parts.append(text)
                        continue

                    if isinstance(child, Tag) and child.name != "ul":
                        text = clean_text(child.get_text(" ", strip=True))
                        if text:
                            parts.append(text)
                text = clean_text(" ".join(parts)).rstrip("*").strip()
                if text:
                    options.append(text)

        options_comment = left_col.select_one(".dsOptionsComment")
        if options_comment:
            comment = clean_text(options_comment.get_text(" ", strip=True))
        break

    return options, comment


def split_ability_segments(ability: Tag) -> list[tuple[str, str]]:
    raw_text = clean_text(ability.get_text(" ", strip=True))
    if ":" not in raw_text:
        return []

    prefix, remainder = raw_text.split(":", 1)
    prefix = clean_text(prefix)
    remainder = clean_text(remainder)

    if prefix in {"CORE", "FACTION"}:
        items = [clean_text(item) for item in re.split(r"\s*,\s*", remainder) if clean_text(item)]
        body = "\n".join(f"*   **{item}**" for item in items)
        return [(prefix.title(), body)]

    pieces = []
    current_label = None
    current_tokens = []
    for token in [clean_text(item) for item in ability.stripped_strings]:
        if token.endswith(":") and len(token) <= 80:
            if current_label:
                pieces.append((current_label, clean_text(" ".join(current_tokens))))
            current_label = token[:-1]
            current_tokens = []
            continue
        current_tokens.append(token)

    if current_label:
        pieces.append((current_label, clean_text(" ".join(current_tokens))))
        return pieces

    return [(prefix, remainder)]


def extract_keywords(card: Tag) -> tuple[str, str]:
    keywords_block = card.select_one(".ds2colKW")
    text = clean_text(keywords_block.get_text(" ", strip=True))
    keyword_text = text.split("FACTION KEYWORDS:")[0].replace("KEYWORDS:", "").strip(" ,")
    faction_text = text.split("FACTION KEYWORDS:")[1].strip(" ,")
    keywords = ", ".join(f"**{item.strip()}**" for item in keyword_text.split(",") if item.strip())
    faction_keywords = ", ".join(
        f"**{item.strip()}**" for item in faction_text.split(",") if item.strip()
    )
    return keywords, faction_keywords


def extract_right_column_sections(right_col: Tag) -> dict[str, list[Tag]]:
    sections: dict[str, list[Tag]] = OrderedDict()
    current_header = None

    for child in right_col.find_all(recursive=False):
        classes = child.get("class", [])
        if "dsHeader" in classes:
            current_header = clean_text(child.get_text(" ", strip=True))
            sections[current_header] = []
            continue

        if "dsAbility" in classes and current_header:
            sections[current_header].append(child)

    return sections


def format_stats_table(stats: list[tuple[str, str]], heading_level: int) -> str:
    hashes = "#" * heading_level
    headers = " | ".join(name for name, _ in stats)
    separators = " | ".join(":---" for _ in stats)
    values = " | ".join(value for _, value in stats)
    return "\n".join(
        [
            f"{hashes} Stats",
            f"| {headers} |",
            f"| {separators} |",
            f"| {values} |",
        ]
    )


def format_weapon_sections(sections: list[tuple[str, list[list[str]]]], heading_level: int) -> str:
    hashes = "#" * heading_level
    rendered = []
    for title, rows in sections:
        rendered.append(f"{hashes} {title}")
        rendered.append("| Weapon | Range | A | BS/WS | S | AP | D | Keywords |")
        rendered.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for row in rows:
            rendered.append(f"| {' | '.join(row)} |")
        rendered.append("")
    return "\n".join(rendered).rstrip()


def format_ability_sections(sections: dict[str, list[Tag]], heading_level: int) -> str:
    hashes = "#" * heading_level
    rendered = []
    ability_blocks = sections.get("ABILITIES", [])
    if ability_blocks:
        rendered.append(f"{hashes} Abilities")
        for block in ability_blocks:
            for title, body in split_ability_segments(block):
                rendered.append(f"{hashes}# **{title}**")
                rendered.append(body)
                rendered.append("")

    wargear_blocks = sections.get("WARGEAR ABILITIES", [])
    if wargear_blocks:
        rendered.append(f"{hashes} Wargear Abilities")
        for block in wargear_blocks:
            for title, body in split_ability_segments(block):
                rendered.append(f"{hashes}# **{title}**")
                rendered.append(body)
                rendered.append("")

    return "\n".join(rendered).rstrip()


def is_points_row(text: str) -> bool:
    return bool(re.fullmatch(r"(?:\d+\s+models?\s+\d+\s*)+", text)) or bool(
        re.fullmatch(r"\d+\s+model\s+\d+", text)
    )


def format_unit_composition(section_name: str, blocks: list[Tag], heading_level: int) -> str:
    hashes = "#" * heading_level
    rendered = [f"{hashes} {title_case_heading(section_name)}"]
    for block in blocks:
        text = clean_text(block.get_text(" ", strip=True))
        if not text or is_points_row(text):
            continue
        rendered.append(f"*   {text}")
    return "\n".join(rendered)


def format_attachment_section(section_name: str, blocks: list[Tag], heading_level: int) -> str:
    hashes = "#" * heading_level
    title = "Leader Attachment" if section_name == "LEADER" else "Attached Unit"
    rendered = [f"{hashes} {title}"]

    for block in blocks:
        text = clean_text(block.get_text(" ", strip=True))
        if ":" in text:
            prefix, suffix = text.split(":", 1)
            prefix = clean_text(prefix)
            suffix = clean_text(suffix)
            if any(marker in suffix for marker in ("You must", "If it is not possible", "counts as", "does not take part")):
                rendered.append(f"{prefix}: {suffix}")
            elif prefix.endswith("following unit"):
                rendered.append(prefix + ":")
                rendered.append(f"*   **{suffix}**")
            elif prefix.endswith("following units") and "," in suffix:
                rendered.append(prefix + ":")
                for item in [clean_text(part) for part in suffix.split(",") if clean_text(part)]:
                    rendered.append(f"*   **{item}**")
            else:
                rendered.append(f"{prefix}: {suffix}")
        else:
            rendered.append(text)

    return "\n".join(rendered)


def format_keywords_section(keywords: str, faction_keywords: str, heading_level: int) -> str:
    hashes = "#" * heading_level
    return "\n".join(
        [
            f"{hashes} Keywords",
            keywords,
            "",
            f"{hashes} Faction Keywords",
            faction_keywords,
        ]
    )


def build_datasheet_markdown(page_slug: str, section_heading_level: int, include_title: bool) -> str:
    soup = fetch_soup(page_slug)
    card = soup.select_one("div.dsOuterFrame.datasheet")
    left_col = card.select_one("div.dsLeftСol")
    right_col = card.select_one("div.dsRightСol")

    title, stats = extract_title_and_stats(card)
    description = extract_description(card)
    weapon_sections = extract_weapon_tables(left_col)
    wargear_options, wargear_comment = extract_wargear_options(left_col)
    right_sections = extract_right_column_sections(right_col)
    keywords, faction_keywords = extract_keywords(card)

    chunks = []
    if include_title:
        chunks.append(f"# Datasheet: {title}")
        chunks.append("")

    if description:
        chunks.append(description)
        chunks.append("")

    chunks.append(format_stats_table(stats, section_heading_level))
    chunks.append("")
    chunks.append(format_weapon_sections(weapon_sections, section_heading_level))
    chunks.append("")
    chunks.append(format_ability_sections(right_sections, section_heading_level))

    if wargear_options:
        hashes = "#" * section_heading_level
        chunks.extend(["", f"{hashes} Wargear Options"])
        for option in wargear_options:
            chunks.append(f"*   {option}")
        if wargear_comment:
            chunks.extend(["", wargear_comment])

    if right_sections.get("UNIT COMPOSITION"):
        chunks.extend(["", format_unit_composition("UNIT COMPOSITION", right_sections["UNIT COMPOSITION"], section_heading_level)])

    if right_sections.get("LEADER"):
        chunks.extend(["", format_attachment_section("LEADER", right_sections["LEADER"], section_heading_level)])

    if right_sections.get("ATTACHED UNIT"):
        chunks.extend(["", format_attachment_section("ATTACHED UNIT", right_sections["ATTACHED UNIT"], section_heading_level)])

    chunks.extend(["", format_keywords_section(keywords, faction_keywords, section_heading_level)])
    return "\n".join(chunk for chunk in chunks if chunk is not None).strip() + "\n"


def update_parent_file(path: Path, page_slugs: list[str]) -> None:
    content = path.read_text(encoding="utf-8").rstrip() + "\n"
    sections = []
    for page_slug in page_slugs:
        markdown = build_datasheet_markdown(page_slug, section_heading_level=4, include_title=False)
        title = clean_text(fetch_soup(page_slug).select_one(".dsH2Header div").get_text(" ", strip=True))
        sections.append(f"### {title}\n\n{markdown.strip()}")

    block = "\n".join(
        [
            VARIANT_BLOCK_START,
            "",
            "## Variant Datasheets",
            "",
            "\n\n".join(sections),
            "",
            VARIANT_BLOCK_END,
        ]
    )

    pattern = re.compile(
        rf"\n?{re.escape(VARIANT_BLOCK_START)}.*?{re.escape(VARIANT_BLOCK_END)}\n?",
        re.DOTALL,
    )
    if pattern.search(content):
        updated = pattern.sub("\n" + block + "\n", content).strip() + "\n"
    else:
        updated = content.rstrip() + "\n\n" + block + "\n"
    path.write_text(updated, encoding="utf-8")


def ensure_wolf_guard_index_entry(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    entry = "*   [Wolf Guard](wolf_guard.md)\n"
    if entry in content:
        return
    anchor = "*   [Wolf Guard Headtakers](wolf_guard_headtakers.md)\n"
    if anchor not in content:
        raise RuntimeError("Could not find insertion point for Wolf Guard index entry")
    content = content.replace(anchor, entry + anchor)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    for file_name, page_slug in STANDALONE_PAGES.items():
        output_path = SPACE_WOLVES_MD_DIR / file_name
        output_path.write_text(
            build_datasheet_markdown(page_slug, section_heading_level=2, include_title=True),
            encoding="utf-8",
        )

    for parent_file, page_slugs in VARIANT_PAGES.items():
        update_parent_file(SPACE_WOLVES_MD_DIR / parent_file, page_slugs)

    ensure_wolf_guard_index_entry(SPACE_WOLVES_MD_DIR / "datasheets.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
