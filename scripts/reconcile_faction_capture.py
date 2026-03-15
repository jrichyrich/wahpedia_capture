import argparse
import json
import shutil
from pathlib import Path


NON_DATASHEET_MARKDOWN = {
    "MIGRATION_SOP.md",
    "army_rules.md",
    "boarding_actions.md",
    "crusade_rules.md",
    "datasheets.md",
    "detachments.md",
    "faq.md",
    "introduction.md",
}

VARIANT_PARENT_MAP = {
    "iron_priest_on_thunderwolf": "iron_priest",
    "logan_grimnar_on_stormrider": "logan_grimnar",
    "wolf_guard_battle_leader_in_terminator_armour": "wolf_guard_battle_leader",
    "wolf_guard_battle_leader_on_thunderwolf": "wolf_guard_battle_leader",
    "wolf_guard_pack_leader_in_terminator_armour": "wolf_guard_pack_leader",
    "wolf_guard_pack_leader_with_jump_pack": "wolf_guard_pack_leader",
    "wulfen_with_storm_shields": "wulfen",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile faction capture outputs against manifests and markdown files."
    )
    parser.add_argument("--output-slug", required=True, help="Faction output slug, e.g. space-wolves")
    parser.add_argument(
        "--markdown-dir",
        help="Optional markdown directory to compare against datasheet files.",
    )
    parser.add_argument(
        "--flatten",
        action="store_true",
        help="Copy nested PNG captures into the faction root folder when missing there.",
    )
    return parser.parse_args()


def normalize_slug(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def manifest_slugs(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        normalize_slug(item["href"].rstrip("/").split("/")[-1])
        for item in data
        if item.get("href")
    }


def png_slugs(paths: list[Path]) -> dict[str, Path]:
    return {normalize_slug(path.stem): path for path in paths}


def is_datasheet_markdown(path: Path) -> bool:
    if path.name in NON_DATASHEET_MARKDOWN:
        return False
    if path.name.startswith("detachment_"):
        return False
    return path.suffix == ".md"


def classify_markdown_coverage(capture_slug: str, markdown_slugs: set[str]) -> tuple[str, str | None]:
    if capture_slug in markdown_slugs:
        return "direct", capture_slug

    if capture_slug in VARIANT_PARENT_MAP and VARIANT_PARENT_MAP[capture_slug] in markdown_slugs:
        return "variant", VARIANT_PARENT_MAP[capture_slug]

    if capture_slug.endswith("_1") and capture_slug[:-2] in markdown_slugs:
        return "variant", capture_slug[:-2]

    return "missing", None


def main() -> int:
    args = parse_args()

    root = Path.cwd()
    faction_dir = root / "out" / "factions" / args.output_slug
    manifest_path = root / "out" / "source" / f"{args.output_slug}-links.json"

    if not faction_dir.exists():
        raise SystemExit(f"Faction output folder not found: {faction_dir}")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    root_png_map = png_slugs(sorted(faction_dir.glob("*.png")))
    all_png_map = png_slugs(sorted(path for path in faction_dir.rglob("*.png") if path.is_file()))
    nested_png_map = {
        slug: path
        for slug, path in all_png_map.items()
        if path.parent != faction_dir
    }
    expected_slugs = manifest_slugs(manifest_path)

    nested_only = sorted((expected_slugs - set(root_png_map)) & set(nested_png_map))
    missing_everywhere = sorted(expected_slugs - set(all_png_map))

    print(f"Faction: {args.output_slug}")
    print(f"Manifest datasheets: {len(expected_slugs)}")
    print(f"Top-level PNGs: {len(root_png_map)}")
    print(f"Recursive PNGs: {len(all_png_map)}")
    print(f"Nested-only captures: {len(nested_only)}")
    print(f"Missing from all capture folders: {len(missing_everywhere)}")

    if nested_only:
        print("\nNested-only captures:")
        for slug in nested_only:
            print(f"- {slug} -> {nested_png_map[slug]}")

    if missing_everywhere:
        print("\nMissing from capture output:")
        for slug in missing_everywhere:
            print(f"- {slug}")

    if args.flatten and nested_only:
        copied = 0
        for slug in nested_only:
            source = nested_png_map[slug]
            destination = faction_dir / source.name
            if destination.exists():
                continue
            shutil.copy2(source, destination)
            copied += 1
        print(f"\nCopied {copied} nested captures into {faction_dir}")

    if args.markdown_dir:
        markdown_dir = Path(args.markdown_dir).expanduser().resolve()
        if not markdown_dir.exists():
            raise SystemExit(f"Markdown directory not found: {markdown_dir}")

        markdown_slugs = {
            normalize_slug(path.stem)
            for path in sorted(markdown_dir.glob("*.md"))
            if is_datasheet_markdown(path)
        }

        direct_matches = []
        variant_matches = []
        missing_markdown = []

        for slug in sorted(expected_slugs):
            coverage, target = classify_markdown_coverage(slug, markdown_slugs)
            if coverage == "direct":
                direct_matches.append(slug)
            elif coverage == "variant":
                variant_matches.append((slug, target))
            else:
                missing_markdown.append(slug)

        nested_direct_matches = [slug for slug in nested_only if slug in direct_matches]
        nested_variant_matches = [
            (slug, target) for slug, target in variant_matches if slug in set(nested_only)
        ]
        nested_missing_markdown = [slug for slug in nested_only if slug in missing_markdown]

        print(f"\nMarkdown directory: {markdown_dir}")
        print(f"Datasheet markdown files: {len(markdown_slugs)}")
        print(f"Direct markdown matches across all captured slugs: {len(direct_matches)}")
        print(f"Variant cards covered by parent markdown across all captured slugs: {len(variant_matches)}")
        print(f"Nested-only captures with direct markdown files: {len(nested_direct_matches)}")
        print(f"Nested-only captures merged into parent markdown files: {len(nested_variant_matches)}")
        print(f"Nested-only captures still missing markdown coverage: {len(nested_missing_markdown)}")

        if nested_direct_matches:
            print("\nNested-only captures already represented by direct markdown files:")
            for slug in nested_direct_matches:
                print(f"- {slug}.md")

        if nested_variant_matches:
            print("\nNested-only captures that should merge into an existing parent markdown file:")
            for slug, parent in nested_variant_matches:
                print(f"- {slug} -> {parent}.md")

        if nested_missing_markdown:
            print("\nNested-only captures with no markdown file or merge rule:")
            for slug in nested_missing_markdown:
                print(f"- {slug}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
