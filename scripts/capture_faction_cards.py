import argparse
import json
import re
import time
from pathlib import Path

from selenium.webdriver import Chrome as Firefox, ChromeOptions as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Wahapedia datasheet screenshots for a faction or filtered view."
    )
    parser.add_argument("--url", required=True, help="Faction landing page URL.")
    parser.add_argument(
        "--output-slug",
        required=True,
        help="Output folder and manifest prefix, e.g. aeldari or space-wolves.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Visible filter text to apply to matching selects. Repeat as needed.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing screenshots and manifests for the output slug before capture.",
    )
    parser.add_argument(
        "--fresh-browser-per-card",
        action="store_true",
        help="Use a new browser instance for each datasheet capture.",
    )
    return parser.parse_args()


def maybe_accept_consent(driver: Firefox) -> None:
    try:
        consent = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Consent']"))
        )
        consent.click()
        time.sleep(0.5)
    except Exception:
        return


def set_selects_by_text(driver: Firefox, visible_text: str) -> bool:
    changed = driver.execute_script(
        """
        const visibleText = arguments[0];
        const normalizedVisibleText = visibleText.trim().toLowerCase();
        const selects = Array.from(document.querySelectorAll("select"));
        const exactMatches = selects
            .map((select) => ({
                select,
                option: Array.from(select.options).find(
                    (candidate) => candidate.text.trim() === visibleText
                ),
            }))
            .filter((item) => item.option);
        let changed = false;

        for (const select of selects) {
            const options = Array.from(select.options);
            const option =
                exactMatches.length > 0
                    ? exactMatches.find((item) => item.select === select)?.option
                    : options.find(
                        (candidate) =>
                            candidate.text.trim().toLowerCase() === normalizedVisibleText
                    );
            if (!option || select.value === option.value) {
                continue;
            }

            select.value = option.value;
            select.dispatchEvent(new Event("input", { bubbles: true }));
            select.dispatchEvent(new Event("change", { bubbles: true }));
            changed = true;
        }

        return changed;
        """,
        visible_text,
    )
    if changed:
        time.sleep(0.75)
    return bool(changed)


def cleanup_page(driver: Firefox) -> None:
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    driver.execute_script(
        """
        if (document.activeElement) {
            document.activeElement.blur();
        }

        const style = document.createElement("style");
        style.innerHTML = `
            .tooltipster-base,
            .tooltip_templates,
            .noprint,
            .ds2col.ShowDatasheetFeatures,
            iframe,
            #btnArmyList,
            img.logo2,
            .ezoic-ad,
            .ezads-sticky-intradiv,
            .adsbygoogle,
            [id^='div-gpt-ad-'] {
                display: none !important;
            }
            * {
                animation: none !important;
                transition: none !important;
            }
        `;
        document.head.appendChild(style);

        document.querySelectorAll("[class*='tooltipster']").forEach((element) => {
            if (
                element.classList.contains("tooltipster-base") ||
                element.classList.contains("tooltip_templates")
            ) {
                element.remove();
            }
        });

        document.querySelectorAll("img[src*='logo2']").forEach((element) => {
            element.remove();
        });

        document.querySelectorAll(".altModels").forEach((element) => {
            const container = element.closest(".dsIconsRoundPad");
            if (container) {
                container.remove();
            } else {
                element.remove();
            }
        });

        document.querySelectorAll("[data-tooltip-content]").forEach((element) => {
            element.removeAttribute("data-tooltip-content");
            element.removeAttribute("data-tooltip-anchor");
        });

        document.querySelectorAll("body *").forEach((element) => {
            if (element.closest(".dsOuterFrame.datasheet")) {
                return;
            }

            const style = window.getComputedStyle(element);
            if (style.position === "fixed" || style.position === "sticky") {
                element.remove();
            }
        });

        document.querySelectorAll("button").forEach((button) => {
            if (button.textContent && button.textContent.trim() === "Consent") {
                const root = button.closest("div");
                if (root) {
                    root.remove();
                }
                button.remove();
            }
        });

        document.querySelectorAll("div").forEach((element) => {
            const text = (element.innerText || "").trim();
            if (text.startsWith("Privacy Preferences")) {
                element.remove();
            }
            if (
                text.includes("Do Not Sell My Information") ||
                text.includes("help improve your experience")
            ) {
                element.remove();
            }
        });

        document
            .querySelectorAll(
                "[id*='consent'], [class*='consent'], [id*='privacy'], [class*='privacy']"
            )
            .forEach((element) => {
                if (!element.closest(".dsOuterFrame.datasheet")) {
                    element.remove();
                }
            });

        const card = document.querySelector("div.dsOuterFrame.datasheet");
        if (card) {
            document.querySelectorAll("body *").forEach((element) => {
                if (
                    element === card ||
                    element.contains(card) ||
                    card.contains(element)
                ) {
                    return;
                }

                element.style.setProperty("visibility", "hidden", "important");
            });

            window.scrollTo(0, 0);
            card.scrollIntoView({ block: "start", inline: "nearest" });
        }
        """
    )
    time.sleep(0.3)


def normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def canonicalize_expected_slug(value: str) -> str:
    value = re.sub(r"-(?:ul|legendary)?-?\d+$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"-legendary-?$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"-ul$", "", value, flags=re.IGNORECASE)
    return normalize_slug(value)


def wait_for_expected_datasheet(
    driver: Firefox, wait: WebDriverWait, expected_slug: str
) -> None:
    normalized_expected = normalize_slug(expected_slug)
    canonical_expected = canonicalize_expected_slug(expected_slug)

    def matches_expected_target(current_driver: Firefox) -> bool:
        title = (current_driver.title or "").strip()
        normalized_title = normalize_slug(title)
        if normalized_title not in {normalized_expected, canonical_expected}:
            return False

        if not current_driver.find_elements(By.CSS_SELECTOR, "div.dsOuterFrame.datasheet"):
            return False

        body_text = current_driver.execute_script(
            "return (document.body && document.body.innerText) || '';"
        )
        return "This datasheet does not meet the selection criteria" not in body_text

    wait.until(matches_expected_target)


def wait_for_rendered_datasheet(
    driver: Firefox, wait: WebDriverWait, expected_slug: str
) -> None:
    normalized_expected = normalize_slug(expected_slug)
    canonical_expected = canonicalize_expected_slug(expected_slug)

    def is_fully_rendered(current_driver: Firefox) -> bool:
        if not current_driver.find_elements(By.CSS_SELECTOR, "div.dsOuterFrame.datasheet"):
            return False

        details = current_driver.execute_script(
            """
            const card = document.querySelector("div.dsOuterFrame.datasheet");
            const title = (document.title || "").trim();
            const text = (card?.innerText || "").trim();
            const stats = Array.from(card?.querySelectorAll("div, span") || [])
                .map((element) => (element.innerText || "").trim())
                .filter(Boolean)
                .slice(0, 40);
            return {
                title,
                textLength: text.length,
                placeholderCount: (text.match(/-{6,}/g) || []).length,
                fontsLoaded:
                    !document.fonts || document.fonts.status === "loaded",
                stats,
            };
            """
        )

        normalized_title = normalize_slug(details["title"])
        if normalized_title not in {normalized_expected, canonical_expected}:
            return False

        if not details["fontsLoaded"]:
            return False

        if details["textLength"] < 200:
            return False

        if details["placeholderCount"] > 8:
            return False

        visible_stats = [
            value
            for value in details["stats"]
            if value
            and value not in {"M", "T", "Sv", "W", "Ld", "OC"}
            and len(value) <= 4
        ]
        return len(visible_stats) >= 6

    wait.until(is_fully_rendered)


def wait_for_filtered_army_list(
    driver: Firefox,
    wait: WebDriverWait,
    baseline_title: str,
    baseline_count: int,
    requested_filters: list[str],
) -> None:
    normalized_filters = {item.strip().lower() for item in requested_filters if item.strip()}

    def has_refreshed(current_driver: Firefox) -> bool:
        current_title = (current_driver.title or "").strip()
        current_count = len(
            current_driver.find_elements(By.CSS_SELECTOR, "#tooltip_contentArmyList a")
        )
        selected_options = {
            option.text.strip().lower()
            for option in current_driver.find_elements(By.CSS_SELECTOR, "select option:checked")
            if option.text.strip()
        }

        missing_filters = normalized_filters.difference(selected_options)
        if missing_filters:
            for missing_filter in requested_filters:
                if missing_filter.strip().lower() in missing_filters:
                    set_selects_by_text(current_driver, missing_filter)
            return False

        if current_count <= 0:
            return False

        return current_title != baseline_title or current_count != baseline_count

    wait.until(has_refreshed)


def wait_for_filter_options(
    driver: Firefox, wait: WebDriverWait, requested_filters: list[str]
) -> None:
    normalized_filters = {item.strip().lower() for item in requested_filters if item.strip()}
    if not normalized_filters:
        return

    def filter_options_ready(current_driver: Firefox) -> bool:
        available_options = {
            option.text.strip().lower()
            for option in current_driver.find_elements(By.CSS_SELECTOR, "select option")
            if option.text.strip()
        }
        return normalized_filters.issubset(available_options)

    wait.until(filter_options_ready)


def fit_window_to_card(driver: Firefox) -> None:
    card = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.dsOuterFrame.datasheet"))
    )
    card_height = driver.execute_script(
        """
        const card = arguments[0];
        return Math.ceil(
            Math.max(card.scrollHeight, card.offsetHeight, card.getBoundingClientRect().height)
        );
        """,
        card,
    )
    target_height = max(2200, min(int(card_height) + 400, 10000))
    driver.set_window_size(1800, target_height)
    time.sleep(0.2)


