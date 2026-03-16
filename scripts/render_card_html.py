import argparse
import json
from html import escape
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a structured datasheet JSON file as a simple HTML card."
    )
    parser.add_argument("--json", required=True, help="Path to a single datasheet JSON file.")
    parser.add_argument(
        "--output",
        help="Optional HTML output path. Defaults next to the JSON file.",
    )
    return parser.parse_args()


def render_characteristics(card: dict[str, object]) -> str:
    boxes = []
    for label, value in card.get("characteristics", {}).items():
        if label == "Invulnerable Save":
            continue
        boxes.append(
            f"""
            <div class="stat-box">
              <div class="stat-label">{escape(label)}</div>
              <div class="stat-value">{escape(str(value))}</div>
            </div>
            """
        )

    invul = card.get("characteristics", {}).get("Invulnerable Save")
    invul_html = ""
    if invul:
        invul_html = f"""
        <div class="invul-row">
          <span class="invul-value">{escape(str(invul))}</span>
          <span class="invul-label">Invulnerable Save</span>
        </div>
        """

    return f"""
    <section class="banner">
      <div class="title-row">
        <h1>{escape(card['name'])}</h1>
        {f"<span class='base-size'>{escape(card['base_size'])}</span>" if card.get('base_size') else ""}
      </div>
      <div class="stats-grid">
        {''.join(boxes)}
      </div>
      {invul_html}
    </section>
    """


