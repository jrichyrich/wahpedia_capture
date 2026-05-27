import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests
import urllib3
from bs4 import BeautifulSoup

try:
    from datasheet_schema import normalize_source_url
    from wahapedia_fetch import BrowserFetchSession, fetch_html as fetch_wahapedia_html, reader_fetch_markdown
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from datasheet_schema import normalize_source_url
    from wahapedia_fetch import BrowserFetchSession, fetch_html as fetch_wahapedia_html, reader_fetch_markdown


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
    parser.add_argument(
        "--fetch-backend",
        choices=("auto", "requests", "browser"),
        default="auto",
        help="Fetch backend to use when direct requests fail.",
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


def datasheets_url_for_slug(faction_slug: str) -> str:
    return f"http://wahapedia.ru/wh40k10ed/factions/{faction_slug}/datasheets.html"


def manifest_from_datasheets_page(faction_slug: str, html_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    army_list = soup.select_one("#tooltip_contentArmyList")
    if not army_list:
        return []

    urls = []
    for link in army_list.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href or href.endswith("datasheets.html"):
            continue
        if href.startswith("/"):
            href = f"http://wahapedia.ru{href}"
        normalized = normalize_source_url(href)
        if not normalized:
            continue
        if canonical_faction_slug(normalized) != faction_slug:
            continue
        urls.append(normalized)
    return manifest_entries_for_urls(urls)


def slug_from_title(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")


def manifest_from_reader_markdown(faction_slug: str, markdown_text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in markdown_text.splitlines()]
    collecting = False
    names: list[str] = []
    section_names = {"Characters", "Battleline", "Other"}
    stop_markers = {"CHARACTERS", "BATTLELINE", "OTHER"}

    for line in lines:
        if line == "Contents":
            collecting = True
            continue
        if not collecting:
            continue
        if line in stop_markers:
            break
        if not line or line in section_names:
            continue
        if line.startswith("Title:") or line.startswith("URL Source:"):
            continue
        names.append(line)

    urls = [
        normalize_source_url(f"http://wahapedia.ru/wh40k10ed/factions/{faction_slug}/{slug_from_title(name)}")
        for name in names
        if slug_from_title(name)
    ]
    return manifest_entries_for_urls(urls)


def fallback_manifests_from_datasheets_pages(
    requested_slugs: list[str],
    *,
    fetch_backend: str,
) -> dict[str, list[dict[str, str]]]:
    cleaned_slugs = [slug.strip() for slug in requested_slugs if slug.strip()]
    if not cleaned_slugs:
        raise SystemExit("Browser fallback requires one or more --output-slug values.")

    manifests: dict[str, list[dict[str, str]]] = {}
    browser_session: BrowserFetchSession | None = None
    try:
        for slug in cleaned_slugs:
            datasheets_url = datasheets_url_for_slug(slug)
            entries = []
            try:
                if browser_session is None:
                    browser_session = BrowserFetchSession()
                _, html_text = fetch_wahapedia_html(
                    datasheets_url,
                    backend="browser" if fetch_backend == "browser" else "auto",
                    browser_session=browser_session,
                    wait_css="#tooltip_contentArmyList a",
                )
                entries = manifest_from_datasheets_page(slug, html_text)
            except Exception:
                _, markdown_text = reader_fetch_markdown(datasheets_url)
                entries = manifest_from_reader_markdown(slug, markdown_text)
            if not entries:
                raise SystemExit(f"No datasheet links discovered for {slug}.")
            manifests[slug] = entries
    finally:
        if browser_session is not None:
            close = getattr(browser_session, "close", None)
            if close:
                close()
    return manifests


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
    try:
        if args.fetch_backend == "browser":
            raise RuntimeError("Browser backend requested for sitemap manifest generation.")
        manifests = manifests_from_sitemap(fetch_sitemap_xml(args.sitemap_url))
    except Exception:
        if args.fetch_backend == "requests":
            raise
        manifests = fallback_manifests_from_datasheets_pages(
            args.output_slug,
            fetch_backend=args.fetch_backend,
        )
    selected = selected_manifests(manifests, args.output_slug)
    if not selected:
        raise SystemExit("No canonical faction manifests were discovered in the sitemap.")

    written_paths = write_manifests(selected, Path(args.source_dir))
    for path in written_paths:
        print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
