import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlsplit, urlunsplit

import requests
import urllib3


FetchBackend = Literal["auto", "requests", "browser"]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WahapediaFetchError(RuntimeError):
    pass


def reader_proxy_url(url: str) -> str:
    return f"https://r.jina.ai/http://{url}"


def reader_fetch_markdown(
    url: str,
    *,
    timeout: int = 45,
    attempts: int = 3,
) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            proxy_url = reader_proxy_url(url)
            try:
                response = requests.get(
                    proxy_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
            except requests.exceptions.SSLError:
                response = requests.get(
                    proxy_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                    verify=False,
                )
            response.raise_for_status()
            if not response.text.strip():
                raise WahapediaFetchError(f"Empty reader response from {proxy_url}")
            return url, response.text
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    escaped = quote(url, safe=":/?&=#%")
    raise WahapediaFetchError(f"Could not fetch reader markdown for {escaped}: {last_error}") from last_error


def alternate_scheme_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme == "https":
        return urlunsplit(("http", parts.netloc, parts.path, parts.query, parts.fragment))
    if parts.scheme == "http":
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    return None


def url_candidates(url: str, include_scheme_fallback: bool = True) -> list[str]:
    candidates = [url]
    alternate = alternate_scheme_url(url) if include_scheme_fallback else None
    if alternate and alternate not in candidates:
        candidates.append(alternate)
    return candidates


def requests_fetch_html(
    url: str,
    *,
    timeout: int = 30,
    attempts: int = 3,
    include_scheme_fallback: bool = True,
) -> tuple[str, str]:
    last_error: Exception | None = None
    for candidate in url_candidates(url, include_scheme_fallback=include_scheme_fallback):
        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(
                    candidate,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
                response.raise_for_status()
                if not response.text.strip():
                    raise WahapediaFetchError(f"Empty response from {candidate}")
                return response.url, response.text
            except requests.exceptions.SSLError as error:
                last_error = error
                try:
                    response = requests.get(
                        candidate,
                        headers={"User-Agent": USER_AGENT},
                        timeout=timeout,
                        verify=False,
                    )
                    response.raise_for_status()
                    if not response.text.strip():
                        raise WahapediaFetchError(f"Empty response from {candidate}")
                    return response.url, response.text
                except Exception as verify_error:  # pragma: no cover - integration-only network path
                    last_error = verify_error
            except Exception as error:
                last_error = error
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    raise WahapediaFetchError(f"Could not fetch {url}: {last_error}") from last_error


@dataclass
class BrowserFetchSession(AbstractContextManager):
    driver: object | None = None

    def __enter__(self) -> "BrowserFetchSession":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def open(self) -> None:
        if self.driver is not None:
            return
        from selenium.webdriver import Firefox, FirefoxOptions

        options = FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--width=1600")
        options.add_argument("--height=2200")
        self.driver = Firefox(options=options)

    def close(self) -> None:
        if self.driver is None:
            return
        self.driver.quit()
        self.driver = None

    def fetch_html(
        self,
        url: str,
        *,
        wait_css: str | None = None,
        wait_text: str | None = None,
        timeout: int = 60,
        include_scheme_fallback: bool = True,
    ) -> tuple[str, str]:
        self.open()
        assert self.driver is not None

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        last_error: Exception | None = None
        for candidate in url_candidates(url, include_scheme_fallback=include_scheme_fallback):
            for attempt in range(1, 3):
                try:
                    self.driver.get(candidate)
                    wait = WebDriverWait(self.driver, timeout)
                    if wait_css:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_css)))
                    if wait_text:
                        wait.until(lambda driver: wait_text in (driver.page_source or ""))
                    html = str(self.driver.page_source or "")
                    if not html.strip():
                        raise WahapediaFetchError(f"Empty browser response from {candidate}")
                    return str(self.driver.current_url), html
                except Exception as error:
                    last_error = error
                    if attempt < 2:
                        time.sleep(1.5 * attempt)
        raise WahapediaFetchError(f"Browser could not fetch {url}: {last_error}") from last_error


def fetch_html(
    url: str,
    *,
    backend: FetchBackend = "auto",
    browser_session: BrowserFetchSession | None = None,
    wait_css: str | None = None,
    wait_text: str | None = None,
    include_scheme_fallback: bool = True,
) -> tuple[str, str]:
    if backend not in {"auto", "requests", "browser"}:
        raise ValueError(f"Unknown fetch backend: {backend}")

    if backend in {"auto", "requests"}:
        try:
            return requests_fetch_html(url, include_scheme_fallback=include_scheme_fallback)
        except Exception:
            if backend == "requests":
                raise

    session = browser_session or BrowserFetchSession()
    should_close = browser_session is None
    try:
        return session.fetch_html(
            url,
            wait_css=wait_css,
            wait_text=wait_text,
            include_scheme_fallback=include_scheme_fallback,
        )
    finally:
        if should_close:
            session.close()
