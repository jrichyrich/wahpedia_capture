import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "export_datasheet_json.py"

spec = importlib.util.spec_from_file_location("export_datasheet_json", MODULE_PATH)
export_datasheet_json = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(export_datasheet_json)

VALIDATE_MODULE_PATH = ROOT / "scripts" / "validate_datasheet_exports.py"
validate_spec = importlib.util.spec_from_file_location(
    "validate_datasheet_exports",
    VALIDATE_MODULE_PATH,
)
validate_datasheet_exports = importlib.util.module_from_spec(validate_spec)
assert validate_spec.loader is not None
validate_spec.loader.exec_module(validate_datasheet_exports)


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

    def test_parse_right_column_sections_supports_non_ds_ability_bodies(self):
        soup = BeautifulSoup(
            """
            <div class="dsOuterFrame datasheet">
              <div class="ds2col">
                <div class="dsLeftСol">
                  <table class="wTable"></table>
                </div>
                <div class="dsRightСol">
                  <div class="dsHeader">ABILITIES</div>
                  <div class="dsAbility">FACTION: <b>Oath of Moment</b></div>
                  <div class="dsHeader">WARGEAR OPTIONS</div>
                  <ul>
                    <li>
                      1 model's boltgun can be replaced with one of the following:
                      <ul>
                        <li>1 flamer</li>
                      </ul>
                    </li>
                  </ul>
                  <div class="dsOptionsComment">Comment text.</div>
                  <div class="dsHeader">UNIT COMPOSITION</div>
                  <div>Every model is equipped with: boltgun.</div>
                  <table><tr><td>5 models</td><td><div class="PriceTag">100</div></td></tr></table>
                </div>
              </div>
            </div>
            """,
            "html.parser",
        )

        sections = export_datasheet_json.parse_right_column_sections(
            soup.select_one("div.dsOuterFrame.datasheet")
        )
        self.assertEqual([section["title"] for section in sections], ["ABILITIES", "WARGEAR OPTIONS", "UNIT COMPOSITION"])
        self.assertEqual(sections[1]["entries"][0]["type"], "option_group")
        self.assertEqual(sections[1]["entries"][0]["items"], ["1 flamer"])
        self.assertEqual(sections[1]["entries"][1]["type"], "text")
        self.assertEqual(sections[2]["entries"][0]["type"], "points")

    def test_section_titles_in_markup_collects_all_headers(self):
        soup = BeautifulSoup(
            """
            <div class="dsOuterFrame datasheet">
              <div class="dsHeader">WARGEAR OPTIONS</div>
              <div class="dsHeader">ABILITIES</div>
              <div class="dsHeader">UNIT COMPOSITION</div>
            </div>
            """,
            "html.parser",
        )

        self.assertEqual(
            export_datasheet_json.section_titles_in_markup(
                soup.select_one("div.dsOuterFrame.datasheet")
            ),
            ["WARGEAR OPTIONS", "ABILITIES", "UNIT COMPOSITION"],
        )

    def test_parse_datasheet_from_soup_adds_export_metadata(self):
        soup = BeautifulSoup(
            """
            <div class="dsOuterFrame datasheet">
              <div class="dsH2Header">Terminator Squad (5 models)</div>
              <div class="dsProfileBaseWrap">
                <div class="dsCharWrapM"><div class="dsCharName">M</div><div class="dsCharValue">5"</div></div>
                <div class="dsCharWrapM"><div class="dsCharName">T</div><div class="dsCharValue">5</div></div>
                <div class="dsCharWrapM"><div class="dsCharName">Sv</div><div class="dsCharValue">2+</div></div>
                <div class="dsCharWrapM"><div class="dsCharName">W</div><div class="dsCharValue">3</div></div>
                <div class="dsCharWrapM"><div class="dsCharName">Ld</div><div class="dsCharValue">6+</div></div>
                <div class="dsCharWrapM"><div class="dsCharName">OC</div><div class="dsCharValue">1</div></div>
              </div>
              <div class="ds2col">
                <div class="dsLeftСol">
                  <table class="wTable"></table>
                  <div class="dsHeader">WARGEAR OPTIONS</div>
                  <ul>
                    <li>
                      1 Terminator's storm bolter can be replaced with one of the following:
                      <ul><li>1 assault cannon</li></ul>
                    </li>
                  </ul>
                </div>
                <div class="dsRightСol">
                  <div class="dsHeader">ABILITIES</div>
                  <div>Ability text.</div>
                  <div class="dsHeader">UNIT COMPOSITION</div>
                  <div>Every model is equipped with: power fist.</div>
                  <table><tr><td>5 models</td><td><div class="PriceTag">170</div></td></tr></table>
                </div>
              </div>
              <div class="ds2colKW">
                <div>KEYWORDS: INFANTRY, TERMINATOR</div>
                <div>FACTION KEYWORDS: ADEPTUS ASTARTES</div>
              </div>
            </div>
            """,
            "html.parser",
        )

        payload = export_datasheet_json.parse_datasheet_from_soup(
            "https://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad/",
            soup,
            fetched_at="2026-03-19T00:00:00+00:00",
            source_content_hash="abc123",
        )

        self.assertEqual(payload["exportSchemaVersion"], 1)
        self.assertEqual(payload["parserVersion"], "2026-03-19-durable-normalization-v1")
        self.assertEqual(
            payload["source"]["normalizedUrl"],
            "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
        )
        self.assertTrue(payload["source"]["canonicalSourceId"].startswith("wahapedia:"))
        self.assertEqual(payload["source"]["fetchedAt"], "2026-03-19T00:00:00+00:00")
        self.assertEqual(payload["source"]["contentHash"], "abc123")
        self.assertEqual(payload["quality"]["rawSectionTitles"], ["WARGEAR OPTIONS", "ABILITIES", "UNIT COMPOSITION"])
        self.assertEqual(payload["quality"]["exportedSectionTitles"], ["WARGEAR OPTIONS", "ABILITIES", "UNIT COMPOSITION"])
        self.assertEqual(payload["quality"]["missingExpectedSections"], [])

    def test_write_export_manifest_collects_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_root = Path(tmpdir)
            faction_dir = out_root / "space-marines"
            faction_dir.mkdir()
            payload = {
                "exportSchemaVersion": 1,
                "parserVersion": "2026-03-19-durable-normalization-v1",
                "source": {
                    "url": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                    "normalizedUrl": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                    "canonicalSourceId": "wahapedia:test",
                    "faction_slug": "space-marines",
                    "datasheet_slug": "Terminator-Squad",
                    "output_slug": "space-marines",
                    "fetchedAt": "2026-03-19T00:00:00+00:00",
                    "contentHash": "abc123",
                },
                "name": "Terminator Squad",
                "characteristics": {"M": '5"', "T": "5", "Sv": "2+", "W": "3", "Ld": "6+", "OC": "1"},
                "weapons": {},
                "abilities": {},
                "unit_composition": [],
                "keywords": ["INFANTRY"],
                "faction_keywords": ["ADEPTUS ASTARTES"],
                "sections": [{"title": "ABILITIES", "entries": []}],
                "quality": {
                    "rawSectionTitles": ["ABILITIES"],
                    "exportedSectionTitles": ["ABILITIES"],
                    "missingExpectedSections": [],
                    "warnings": [],
                },
            }
            (faction_dir / "Terminator-Squad.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            manifest_path = export_datasheet_json.write_export_manifest(out_root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["exportSchemaVersion"], 1)
            self.assertEqual(manifest["parserVersion"], "2026-03-19-durable-normalization-v1")
            self.assertEqual(len(manifest["records"]), 1)
            self.assertEqual(manifest["records"][0]["outputSlug"], "space-marines")
            self.assertEqual(manifest["records"][0]["datasheetSlug"], "Terminator-Squad")
            self.assertEqual(manifest["records"][0]["canonicalSourceId"], "wahapedia:test")

    def test_validate_local_exports_flags_missing_exported_wargear_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_root = Path(tmpdir)
            faction_dir = out_root / "space-marines"
            faction_dir.mkdir()
            payload = {
                "exportSchemaVersion": 1,
                "parserVersion": "2026-03-19-durable-normalization-v1",
                "source": {
                    "url": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                    "normalizedUrl": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                    "canonicalSourceId": "wahapedia:test",
                    "faction_slug": "space-marines",
                    "datasheet_slug": "Terminator-Squad",
                    "output_slug": "space-marines",
                    "fetchedAt": "2026-03-19T00:00:00+00:00",
                    "contentHash": "abc123",
                },
                "name": "Terminator Squad",
                "characteristics": {"M": '5"', "T": "5", "Sv": "2+", "W": "3", "Ld": "6+", "OC": "1"},
                "weapons": {},
                "abilities": {},
                "unit_composition": [],
                "keywords": ["INFANTRY"],
                "faction_keywords": ["ADEPTUS ASTARTES"],
                "sections": [{"title": "ABILITIES", "entries": []}, {"title": "UNIT COMPOSITION", "entries": []}],
                "quality": {
                    "rawSectionTitles": ["WARGEAR OPTIONS", "ABILITIES", "UNIT COMPOSITION"],
                    "exportedSectionTitles": ["ABILITIES", "UNIT COMPOSITION"],
                    "missingExpectedSections": ["WARGEAR OPTIONS"],
                    "warnings": ["section-missing:WARGEAR OPTIONS"],
                },
            }
            (faction_dir / "Terminator-Squad.json").write_text(json.dumps(payload), encoding="utf-8")
            export_datasheet_json.write_export_manifest(out_root)

            report = validate_datasheet_exports.validate_local_exports(out_root, [], [])
            self.assertEqual(report["recordCount"], 1)
            self.assertIn(
                "WARGEAR OPTIONS header present in markup but missing from exported sections",
                report["records"][0]["warnings"],
            )

    def test_validate_local_exports_flags_duplicate_source_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_root = Path(tmpdir)
            for output_slug, section_title in (("space-marines", "WARGEAR OPTIONS"), ("ultramarines", "ABILITIES")):
                faction_dir = out_root / output_slug
                faction_dir.mkdir(exist_ok=True)
                payload = {
                    "exportSchemaVersion": 1,
                    "parserVersion": "2026-03-19-durable-normalization-v1",
                    "source": {
                        "url": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                        "normalizedUrl": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Terminator-Squad",
                        "canonicalSourceId": "wahapedia:test",
                        "faction_slug": output_slug,
                        "datasheet_slug": "Terminator-Squad",
                        "output_slug": output_slug,
                        "fetchedAt": "2026-03-19T00:00:00+00:00",
                        "contentHash": "abc123",
                    },
                    "name": "Terminator Squad",
                    "characteristics": {"M": '5"', "T": "5", "Sv": "2+", "W": "3", "Ld": "6+", "OC": "1"},
                    "weapons": {},
                    "abilities": {},
                    "unit_composition": [],
                    "keywords": ["INFANTRY"],
                    "faction_keywords": ["ADEPTUS ASTARTES"],
                    "sections": [{"title": section_title, "entries": []}],
                    "quality": {
                        "rawSectionTitles": [section_title],
                        "exportedSectionTitles": [section_title],
                        "missingExpectedSections": [],
                        "warnings": [],
                    },
                }
                (faction_dir / "Terminator-Squad.json").write_text(json.dumps(payload), encoding="utf-8")

            export_datasheet_json.write_export_manifest(out_root)
            report = validate_datasheet_exports.validate_local_exports(
                out_root,
                ["space-marines", "ultramarines"],
                ["Terminator-Squad"],
            )
            self.assertEqual(len(report["driftRecords"]), 1)
            self.assertEqual(report["driftRecords"][0]["canonicalSourceId"], "wahapedia:test")

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
