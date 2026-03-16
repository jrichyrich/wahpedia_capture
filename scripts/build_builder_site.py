import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_command(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the builder-ready catalogs and optional example card HTML."
    )
    parser.add_argument(
        "--export-output-slug",
        action="append",
        default=[],
        help="Optional faction slug to refresh with export_datasheet_json.py before building catalogs.",
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
    return parser.parse_args()


def render_all_examples() -> None:
    json_root = ROOT / "out" / "json"
    for json_path in sorted(json_root.glob("*/*.json")):
        if json_path.name == "index.json":
            continue
        run_command([PYTHON, "scripts/render_card_html.py", "--json", str(json_path)])


def main() -> None:
    args = parse_args()

    for slug in args.export_output_slug:
        run_command([PYTHON, "scripts/export_datasheet_json.py", "--output-slug", slug])

    if args.render_example_html:
        render_all_examples()

    command = [PYTHON, "scripts/build_builder_catalog.py"]
    if args.clean:
        command.append("--clean")
    for faction in args.build_faction:
        command.extend(["--faction", faction])
    run_command(command)


if __name__ == "__main__":
    main()