def unique_links(driver: Firefox) -> list[dict[str, str]]:
    seen = set()
    items = []

    for element in driver.find_elements(By.CSS_SELECTOR, "#tooltip_contentArmyList a"):
        href = element.get_attribute("href")
        if href and href.startswith("https://wahapedia.ru/"):
            href = "http://wahapedia.ru/" + href.removeprefix("https://wahapedia.ru/")
        text = element.text.strip()
        if not href or href.endswith("datasheets.html") or href in seen:
            continue
        seen.add(href)
        items.append({"name": text, "href": href})

    return items


def clear_outputs(output_dir: Path, source_dir: Path, output_slug: str) -> None:
    for path in output_dir.glob("*.png"):
        path.unlink(missing_ok=True)

    for path in (
        source_dir / f"{output_slug}-links.json",
        source_dir / f"{output_slug}-failures.json",
    ):
        path.unlink(missing_ok=True)


def build_driver() -> tuple[Firefox, WebDriverWait]:
    options = FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--window-size=1800,2200")
    # `none` avoids long waits on Wahapedia assets, but we must verify the page title
    # before saving so we don't capture the previous datasheet during navigation.
    options.page_load_strategy = "none"

    driver = Firefox(options=options)
    driver.set_page_load_timeout(30)
    wait = WebDriverWait(driver, 60)
    return driver, wait


def capture_datasheet(
    driver: Firefox,
    wait: WebDriverWait,
    href: str,
    slug: str,
    filters: list[str],
    destination: Path,
) -> None:
    driver.get(href)
    maybe_accept_consent(driver)
    wait_for_filter_options(driver, wait, filters)
    for filter_text in filters:
        set_selects_by_text(driver, filter_text)
    wait_for_expected_datasheet(driver, wait, slug)
    wait_for_rendered_datasheet(driver, wait, slug)
    fit_window_to_card(driver)
    cleanup_page(driver)
    wait_for_rendered_datasheet(driver, wait, slug)
    fit_window_to_card(driver)
    cleanup_page(driver)
    wait_for_rendered_datasheet(driver, wait, slug)
    card = driver.find_element(By.CSS_SELECTOR, "div.dsOuterFrame.datasheet")
    card.screenshot(str(destination))


def main() -> int:
    args = parse_args()

    root = Path.cwd()
    output_dir = root / "out" / "factions" / args.output_slug
    source_dir = root / "out" / "source"
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    if args.clear:
        clear_outputs(output_dir, source_dir, args.output_slug)

    driver, wait = build_driver()

    try:
        print(f"Opening {args.url}", flush=True)
        driver.get(args.url)
        maybe_accept_consent(driver)
        wait_for_filter_options(driver, wait, args.filter)
        baseline_title = (driver.title or "").strip()
        baseline_count = len(driver.find_elements(By.CSS_SELECTOR, "#tooltip_contentArmyList a"))
        for filter_text in args.filter:
            set_selects_by_text(driver, filter_text)
        if args.filter:
            wait_for_filtered_army_list(
                driver, wait, baseline_title, baseline_count, args.filter
            )
        wait.until(
            lambda current_driver: len(
                current_driver.find_elements(By.CSS_SELECTOR, "#tooltip_contentArmyList a")
            )
            > 0
        )

        links = unique_links(driver)
        print(f"Found {len(links)} {args.output_slug} unit links", flush=True)

        with (source_dir / f"{args.output_slug}-links.json").open("w") as file:
            json.dump(links, file, indent=2)

        failures = []
        for index, item in enumerate(links, start=1):
            slug = item["href"].rstrip("/").split("/")[-1]
            destination = output_dir / f"{slug}.png"

            print(f"[{index}/{len(links)}] fetch {slug}", flush=True)
            try:
                if args.fresh_browser_per_card:
                    card_driver, card_wait = build_driver()
                    try:
                        capture_datasheet(
                            card_driver,
                            card_wait,
                            item["href"],
                            slug,
                            args.filter,
                            destination,
                        )
                    finally:
                        card_driver.quit()
                else:
                    capture_datasheet(
                        driver,
                        wait,
                        item["href"],
                        slug,
                        args.filter,
                        destination,
                    )
            except Exception as error:
                failures.append(
                    {"slug": slug, "href": item["href"], "error": str(error)}
                )
                print(f"  failed: {error}", flush=True)

        print(f"Completed with {len(failures)} failures", flush=True)
        with (source_dir / f"{args.output_slug}-failures.json").open("w") as file:
            json.dump(failures, file, indent=2)
        return 0 if not failures else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
