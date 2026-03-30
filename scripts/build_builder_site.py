import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from datasheet_schema import normalize_source_url
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from datasheet_schema import normalize_source_url


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_command(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def load_source_manifest(output_slug: str) -> list[dict[str, object]]:
    path = ROOT / "out" / "source" / f"{output_slug}-links.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Source manifest has unexpected shape: {path}")
        return data

    bundle_path = ROOT / "out" / "json" / output_slug / "index.json"
    if bundle_path.exists():
        cards = json.loads(bundle_path.read_text(encoding="utf-8"))
        if not isinstance(cards, list):
            raise ValueError(f"Bundle has unexpected shape: {bundle_path}")
        return [
            {"href": str(card.get("source", {}).get("url") or ""), "name": str(card.get("name") or "")}
            for card in cards
            if str(card.get("source", {}).get("url") or "").strip()
        ]

    raise FileNotFoundError(f"Source manifest not found: {path}")


def manifest_urls(output_slug: str) -> set[str]:
    return {
        normalize_source_url(str(item.get("href") or ""))
        for item in load_source_manifest(output_slug)
        if normalize_source_url(str(item.get("href") or ""))
    }


def discover_impacted_output_slugs(output_slugs: list[str]) -> list[str]:
    selected = sorted({slug.strip() for slug in output_slugs if slug.strip()})
    if not selected:
        return []

    selected_urls: set[str] = set()
    for slug in selected:
        selected_urls.update(manifest_urls(slug))

    impacted = set(selected)
    for path in sorted((ROOT / "out" / "source").glob("*-links.json")):
        output_slug = path.name.removesuffix("-links.json")
        urls = {
            normalize_source_url(str(item.get("href") or ""))
            for item in json.loads(path.read_text(encoding="utf-8"))
            if normalize_source_url(str(item.get("href") or ""))
        }
        if urls.intersection(selected_urls):
            impacted.add(output_slug)
    return sorted(impacted)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the builder-ready catalogs and optional example card HTML."
    )
    parser.add_argument(
        "--refresh-sitemap-manifest",
        action="append",
        default=[],
        help="Optional canonical faction slug to refresh from the Wahapedia sitemap before exporting.",
    )
    parser.add_argument(
        "--export-output-slug",
        action="append",
        default=[],
        help="Optional faction slug to refresh with export_datasheet_json.py before building catalogs.",
    )
    parser.add_argument(
        "--export-faction-rules",
        action="append",
        default=[],
        help="Optional faction slug to refresh with export_faction_rules.py before building catalogs.",
    )
    parser.add_argument(
        "--build-faction",
        action="append",
        default=[],
        help="Optional faction slug to limit builder catalog generation. Repeat as needed.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete out/builder before generating fresh catalogs.",
    )
    parser.add_argument(
        "--render-example-html",
        action="store_true",
        help="Regenerate per-card example HTML files for every exported JSON file before building catalogs.",
    )
    parser.add_argument(
        "--export-workers",
        type=int,
        default=4,
        help="Concurrent workers to use while refreshing exported datasheets.",
    )
    return parser.parse_args()


def render_all_examples() -> None:
    json_root = ROOT / "out" / "json"
    for json_path in sorted(json_root.glob("*/*.json")):
        if json_path.name == "index.json":
            continue
        run_command([PYTHON, "scripts/render_card_html.py", "--json", str(json_path)])


def main() -> None:
    args = parse_args()

    if args.refresh_sitemap_manifest:
        command = [PYTHON, "scripts/build_sitemap_manifests.py"]
        for slug in args.refresh_sitemap_manifest:
            command.extend(["--output-slug", slug])
        run_command(command)

    export_slugs = discover_impacted_output_slugs(args.export_output_slug)
    for slug in export_slugs:
        run_command(
            [
                PYTHON,
                "scripts/export_datasheet_json.py",
                "--output-slug",
                slug,
                "--workers",
                str(max(1, args.export_workers)),
            ]
        )

    run_command([PYTHON, "scripts/export_datasheet_json.py", "--sync-duplicates"])

    faction_rules_targets = sorted({
        *discover_impacted_output_slugs(args.export_faction_rules),
        *(args.build_faction or export_slugs),
    })
    if faction_rules_targets:
        command = [PYTHON, "scripts/export_faction_rules.py"]
        for slug in faction_rules_targets:
            command.extend(["--output-slug", slug])
        run_command(command)

    if args.render_example_html:
        render_all_examples()

    validation_command = [PYTHON, "scripts/validate_datasheet_exports.py", "--local-only", "--strict"]
    validation_targets = args.build_faction or export_slugs
    for faction in validation_targets:
        validation_command.extend(["--output-slug", faction])
    run_command(validation_command)

    command = [PYTHON, "scripts/build_builder_catalog.py"]
    if args.clean:
        command.append("--clean")
    for faction in args.build_faction:
        command.extend(["--faction", faction])
    run_command(command)


if __name__ == "__main__":
    main()
