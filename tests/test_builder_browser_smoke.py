import functools
import http.server
import socketserver
import threading
import unittest
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:  # pragma: no cover - handled with a module-level skip
    webdriver = None
    WebDriverException = Exception
    By = None
    EC = None
    Select = None
    WebDriverWait = None


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003 - inherited signature
        return


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


@unittest.skipUnless(webdriver is not None, "selenium is not installed")
class BuilderBrowserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/docs/builder/index.html"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def setUp(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1800")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        try:
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as error:  # pragma: no cover - depends on host browser availability
            raise unittest.SkipTest(f"Chrome webdriver is unavailable: {error}") from error
        self.wait = WebDriverWait(self.driver, 20)
        self.driver.get(self.base_url)
        self.wait_for_builder()
        self.driver.execute_script("window.localStorage.clear();")
        self.driver.get(self.base_url)
        self.wait_for_builder()

    def tearDown(self):
        if hasattr(self, "driver"):
            self.driver.quit()

    def wait_for_builder(self):
        self.wait.until(EC.presence_of_element_located((By.ID, "faction-select")))
        self.wait.until(lambda driver: driver.find_element(By.ID, "faction-select").is_enabled())
        self.wait.until(lambda driver: "Coverage summary will appear" not in driver.find_element(By.ID, "data-confidence").text)
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#unit-list [data-action='add-unit']")))

    def test_filter_edit_and_save_flow(self):
        Select(self.driver.find_element(By.ID, "faction-select")).select_by_visible_text("Space Wolves")
        self.wait.until(lambda driver: "180/191 units are ready" in driver.find_element(By.ID, "data-confidence").text)

        self.driver.find_element(By.ID, "advanced-filters-toggle").click()
        Select(self.driver.find_element(By.ID, "support-filter")).select_by_visible_text("Needs review")
        self.wait.until(lambda driver: "Needs review" in driver.find_element(By.ID, "unit-list").text)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='focus-unit']").click()
        self.wait.until(lambda driver: "already in your roster" in driver.find_element(By.ID, "unit-list").text or "Add this unit to start configuring it in the roster workspace." in driver.find_element(By.ID, "unit-list").text)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']").click()
        self.wait.until(lambda driver: "Edit" in driver.find_element(By.ID, "roster-body").text)
        self.driver.find_element(By.CSS_SELECTOR, "#roster-body [data-action='edit-entry']").click()
        self.wait.until(lambda driver: not driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.assertIn("Needs review", self.driver.find_element(By.ID, "entry-editor").text)

        self.driver.find_element(By.ID, "save-roster").click()
        self.wait.until(lambda driver: "Saved" in driver.find_element(By.ID, "roster-status").text)
        self.wait.until(
            lambda driver: "compatible" in driver.find_element(By.CSS_SELECTOR, "#saved-roster-select option").text
        )

    def test_mobile_workspace_tabs_and_summary(self):
        self.driver.set_window_size(430, 1200)
        self.driver.get(self.base_url)
        self.wait_for_builder()

        self.wait.until(lambda driver: driver.find_element(By.ID, "mobile-workspace-bar").is_displayed())
        self.assertTrue(self.driver.find_element(By.ID, "browse-panel").is_displayed())

        starting_points = self.driver.find_element(By.ID, "mobile-summary-points").text
        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']").click()
        self.wait.until(lambda driver: driver.find_element(By.ID, "mobile-summary-points").text != starting_points)

        self.driver.find_element(By.ID, "mobile-tab-roster").click()
        self.wait.until(lambda driver: driver.find_element(By.ID, "roster-panel").is_displayed())

        self.driver.find_element(By.ID, "mobile-tab-cards").click()
        self.wait.until(lambda driver: driver.find_element(By.ID, "preview-panel").is_displayed())

    def test_stale_roster_repair_copy_flow(self):
        stale_roster = {
            "schemaVersion": 6,
            "id": "roster-stale-1",
            "savedAt": "2026-03-01T12:00:00.000Z",
            "appVersion": "builder-catalog-v2",
            "factionSlug": "adeptus-custodes",
            "name": "Broken Custodes",
            "builderSchemaVersion": 5,
            "builderGeneratedAt": "2026-03-01T12:00:00.000Z",
            "army": {"battleSize": "incursion", "detachmentId": None, "warlordInstanceId": None},
            "entries": [
                {
                    "instanceId": "entry-missing",
                    "unitId": "shield-captain-old",
                    "optionId": "1-model",
                    "quantity": 1,
                    "wargearSelections": {},
                },
                {
                    "instanceId": "entry-good",
                    "unitId": "blade-champion",
                    "optionId": "1-model",
                    "quantity": 1,
                    "wargearSelections": {},
                },
            ],
        }
        self.driver.execute_script(
            """
            const roster = arguments[0];
            window.localStorage.clear();
            window.localStorage.setItem(
                "wahpediaCapture.builder.v1.savedRosters",
                JSON.stringify([{
                    id: roster.id,
                    name: roster.name,
                    factionSlug: roster.factionSlug,
                    savedAt: roster.savedAt,
                    builderSchemaVersion: roster.builderSchemaVersion,
                    builderGeneratedAt: roster.builderGeneratedAt,
                }])
            );
            window.localStorage.setItem("wahpediaCapture.builder.v1.activeRosterId", roster.id);
            window.localStorage.setItem(
                `wahpediaCapture.builder.v1.roster.${roster.id}`,
                JSON.stringify(roster)
            );
            """,
            stale_roster,
        )
        self.driver.get(self.base_url)
        self.wait_for_builder()

        self.wait.until(lambda driver: "Roster repair" in driver.find_element(By.ID, "repair-panel").text)
        self.driver.find_element(By.CSS_SELECTOR, "#repair-panel [data-action='repair-copy']").click()

        self.wait.until(lambda driver: "Started a repaired copy" in driver.find_element(By.ID, "roster-status").text)
        roster_body = self.driver.find_element(By.ID, "roster-body").text
        self.assertIn("Blade Champion", roster_body)
        self.assertNotIn("shield-captain-old", roster_body)
        self.assertIn("Repaired", self.driver.find_element(By.ID, "roster-name").get_attribute("value"))


if __name__ == "__main__":
    unittest.main()
