import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

try:
    from wahapedia_fetch import USER_AGENT, reader_proxy_url
except ModuleNotFoundError:  # pragma: no cover - importlib/unit test path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wahapedia_fetch import USER_AGENT, reader_proxy_url


DATASHEET_SELECTOR = "div.dsOuterFrame.datasheet"


class JinaTemporaryBlockError(RuntimeError):
    def __init__(self, message: str, cooldown_until: datetime | None = None):
        super().__init__(message)
        self.cooldown_until = cooldown_until


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture live Wahapedia DOM screenshots through Jina Reader."
    )
    parser.add_argument("--output-slug", required=True)
    parser.add_argument("--source-root", default="out/source")
    parser.add_argument("--out-root", default="out/factions")
    parser.add_argument(
        "--card-slug",
        action="append",
        default=[],
        help="Limit capture to one or more datasheet slugs. Repeat as needed.",
    )
    parser.add_argument(
        "--raw-dir",
        help="Optional folder for uncropped full-page screenshots.",
    )
    parser.add_argument(
        "--mode",
        choices=["pageshot", "screenshot"],
        default="pageshot",
        help="Use pageshot for full-page capture plus crop, or screenshot for a viewport shot.",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        help="Keep the Jina screenshot exactly as returned.",
    )
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay", type=float, default=90.0)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not request screenshots that already exist in the output folder.",
    )
    parser.add_argument(
        "--loop-until-complete",
        action="store_true",
        help="Keep retrying missing cards, sleeping through Jina cooldowns until all are captured.",
    )
    parser.add_argument(
        "--next-missing-once",
        action="store_true",
        help="Capture only the first manifest card missing from the raw DOM cache, then exit.",
    )
    parser.add_argument(
        "--cooldown-buffer-seconds",
        type=int,
        default=300,
        help="Extra seconds to wait after a parsed Jina cooldown before retrying.",
    )
    parser.add_argument(
        "--docs-source-cards-root",
        default="docs/builder/data/source-cards",
        help="Builder source-card root to update after successful captures.",
    )
    return parser.parse_args()


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def load_manifest(path: Path, requested_slugs: list[str]) -> list[dict[str, str]]:
    links = json.loads(path.read_text(encoding="utf-8"))
    if requested_slugs:
        requested = set(requested_slugs)
        links = [item for item in links if slug_from_url(str(item.get("href") or "")) in requested]
    return links


def jina_headers(mode: str, timeout: int) -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "X-Respond-With": mode,
        "X-Engine": "browser",
        "X-Wait-For-Selector": DATASHEET_SELECTOR,
        "X-Target-Selector": DATASHEET_SELECTOR,
        "X-Timeout": str(timeout),
        "X-Remove-Overlay": "true",
    }


