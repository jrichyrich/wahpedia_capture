import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PAGE_WIDTH = 1000
MARGIN = 36
GAP = 14
INK = (24, 24, 24)
PANEL = (246, 241, 231)
SHADE = (226, 217, 203)
LIGHT = (253, 250, 244)
LINE = (45, 45, 45)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render exported datasheet JSON files into local PNG source cards."
    )
    parser.add_argument("--output-slug", required=True)
    parser.add_argument("--json-root", default="out/json")
    parser.add_argument("--out-root", default="out/factions")
    parser.add_argument(
        "--card-slug",
        action="append",
        default=[],
        help="Limit rendering to one or more datasheet slugs.",
    )
    return parser.parse_args()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_TITLE = font(38, bold=True)
FONT_H2 = font(22, bold=True)
FONT_H3 = font(18, bold=True)
FONT_BODY = font(18)
FONT_SMALL = font(15)
FONT_STAT_LABEL = font(14, bold=True)
FONT_STAT_VALUE = font(30, bold=True)


def text_size(draw: ImageDraw.ImageDraw, text: str, active_font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=active_font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: object, active_font: ImageFont.ImageFont, width: int) -> list[str]:
    words = str(text or "").replace("\n", " ").split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and text_size(draw, candidate, active_font)[0] > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: object,
    active_font: ImageFont.ImageFont,
    width: int,
    *,
    fill: tuple[int, int, int] = INK,
    spacing: int = 5,
) -> int:
    x, y = xy
    line_height = text_size(draw, "Ag", active_font)[1] + spacing
    for line in wrap_text(draw, text, active_font, width):
        draw.text((x, y), line, font=active_font, fill=fill)
        y += line_height
    return y


def draw_section_header(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, title: str) -> int:
    draw.rectangle((x, y, x + width, y + 34), fill=SHADE, outline=LINE, width=1)
    draw.text((x + 12, y + 7), title.upper(), font=FONT_H3, fill=INK)
    return y + 34


def draw_stat_grid(draw: ImageDraw.ImageDraw, card: dict[str, object], x: int, y: int, width: int) -> int:
    characteristics = card.get("characteristics", {}) if isinstance(card.get("characteristics"), dict) else {}
    labels = [label for label in ("M", "T", "Sv", "W", "Ld", "OC") if characteristics.get(label)]
    box_gap = 8
    box_width = (width - box_gap * (len(labels) - 1)) // max(1, len(labels))
    for index, label in enumerate(labels):
        left = x + index * (box_width + box_gap)
        draw.rectangle((left, y, left + box_width, y + 76), fill=LIGHT, outline=LINE, width=1)
        value = str(characteristics.get(label) or "")
        tw, _ = text_size(draw, label, FONT_STAT_LABEL)
        draw.text((left + (box_width - tw) / 2, y + 8), label, font=FONT_STAT_LABEL, fill=INK)
        tw, _ = text_size(draw, value, FONT_STAT_VALUE)
        draw.text((left + (box_width - tw) / 2, y + 34), value, font=FONT_STAT_VALUE, fill=INK)
    y += 90
    invul = characteristics.get("Invulnerable Save")
    if invul:
        text = f"Invulnerable Save: {invul}"
        draw.rectangle((x, y, x + 245, y + 34), fill=LIGHT, outline=LINE, width=1)
        draw.text((x + 10, y + 8), text, font=FONT_SMALL, fill=INK)
        y += 48
    return y


def weapon_columns(rows: list[dict[str, object]], skill_key: str) -> list[str]:
    base = ["range", "a", skill_key, "s", "ap", "d"]
    return [key for key in base if any(row.get(key) for row in rows)]


def draw_weapon_table(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    title: str,
    rows: list[dict[str, object]],
    skill_key: str,
) -> int:
    if not rows:
        return y
    y = draw_section_header(draw, x, y, width, title)
    columns = weapon_columns(rows, skill_key)
    stat_width = 60
    name_width = width - stat_width * len(columns)
    draw.rectangle((x, y, x + width, y + 30), fill=LIGHT, outline=LINE, width=1)
    draw.text((x + 8, y + 7), "WEAPON", font=FONT_SMALL, fill=INK)
    for index, column in enumerate(columns):
        draw.text((x + name_width + index * stat_width + 8, y + 7), column.upper(), font=FONT_SMALL, fill=INK)
    y += 30
    for row in rows:
        name = str(row.get("name") or "")
        abilities = ", ".join(str(item) for item in row.get("abilities", []))
        name_lines = wrap_text(draw, name, FONT_SMALL, name_width - 12)
        ability_lines = wrap_text(draw, abilities, FONT_SMALL, name_width - 12) if abilities else []
        row_height = max(34, 12 + 19 * (len(name_lines) + len(ability_lines)))
        draw.rectangle((x, y, x + width, y + row_height), fill=PANEL, outline=(160, 150, 136), width=1)
        cy = y + 7
        for line in name_lines:
            draw.text((x + 8, cy), line, font=FONT_SMALL, fill=INK)
            cy += 19
        for line in ability_lines:
            draw.text((x + 8, cy), line.upper(), font=FONT_SMALL, fill=(80, 80, 80))
            cy += 19
        for index, column in enumerate(columns):
            value = str(row.get(column) or "")
            draw.text((x + name_width + index * stat_width + 8, y + 9), value, font=FONT_SMALL, fill=INK)
        y += row_height
    return y + GAP


