import functools
import http.server
import json
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
MANIFEST = json.loads((ROOT / "docs" / "builder" / "data" / "manifest.json").read_text(encoding="utf-8"))
CURRENT_SCHEMA_VERSION = MANIFEST.get("schemaVersion")
CURRENT_GENERATED_AT = MANIFEST.get("generatedAt")


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

    def seed_saved_roster(self, roster):
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
            roster,
        )
        self.driver.get(self.base_url)
        self.wait_for_builder()

    def test_filter_edit_and_save_flow(self):
        Select(self.driver.find_element(By.ID, "faction-select")).select_by_visible_text("Aeldari")
        self.driver.find_element(By.ID, "catalog-health-toggle").click()
        self.wait.until(
            lambda driver: "97/97 units are ready without known review flags."
            in driver.find_element(By.ID, "data-confidence").text
        )

        self.driver.find_element(By.ID, "advanced-filters-toggle").click()
        Select(self.driver.find_element(By.ID, "support-filter")).select_by_visible_text("Ready only")
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']")) > 0)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='focus-unit']").click()
        self.wait.until(lambda driver: "already in your roster" in driver.find_element(By.ID, "unit-list").text or "Add this unit to start configuring it in the roster workspace." in driver.find_element(By.ID, "unit-list").text)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']").click()
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#roster-body .roster-entry")) > 0)
        self.driver.find_element(By.CSS_SELECTOR, "#roster-body [data-action='edit-entry']").click()
        self.wait.until(lambda driver: not driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.assertIn("CONFIGURATION", self.driver.find_element(By.ID, "entry-editor").text)

        self.driver.find_element(By.ID, "save-roster").click()
        self.wait.until(lambda driver: "Saved" in driver.find_element(By.ID, "roster-status").text)
        self.wait.until(
            lambda driver: "compatible" in driver.find_element(By.CSS_SELECTOR, "#saved-roster-select option").text
        )

    def test_catalog_details_open_without_mutating_roster(self):
        Select(self.driver.find_element(By.ID, "faction-select")).select_by_visible_text("Aeldari")
        starting_points = self.driver.find_element(By.ID, "total-points").text
        self.assertIn("No roster entries yet.", self.driver.find_element(By.ID, "roster-body").text)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='focus-unit']").click()
        self.wait.until(lambda driver: not driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.assertIn("Browse only", self.driver.find_element(By.ID, "entry-editor").text)
        self.assertIn("Add to roster", self.driver.find_element(By.ID, "entry-editor").text)
        self.assertIn("datasheet-card", self.driver.find_element(By.ID, "entry-editor").get_attribute("innerHTML"))
        self.assertEqual([], self.driver.find_elements(By.CSS_SELECTOR, "#entry-editor [data-action='option-select']"))
        self.assertEqual([], self.driver.find_elements(By.CSS_SELECTOR, "#entry-editor [data-action='warlord-select']"))
        self.assertEqual(starting_points, self.driver.find_element(By.ID, "total-points").text)
        self.assertIn("No roster entries yet.", self.driver.find_element(By.ID, "roster-body").text)

        self.driver.find_element(By.CSS_SELECTOR, "#entry-editor [data-action='add-unit']").click()
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#roster-body .roster-entry")) == 1)
        self.assertNotIn("No roster entries yet.", self.driver.find_element(By.ID, "roster-body").text)

    def test_inline_card_selection_updates_roster_without_opening_editor(self):
        Select(self.driver.find_element(By.ID, "faction-select")).select_by_visible_text("Adeptus Custodes")
        self.driver.find_element(By.ID, "unit-search").clear()
        self.driver.find_element(By.ID, "unit-search").send_keys("Caladius Grav-tank")
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']")) > 0)

        self.driver.find_element(By.CSS_SELECTOR, "#unit-list [data-action='add-unit']").click()
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#preview-body [data-action='card-inline-select']")) > 0)
        self.driver.find_element(By.CSS_SELECTOR, "#preview-body [data-action='card-inline-select']").click()

        self.wait.until(
            lambda driver: "updated to" in driver.find_element(By.ID, "roster-status").text.lower()
        )
        self.assertIn("undo", self.driver.find_element(By.ID, "roster-status").text.lower())
        self.assertTrue(self.driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#preview-body [data-preview-inline-status]")) > 0)
        preview_inline_status = self.driver.find_element(By.CSS_SELECTOR, "#preview-body [data-preview-inline-status]")
        self.assertIn("updated to", preview_inline_status.text.lower())
        self.assertIn("undo", preview_inline_status.text.lower())
        self.assertTrue(self.driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))

        self.driver.find_element(By.CSS_SELECTOR, "#preview-body [data-action='open-entry-editor']").click()
        self.wait.until(lambda driver: not driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.assertIn("CONFIGURATION", self.driver.find_element(By.ID, "entry-editor").text)

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

        self.wait.until(lambda driver: "roster repair" in driver.find_element(By.ID, "repair-panel").text.lower())
        self.driver.find_element(By.CSS_SELECTOR, "#repair-panel [data-action='repair-copy']").click()

        self.wait.until(lambda driver: "Started a repaired copy" in driver.find_element(By.ID, "roster-status").text)
        roster_body = self.driver.find_element(By.ID, "roster-body").text
        self.assertIn("Blade Champion", roster_body)
        self.assertNotIn("shield-captain-old", roster_body)
        self.assertIn("Repaired", self.driver.find_element(By.ID, "roster-name").get_attribute("value"))

    def test_enhancement_mismatch_summary_focuses_invalid_entry(self):
        roster = {
            "schemaVersion": 6,
            "id": "roster-enhancement-ui",
            "savedAt": "2026-04-02T12:00:00.000Z",
            "appVersion": "builder-catalog-v2",
            "factionSlug": "aeldari",
            "name": "Enhancement UI",
            "builderSchemaVersion": CURRENT_SCHEMA_VERSION,
            "builderGeneratedAt": CURRENT_GENERATED_AT,
            "army": {"battleSize": "strike-force", "detachmentId": "warhost", "warlordInstanceId": "entry-autarch"},
            "entries": [
                {
                    "instanceId": "entry-autarch",
                    "unitId": "autarch",
                    "optionId": "1-model",
                    "quantity": 1,
                    "enhancementId": "psychic-destroyer",
                    "wargearSelections": {},
                }
            ],
        }
        self.seed_saved_roster(roster)

        self.wait.until(
            lambda driver: "psychic destroyer requires asuryani psyker"
            in driver.find_element(By.ID, "legality-summary").text.lower()
        )
        self.driver.find_element(By.CSS_SELECTOR, "#legality-summary [data-action='open-entry-issue']").click()
        self.wait.until(lambda driver: not driver.find_element(By.ID, "entry-editor").get_attribute("hidden"))
        self.assertIn("Psychic Destroyer requires ASURYANI PSYKER", self.driver.find_element(By.ID, "entry-editor").text)
        self.driver.find_element(By.ID, "save-roster").click()
        self.wait.until(lambda driver: "Saved" in driver.find_element(By.ID, "roster-status").text)

    def test_leader_composition_summary_surfaces_extra_leader_issue(self):
        roster = {
            "schemaVersion": 6,
            "id": "roster-leader-ui",
            "savedAt": "2026-04-02T12:05:00.000Z",
            "appVersion": "builder-catalog-v2",
            "factionSlug": "space-marines",
            "name": "Leader UI",
            "builderSchemaVersion": CURRENT_SCHEMA_VERSION,
            "builderGeneratedAt": CURRENT_GENERATED_AT,
            "army": {"battleSize": "strike-force", "detachmentId": "gladius-task-force", "warlordInstanceId": "entry-captain"},
            "entries": [
                {"instanceId": "entry-bodyguard", "unitId": "intercessor-squad", "optionId": "5-models", "quantity": 1, "wargearSelections": {}},
                {"instanceId": "entry-captain", "unitId": "captain", "optionId": "1-model", "quantity": 1, "wargearSelections": {}, "attachedToInstanceId": "entry-bodyguard"},
                {"instanceId": "entry-lieutenant", "unitId": "lieutenant", "optionId": "1-model", "quantity": 1, "wargearSelections": {}, "attachedToInstanceId": "entry-bodyguard"},
                {"instanceId": "entry-apothecary", "unitId": "apothecary", "optionId": "1-model", "quantity": 1, "wargearSelections": {}, "attachedToInstanceId": "entry-bodyguard"},
            ],
        }
        self.seed_saved_roster(roster)

        self.wait.until(
            lambda driver: "allowed leader combination" in driver.find_element(By.ID, "legality-summary").text.lower()
        )
        self.driver.find_element(By.CSS_SELECTOR, "#legality-summary [data-action='open-entry-issue']").click()
        self.wait.until(lambda driver: "apothecary" in driver.find_element(By.ID, "entry-editor").text.lower())
        self.assertIn("allowed Leader combination", self.driver.find_element(By.ID, "entry-editor").text)

    def test_transport_assignment_summary_surfaces_allowlist_issue(self):
        roster = {
            "schemaVersion": 6,
            "id": "roster-transport-ui",
            "savedAt": "2026-04-02T12:10:00.000Z",
            "appVersion": "builder-catalog-v2",
            "factionSlug": "aeldari",
            "name": "Transport UI",
            "builderSchemaVersion": CURRENT_SCHEMA_VERSION,
            "builderGeneratedAt": CURRENT_GENERATED_AT,
            "army": {"battleSize": "strike-force", "detachmentId": "warhost", "warlordInstanceId": "entry-autarch"},
            "entries": [
                {"instanceId": "entry-autarch", "unitId": "autarch", "optionId": "1-model", "quantity": 1, "wargearSelections": {}},
                {"instanceId": "entry-guardians", "unitId": "guardian-defenders", "optionId": "11-models", "quantity": 1, "wargearSelections": {}, "embarkedInInstanceId": "entry-raider"},
                {"instanceId": "entry-raider", "unitId": "ynnari-raider", "optionId": "1-model", "quantity": 1, "wargearSelections": {}},
            ],
        }
        self.seed_saved_roster(roster)

        self.wait.until(
            lambda driver: "named-unit allowlist" in driver.find_element(By.ID, "legality-summary").text.lower()
        )
        self.driver.find_element(By.CSS_SELECTOR, "#legality-summary [data-action='open-entry-issue']").click()
        self.wait.until(lambda driver: "guardian defenders" in driver.find_element(By.ID, "entry-editor").text.lower())
        self.assertIn("named-unit allowlist", self.driver.find_element(By.ID, "entry-editor").text)

    def test_print_pack_summary_persists_across_preview_modes(self):
        roster = {
            "schemaVersion": 6,
            "id": "roster-print-pack-ui",
            "savedAt": "2026-04-02T12:30:00.000Z",
            "appVersion": "builder-catalog-v2",
            "factionSlug": "aeldari",
            "name": "Print Pack UI",
            "builderSchemaVersion": CURRENT_SCHEMA_VERSION,
            "builderGeneratedAt": CURRENT_GENERATED_AT,
            "army": {"battleSize": "strike-force", "detachmentId": "warhost", "warlordInstanceId": "entry-autarch"},
            "entries": [
                {"instanceId": "entry-autarch", "unitId": "autarch", "optionId": "1-model", "quantity": 1, "wargearSelections": {}},
                {"instanceId": "entry-guardians", "unitId": "guardian-defenders", "optionId": "11-models", "quantity": 1, "wargearSelections": {}},
            ],
        }
        self.seed_saved_roster(roster)

        self.wait.until(
            lambda driver: "print pack ui" in driver.find_element(By.CSS_SELECTOR, ".print-pack-summary").text.lower()
        )
        configured_status = self.driver.find_element(By.CSS_SELECTOR, ".print-pack-status-line").text
        configured_summary = self.driver.find_element(By.CSS_SELECTOR, ".print-pack-summary").text
        self.assertIn("Configured card mode", configured_status)
        self.assertIn("Guardian Defenders", configured_summary)

        self.driver.find_element(By.ID, "preview-mode-source").click()
        self.wait.until(
            lambda driver: "original wahapedia mode"
            in driver.find_element(By.CSS_SELECTOR, ".print-pack-status-line").text.lower()
        )
        source_status = self.driver.find_element(By.CSS_SELECTOR, ".print-pack-status-line").text
        source_summary = self.driver.find_element(By.CSS_SELECTOR, ".print-pack-summary").text
        self.assertIn("Original Wahapedia mode", source_status)
        self.assertIn("PRINT PACK UI", source_summary)


if __name__ == "__main__":
    unittest.main()