def cooldown_from_jina_error(text: str) -> datetime | None:
    match = re.search(r"blocked until (.+?) due to", text)
    if not match:
        return None
    raw_value = re.sub(r"\s*\(.+?\)\s*$", "", match.group(1)).strip()
    for fmt in ("%a %b %d %Y %H:%M:%S GMT%z", "%a %b %d %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(raw_value, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def fetch_jina_screenshot(
    url: str,
    *,
    mode: str,
    timeout: int,
    attempts: int,
) -> bytes:
    proxy_url = reader_proxy_url(url)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            try:
                response = requests.get(
                    proxy_url,
                    headers=jina_headers(mode, timeout),
                    timeout=timeout,
                )
            except requests.exceptions.SSLError:
                response = requests.get(
                    proxy_url,
                    headers=jina_headers(mode, timeout),
                    timeout=timeout,
                    verify=False,
                )
            if response.status_code == 451:
                raise JinaTemporaryBlockError(
                    f"Jina temporarily blocked this domain: {response.text}",
                    cooldown_until=cooldown_from_jina_error(response.text),
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image/png" not in content_type:
                raise RuntimeError(f"Expected PNG response from Jina, got {content_type}: {response.text[:300]}")
            return response.content
        except JinaTemporaryBlockError:
            raise
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Could not capture {url}: {last_error}") from last_error


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum(abs(left[index] - right[index]) for index in range(3))


def row_score(
    image: Image.Image,
    y: int,
    *,
    x_start: int,
    x_end: int,
    background: tuple[int, int, int],
) -> tuple[int, int]:
    changed = 0
    strong = 0
    for x in range(x_start, x_end, 2):
        pixel = image.getpixel((x, y))
        if color_distance(pixel, background) > 25:
            changed += 1
        if (max(pixel) - min(pixel) > 35 and sum(pixel) < 700) or sum(pixel) < 160:
            strong += 1
    return changed, strong


def is_teal_header_pixel(pixel: tuple[int, int, int]) -> bool:
    return pixel[0] < 25 and 45 <= pixel[1] <= 110 and 70 <= pixel[2] <= 145


def is_feature_action_pixel(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    if red < 25 and 45 <= green <= 130 and 70 <= blue <= 160:
        return True
    if red < 35 and 90 <= green <= 155 and 120 <= blue <= 185:
        return True
    if red < 40 and 95 <= green <= 160 and 70 <= blue <= 145:
        return True
    if red >= 150 and green < 45 and blue < 45:
        return True
    return False


def sampled_ratio(
    image: Image.Image,
    y: int,
    x_start: int,
    x_end: int,
    predicate,
) -> float:
    samples = 0
    matches = 0
    for x in range(x_start, x_end, 4):
        samples += 1
        if predicate(image.getpixel((x, y))):
            matches += 1
    return matches / max(1, samples)


def find_feature_section_top(
    image: Image.Image,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> int | None:
    card_width = right - left
    left_column_start = left + 20
    left_column_end = left + int(card_width * 0.58)
    search_start = top + 450

    for y in range(search_start, max(search_start, bottom - 80)):
        sustained_header_rows = sum(
            1
            for offset in range(0, 14, 2)
            if sampled_ratio(
                image,
                y + offset,
                left_column_start,
                left_column_end,
                is_teal_header_pixel,
            )
            > 0.7
        )
        if sustained_header_rows < 5:
            continue

        action_rows = sum(
            1
            for future_y in range(y + 35, min(y + 220, bottom), 5)
            if sampled_ratio(
                image,
                future_y,
                left_column_start,
                left_column_end,
                is_feature_action_pixel,
            )
            > 0.55
        )
        if action_rows >= 8:
            return y

    return None


def find_datasheet_crop_box(image: Image.Image) -> tuple[int, int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    background = rgb.getpixel((0, 0))
    x_start = max(0, int(width * 0.05))
    x_end = min(width, int(width * 0.95))
    sample_count = max(1, (x_end - x_start) // 2)

    top = None
    for y in range(max(140, int(height * 0.02)), min(height, 500)):
        _, strong = row_score(rgb, y, x_start=x_start, x_end=x_end, background=background)
        if strong > sample_count * 0.65:
            top = y
            break

    if top is None:
        return (0, 0, width, height)

    rows_for_x = range(top, min(height, top + 120))
    xs: list[int] = []
    for y in rows_for_x:
        for x in range(width):
            if color_distance(rgb.getpixel((x, y)), background) > 25:
                xs.append(x)
    if not xs:
        left, right = 0, width
    else:
        left = max(0, min(xs) - 2)
        right = min(width, max(xs) + 3)

    strong_rows: list[int] = []
    for y in range(top, height):
        _, strong = row_score(rgb, y, x_start=x_start, x_end=x_end, background=background)
        if strong > sample_count * 0.05:
            strong_rows.append(y)

    bottom = height
    previous = strong_rows[0] if strong_rows else top
    for y in strong_rows[1:]:
        gap = y - previous
        if gap > 300 or (previous > top + 1200 and gap > 50):
            bottom = previous + 8
            break
        previous = y
    else:
        bottom = previous + 8

    feature_top = find_feature_section_top(
        rgb,
        left=left,
        top=top,
        right=right,
        bottom=min(height, bottom),
    )
    if feature_top is not None:
        bottom = min(bottom, feature_top)

    return (left, top, right, min(height, bottom))


def crop_datasheet_screenshot(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGB")
    if image.width <= 1100:
        feature_top = find_feature_section_top(
            image,
            left=0,
            top=0,
            right=image.width,
            bottom=image.height,
        )
        crop_box = (0, 0, image.width, feature_top or image.height)
    else:
        crop_box = find_datasheet_crop_box(image)
    cropped = image.crop(crop_box)
    cropped.save(destination)


def captured_slugs(raw_dir: Path | None, output_dir: Path) -> set[str]:
    source_dir = raw_dir or output_dir
    return {path.stem for path in source_dir.glob("*.png")}


def copy_to_docs_source_cards(destination: Path, docs_root: Path, output_slug: str) -> None:
    target_dir = docs_root / output_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, target_dir / destination.name)


def capture_all(args: argparse.Namespace) -> int:
    root = Path.cwd()
    manifest_path = root / args.source_root / f"{args.output_slug}-links.json"
    output_dir = root / args.out_root / args.output_slug
    raw_dir = (root / args.raw_dir) if args.raw_dir else None
    output_dir.mkdir(parents=True, exist_ok=True)
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)

    links = load_manifest(manifest_path, args.card_slug)
    failures: list[dict[str, str]] = []
    for index, item in enumerate(links, start=1):
        href = str(item.get("href") or "")
        slug = slug_from_url(href)
        destination = output_dir / f"{slug}.png"
        raw_destination = (raw_dir / f"{slug}.png") if raw_dir else destination
        skip_marker = raw_destination if raw_dir else destination
        if args.skip_existing and destination.exists() and skip_marker.exists():
            print(f"[{index}/{len(links)}] skip {slug}", flush=True)
            continue
        print(f"[{index}/{len(links)}] capture {slug}", flush=True)
        try:
            raw_destination.write_bytes(
                fetch_jina_screenshot(
                    href,
                    mode=args.mode,
                    timeout=args.timeout,
                    attempts=args.attempts,
                )
            )
            if not args.no_crop and args.mode == "pageshot":
                crop_datasheet_screenshot(raw_destination, destination)
        except Exception as error:
            failures.append({"slug": slug, "href": href, "error": str(error)})
            print(f"  failed: {error}", flush=True)
            if isinstance(error, JinaTemporaryBlockError):
                print("Temporary Jina block detected; stopping to avoid extending the cooldown.", flush=True)
                break
        if index < len(links):
            time.sleep(args.delay)

    failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
    failures_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(f"Completed with {len(failures)} failures", flush=True)
    return 0 if not failures else 1


def capture_until_complete(args: argparse.Namespace) -> int:
    root = Path.cwd()
    manifest_path = root / args.source_root / f"{args.output_slug}-links.json"
    output_dir = root / args.out_root / args.output_slug
    raw_dir = (root / args.raw_dir) if args.raw_dir else output_dir
    docs_root = root / args.docs_source_cards_root
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    links = load_manifest(manifest_path, args.card_slug)

    while True:
        done = captured_slugs(raw_dir, output_dir)
        remaining = [item for item in links if slug_from_url(str(item.get("href") or "")) not in done]
        if not remaining:
            failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
            failures_path.write_text("[]", encoding="utf-8")
            print(f"All {len(links)} requested cards captured", flush=True)
            return 0

        item = remaining[0]
        href = str(item.get("href") or "")
        slug = slug_from_url(href)
        destination = output_dir / f"{slug}.png"
        raw_destination = raw_dir / f"{slug}.png"
        print(f"[{len(done) + 1}/{len(links)}] capture {slug}", flush=True)

        try:
            raw_destination.write_bytes(
                fetch_jina_screenshot(
                    href,
                    mode=args.mode,
                    timeout=args.timeout,
                    attempts=args.attempts,
                )
            )
            if not args.no_crop and args.mode == "pageshot":
                crop_datasheet_screenshot(raw_destination, destination)
            copy_to_docs_source_cards(destination, docs_root, args.output_slug)
            failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
            failures_path.write_text("[]", encoding="utf-8")
        except JinaTemporaryBlockError as error:
            failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
            failures_path.write_text(
                json.dumps([{"slug": slug, "href": href, "error": str(error)}], indent=2),
                encoding="utf-8",
            )
            if error.cooldown_until is None:
                print(f"Temporary Jina block without parsed cooldown: {error}", flush=True)
                return 1
            wait_seconds = max(
                0,
                int((error.cooldown_until - datetime.now(timezone.utc)).total_seconds())
                + args.cooldown_buffer_seconds,
            )
            print(
                f"Temporary Jina block until {error.cooldown_until.isoformat()}; "
                f"sleeping {wait_seconds} seconds",
                flush=True,
            )
            time.sleep(wait_seconds)
        except Exception as error:
            failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
            failures_path.write_text(
                json.dumps([{"slug": slug, "href": href, "error": str(error)}], indent=2),
                encoding="utf-8",
            )
            print(f"  failed: {error}", flush=True)
            print(f"Sleeping {args.delay} seconds before retrying {slug}", flush=True)
            time.sleep(args.delay)


def capture_next_missing_once(args: argparse.Namespace) -> int:
    root = Path.cwd()
    manifest_path = root / args.source_root / f"{args.output_slug}-links.json"
    output_dir = root / args.out_root / args.output_slug
    raw_dir = (root / args.raw_dir) if args.raw_dir else output_dir
    docs_root = root / args.docs_source_cards_root
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    links = load_manifest(manifest_path, args.card_slug)
    done = captured_slugs(raw_dir, output_dir)
    remaining = [item for item in links if slug_from_url(str(item.get("href") or "")) not in done]
    failures_path = root / args.source_root / f"{args.output_slug}-dom-screenshot-failures.json"
    if not remaining:
        failures_path.write_text("[]", encoding="utf-8")
        print(f"All {len(links)} requested cards captured", flush=True)
        return 0

    item = remaining[0]
    href = str(item.get("href") or "")
    slug = slug_from_url(href)
    destination = output_dir / f"{slug}.png"
    raw_destination = raw_dir / f"{slug}.png"
    print(f"capture {slug}", flush=True)

    try:
        raw_destination.write_bytes(
            fetch_jina_screenshot(
                href,
                mode=args.mode,
                timeout=args.timeout,
                attempts=args.attempts,
            )
        )
        if not args.no_crop and args.mode == "pageshot":
            crop_datasheet_screenshot(raw_destination, destination)
        copy_to_docs_source_cards(destination, docs_root, args.output_slug)
        failures_path.write_text("[]", encoding="utf-8")
        print(f"captured {slug}", flush=True)
        return 0
    except JinaTemporaryBlockError as error:
        failures_path.write_text(
            json.dumps([{"slug": slug, "href": href, "error": str(error)}], indent=2),
            encoding="utf-8",
        )
        if error.cooldown_until:
            print(f"Temporary Jina block until {error.cooldown_until.isoformat()}", flush=True)
        else:
            print(f"Temporary Jina block: {error}", flush=True)
        return 1
    except Exception as error:
        failures_path.write_text(
            json.dumps([{"slug": slug, "href": href, "error": str(error)}], indent=2),
            encoding="utf-8",
        )
        print(f"failed {slug}: {error}", flush=True)
        return 1


def main() -> int:
    args = parse_args()
    if args.next_missing_once:
        return capture_next_missing_once(args)
    if args.loop_until_complete:
        return capture_until_complete(args)
    return capture_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