def render_weapon_table(title: str, rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""

    sample = rows[0]
    columns = [key for key in sample.keys() if key not in {"name", "abilities"}]
    header_html = "".join(
        f"<th>{escape(column.upper())}</th>" for column in columns
    )

    body = []
    for row in rows:
        ability_text = ""
        if row.get("abilities"):
            ability_text = f"<div class='weapon-abilities'>{escape(', '.join(row['abilities']))}</div>"
        body.append(
            f"""
            <tr>
              <td class="weapon-name">
                <div>{escape(str(row['name']))}</div>
                {ability_text}
              </td>
              {''.join(f"<td>{escape(str(row[column]))}</td>" for column in columns)}
            </tr>
            """
        )

    return f"""
    <section class="weapon-section">
      <h2>{escape(title.replace('_', ' '))}</h2>
      <table>
        <thead>
          <tr>
            <th>Weapon</th>
            {header_html}
          </tr>
        </thead>
        <tbody>
          {''.join(body)}
        </tbody>
      </table>
    </section>
    """


def render_section_entry(entry: dict[str, object]) -> str:
    entry_type = entry.get("type")
    if entry_type == "tagged_list":
        items = "".join(f"<li>{escape(str(item))}</li>" for item in entry.get("items", []))
        return f"""
        <div class="section-entry">
          <h4>{escape(str(entry['label']).title())}</h4>
          <ul>{items}</ul>
        </div>
        """

    if entry_type == "rule":
        return f"""
        <div class="section-entry">
          <h4>{escape(str(entry['name']))}</h4>
          <p>{escape(str(entry['text']))}</p>
        </div>
        """

    if entry_type == "list":
        items = "".join(f"<li>{escape(str(item))}</li>" for item in entry.get("items", []))
        return f"<div class='section-entry'><ul>{items}</ul></div>"

    if entry_type == "statement":
        return f"""
        <div class="section-entry">
          <h4>{escape(str(entry['label']))}</h4>
          <p>{escape(str(entry['text']))}</p>
        </div>
        """

    if entry_type == "points":
        rows = "".join(
            f"<tr><td>{escape(str(row['label']))}</td><td>{escape(str(row['points']))}</td></tr>"
            for row in entry.get("rows", [])
        )
        return f"""
        <div class="section-entry">
          <table class="points-table">
            <tbody>{rows}</tbody>
          </table>
        </div>
        """

    return f"<div class='section-entry'><p>{escape(str(entry.get('text', '')))}</p></div>"


def render_sections(card: dict[str, object]) -> str:
    sections = []
    for section in card.get("sections", []):
        entries = "".join(render_section_entry(entry) for entry in section.get("entries", []))
        sections.append(
            f"""
            <section class="detail-section">
              <h3>{escape(str(section['title']))}</h3>
              {entries}
            </section>
            """
        )
    return "".join(sections)


def render_keywords(card: dict[str, object]) -> str:
    keywords = ", ".join(card.get("keywords", []))
    faction_keywords = ", ".join(card.get("faction_keywords", []))
    return f"""
    <footer class="keywords">
      <div><strong>Keywords:</strong> {escape(keywords)}</div>
      <div><strong>Faction Keywords:</strong> {escape(faction_keywords)}</div>
    </footer>
    """


def render_html(card: dict[str, object]) -> str:
    weapons = card.get("weapons", {})
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(card['name'])}</title>
  <style>
    :root {{
      --ink: #111111;
      --panel: #f5f1e8;
      --line: #222222;
      --shade: #dfd7c8;
      --accent: #2d2d2d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background:
        radial-gradient(circle at top left, #f8f4eb, #e6ddcf 60%, #d7cebf);
      color: var(--ink);
      font-family: "Arial Narrow", Arial, sans-serif;
    }}
    .card {{
      max-width: 1100px;
      margin: 0 auto;
      background: var(--panel);
      border: 2px solid var(--line);
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.14);
    }}
    .title-row, .banner, .detail-grid, .keywords {{
      padding: 18px 24px;
    }}
    .title-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      border-bottom: 2px solid var(--line);
    }}
    h1, h2, h3, h4 {{
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    h1 {{ font-size: 2.35rem; }}
    h2, h3 {{ font-size: 1.1rem; }}
    h4 {{ font-size: 1rem; margin-bottom: 6px; }}
    .base-size {{
      font-size: 0.95rem;
      text-transform: uppercase;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .stat-box {{
      border-top: 2px solid var(--line);
      border-left: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 8px 10px 10px;
      background: #fbf9f4;
      text-align: center;
    }}
    .stat-label {{
      font-size: 0.8rem;
      text-transform: uppercase;
    }}
    .stat-value {{
      font-size: 2rem;
      font-weight: 700;
      line-height: 1;
    }}
    .invul-row {{
      margin-top: 14px;
      display: inline-flex;
      border: 1px solid var(--line);
      align-items: center;
      background: #fbf9f4;
    }}
    .invul-value {{
      padding: 8px 12px;
      font-size: 1.35rem;
      font-weight: 700;
      border-right: 1px solid var(--line);
    }}
    .invul-label {{
      padding: 8px 12px;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 0;
      border-top: 1px solid var(--line);
    }}
    .left-pane {{
      border-right: 1px solid var(--line);
    }}
    .weapon-section h2,
    .detail-section h3 {{
      padding: 10px 20px;
      background: #ece6da;
      border-bottom: 1px solid var(--line);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    thead th {{
      background: #f0ebe1;
      border-bottom: 1px solid var(--line);
      font-size: 0.85rem;
      text-transform: uppercase;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(17, 17, 17, 0.16);
      text-align: left;
      vertical-align: top;
    }}
    .weapon-name {{
      width: 45%;
      font-weight: 700;
    }}
    .weapon-abilities {{
      margin-top: 4px;
      font-size: 0.8rem;
      text-transform: uppercase;
    }}
    .section-entry {{
      padding: 14px 20px;
      border-bottom: 1px solid rgba(17, 17, 17, 0.12);
    }}
    .section-entry p,
    .section-entry ul {{
      margin: 0;
      line-height: 1.45;
    }}
    .section-entry ul {{
      padding-left: 18px;
    }}
    .points-table td:last-child {{
      text-align: right;
      font-weight: 700;
    }}
    .keywords {{
      display: grid;
      gap: 8px;
      border-top: 2px solid var(--line);
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    @media (max-width: 820px) {{
      body {{ padding: 12px; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .left-pane {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .title-row {{ flex-direction: column; gap: 8px; }}
    }}
  </style>
</head>
<body>
  <main class="card">
    {render_characteristics(card)}
    <section class="detail-grid">
      <div class="left-pane">
        {render_weapon_table("Ranged Weapons", weapons.get("ranged_weapons", []))}
        {render_weapon_table("Melee Weapons", weapons.get("melee_weapons", []))}
      </div>
      <div class="right-pane">
        {render_sections(card)}
      </div>
    </section>
    {render_keywords(card)}
  </main>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    json_path = Path(args.json)
    output_path = Path(args.output) if args.output else json_path.with_suffix(".html")

    card = json.loads(json_path.read_text(encoding="utf-8"))
    output_path.write_text(render_html(card), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
