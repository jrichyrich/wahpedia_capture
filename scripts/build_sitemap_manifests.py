import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests
import urllib3

try:
    from datasheet_schema import normalize_source_url
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from datasheet_schema import normalize_source_url


DEFAULT_SITEMAP_URL = "https://wahapedia.ru/wh40k10ed/SiteMap.xml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical Wahapedia source manifests from the live sitemap."
    )
    parser.add_argument(
        "--output-slug",
        action="append",
        default=[],
        help="Canonical Wahapedia faction slug to write. Repeat as needed.",
    )
    parser.add_argument(
        "--source-dir",
        default="out/source",
        help="Directory where <slug>-links.json files will be written.",
    )
    parser.add_argument(
        "--sitemap-url",
        default=DEFAULT_SITEMAP_URL,
        help="Override the sitemap URL for testing or alternate sources.",
    )
    return parser.parse_args()


def fetch_sitemap_xml(url: str) -> str:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError:
        # Wahapedia intermittently serves a certificate chain Python does not trust.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, timeout=30, verify=False)
        response.raise_for_status()
        return response.text


def sitemap_urls(xml_text: str) -> list[str]:
    root = ET.fromstring((xml_text or "").lstrip("\ufeff"))
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [
        (node.text or "").strip()
        for node in root.findall("sm:url/sm:loc", namespace)
        if (node.text or "").strip()
    ]


def canonical_faction_slug(url: str) -> str | None:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if len(parts) != 4:
        return None
    if parts[0] != "wh40k10ed" or parts[1] != "factions":
        return None
    if not parts[2].strip() or not parts[3].strip():
        return None
    # Wahapedia also exposes lowercase faction subsection pages such as
    # /factions/aeldari/asuryani. Datasheet slugs are title-cased and may
    # include digits or non-ASCII uppercase characters, so reject all-lowercase
    # terminal path segments here.
    if not any(character.isupper() for character in parts[3]):
        return None
    return parts[2]


def manifest_entries_for_urls(urls: list[str]) -> list[dict[str, str]]:
    normalized_urls = sorted({normalize_source_url(url) for url in urls if normalize_source_url(url)})
    return [{"name": "", "href": url} for url in normalized_urls]


def manifests_from_sitemap(xml_text: str) -> dict[str, list[dict[str, str]]]:
    grouped_urls: dict[str, list[str]] = {}
    for url in sitemap_urls(xml_text):
        faction_slug = canonical_faction_slug(url)
        if not faction_slug:
            continue
        grouped_urls.setdefault(faction_slug, []).append(url)
    return {
        faction_slug: manifest_entries_for_urls(urls)
        for faction_slug, urls in sorted(grouped_urls.items())
    }


def selected_manifests(
    manifests: dict[str, list[dict[str, str]]],
    requested_slugs: list[str],
) -> dict[str, list[dict[str, str]]]:
    cleaned_slugs = [slug.strip() for slug in requested_slugs if slug.strip()]
    if not cleaned_slugs:
        return manifests

    missing = [slug for slug in cleaned_slugs if slug not in manifests]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise SystemExit(
            "Non-canonical or unknown output slug(s): "
            f"{missing_list}. Use the browser-based manifest generation path for filtered subsets."
        )

    return {slug: manifests[slug] for slug in cleaned_slugs}


def write_manifests(
    manifests: dict[str, list[dict[str, str]]],
    source_dir: Path,
) -> list[Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    written_paths = []
    for faction_slug, entries in manifests.items():
        path = source_dir / f"{faction_slug}-links.json"
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        written_paths.append(path)
    return written_paths


def main() -> int:
    args = parse_args()
    manifests = manifests_from_sitemap(fetch_sitemap_xml(args.sitemap_url))
    selected = selected_manifests(manifests, args.output_slug)
    if not selected:
        raise SystemExit("No canonical faction manifests were discovered in the sitemap.")

    written_paths = write_manifests(selected, Path(args.source_dir))
    for path in written_paths:
        print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
