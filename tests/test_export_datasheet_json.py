import importlib.util
import json
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "export_datasheet_json.py"

spec = importlib.util.spec_from_file_location("export_datasheet_json", MODULE_PATH)
export_datasheet_json = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(export_datasheet_json)


class ExportDatasheetTests(unittest.TestCase):
    def test_parse_characteristics_supports_ds_char_wrap_m(self):
        soup = BeautifulSoup(
            """
            <div class="dsSelection">
              <div class="dsProfileBaseWrap">
                <div class="dsProfileWrap">
                  <div class="dsCharWrapM">
                    <div class="dsCharName">M</div>
                    <div class="dsCharValue">20+"</div>
                  </div>
                  <div class="dsCharWrapM">
                    <div class="dsCharName">T</div>
                    <div class="dsCharValue">8</div>
                  </div>
                  <div class="dsCharWrapM">
                    <div class="dsCharName">Sv</div>
                    <div class="dsCharValue">3+</div>
                  </div>
                </div>
              </div>
              <div class="dsInvulWrap">
                <div class="dsCharInvulValue">5+</div>
              </div>
            </div>
            """,
            "html.parser",
        )

        characteristics = export_datasheet_json.parse_characteristics(soup.select_one("div.dsSelection"))
        self.assertEqual(
            characteristics,
            {
                "M": '20+"',
                "T": "8",
                "Sv": "3+",
                "Invulnerable Save": "5+",
            },
        )

    def test_parse_section_block_supports_wargear_options(self):
        soup = BeautifulSoup(
            """
            <div>
              <ul>
                <li>
                  1 Tactical Marine's boltgun can be replaced with one of the following:
                  <ul>
                    <li>1 flamer</li>
                    <li>1 meltagun</li>
                  </ul>
                </li>
              </ul>
              <div class="dsOptionsComment">Only one model can take this option.</div>
            </div>
            """,
            "html.parser",
        )

        entries = export_datasheet_json.parse_section_block("WARGEAR OPTIONS", soup.div)
        self.assertEqual(entries[0]["type"], "option_group")
        self.assertIn("boltgun can be replaced", entries[0]["label"])
        self.assertEqual(entries[0]["items"], ["1 flamer", "1 meltagun"])
        self.assertEqual(entries[1]["type"], "text")
        self.assertIn("Only one model", entries[1]["text"])

    def test_real_repo_aircraft_exports_include_core_stats(self):
        samples = [
            ROOT / "out" / "json" / "space-marines" / "Stormtalon-Gunship.json",
            ROOT / "out" / "json" / "aeldari" / "Crimson-Hunter.json",
        ]
        for path in samples:
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                for stat in ("M", "T", "Sv", "W", "Ld", "OC"):
                    self.assertIn(stat, payload["characteristics"])
                    self.assertTrue(payload["characteristics"][stat])


if __name__ == "__main__":
    unittest.main()