def render_entry_lines(entry: dict[str, object]) -> list[tuple[str, object]]:
    entry_type = entry.get("type")
    if entry_type == "tagged_list":
        return [(str(entry.get("label") or ""), ", ".join(str(item) for item in entry.get("items", [])))]
    if entry_type == "rule":
        return [(str(entry.get("name") or ""), entry.get("text") or "")]
    if entry_type == "statement":
        return [(str(entry.get("label") or ""), entry.get("text") or "")]
    if entry_type == "list":
        return [("", item) for item in entry.get("items", [])]
    if entry_type == "points":
        return [("Points", f"{row.get('label')}: {row.get('points')}") for row in entry.get("rows", [])]
    return [("", entry.get("text") or "")]


def draw_sections(draw: ImageDraw.ImageDraw, card: dict[str, object], x: int, y: int, width: int) -> int:
    sections = card.get("sections", []) if isinstance(card.get("sections"), list) else []
    for section in sections:
        title = str(section.get("title") or "")
        y = draw_section_header(draw, x, y, width, title)
        for entry in section.get("entries", []):
            for label, text in render_entry_lines(entry):
                block_top = y
                if label:
                    draw.text((x + 10, y + 8), label.upper(), font=FONT_SMALL, fill=INK)
                    y += 22
                y = draw_wrapped(draw, (x + 10, y + 4), text, FONT_SMALL, width - 20)
                y += 8
                draw.line((x, y, x + width, y), fill=(190, 180, 166), width=1)
                if y - block_top < 28:
                    y = block_top + 28
        y += GAP
    return y


def render_card(card: dict[str, object]) -> Image.Image:
    scratch = Image.new("RGB", (PAGE_WIDTH, 4000), PANEL)
    draw = ImageDraw.Draw(scratch)
    content_width = PAGE_WIDTH - MARGIN * 2
    y = MARGIN
    title = str(card.get("name") or "Datasheet")
    base_size = str(card.get("base_size") or "")
    draw.rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 82), fill=SHADE, outline=LINE, width=2)
    draw.text((MARGIN + 16, y + 18), title.upper(), font=FONT_TITLE, fill=INK)
    if base_size:
        wrapped = textwrap.shorten(base_size.replace("⌀", "dia. "), width=30, placeholder="...")
        draw.text((PAGE_WIDTH - MARGIN - 230, y + 32), wrapped, font=FONT_SMALL, fill=INK)
    y += 100
    y = draw_stat_grid(draw, card, MARGIN, y, content_width)

    left_width = 570
    right_width = content_width - left_width - GAP
    left_y = y
    right_y = y
    weapons = card.get("weapons", {}) if isinstance(card.get("weapons"), dict) else {}
    left_y = draw_weapon_table(
        draw,
        MARGIN,
        left_y,
        left_width,
        "Ranged Weapons",
        list(weapons.get("ranged_weapons", [])),
        "bs",
    )
    left_y = draw_weapon_table(
        draw,
        MARGIN,
        left_y,
        left_width,
        "Melee Weapons",
        list(weapons.get("melee_weapons", [])),
        "ws",
    )
    right_y = draw_sections(draw, card, MARGIN + left_width + GAP, right_y, right_width)
    y = max(left_y, right_y) + GAP

    keywords = ", ".join(str(item) for item in card.get("keywords", []))
    faction_keywords = ", ".join(str(item) for item in card.get("faction_keywords", []))
    y = draw_section_header(draw, MARGIN, y, content_width, "Keywords")
    y = draw_wrapped(draw, (MARGIN + 10, y + 8), f"KEYWORDS: {keywords}", FONT_SMALL, content_width - 20)
    y = draw_wrapped(draw, (MARGIN + 10, y + 8), f"FACTION KEYWORDS: {faction_keywords}", FONT_SMALL, content_width - 20)
    y += MARGIN

    return scratch.crop((0, 0, PAGE_WIDTH, min(y, scratch.height)))


def render_slug(json_path: Path, destination: Path) -> None:
    card = json.loads(json_path.read_text(encoding="utf-8"))
    image = render_card(card)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def main() -> int:
    args = parse_args()
    source_dir = Path(args.json_root) / args.output_slug
    output_dir = Path(args.out_root) / args.output_slug
    slug_filter = {slug.strip() for slug in args.card_slug if slug.strip()}
    paths = [
        path
        for path in sorted(source_dir.glob("*.json"))
        if path.name != "index.json" and (not slug_filter or path.stem in slug_filter)
    ]
    if not paths:
        raise SystemExit(f"No datasheet JSON files found in {source_dir}")

    for index, json_path in enumerate(paths, start=1):
        destination = output_dir / f"{json_path.stem}.png"
        render_slug(json_path, destination)
        print(f"[{index}/{len(paths)}] wrote {destination}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
