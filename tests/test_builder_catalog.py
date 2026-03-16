import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_builder_catalog.py"

spec = importlib.util.spec_from_file_location("build_builder_catalog", MODULE_PATH)
build_builder_catalog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_builder_catalog)


class BuilderCatalogTests(unittest.TestCase):
    def test_normalize_card_preserves_structured_fields(self):
        card = {
            "source": {
                "url": "http://wahapedia.ru/wh40k10ed/factions/aeldari/Avatar-of-Khaine",
                "faction_slug": "aeldari",
                "datasheet_slug": "Avatar-of-Khaine",
            },
            "name": "Avatar of Khaine",
            "base_size": "80mm",
            "characteristics": {
                "M": '10"',
                "T": "11",
                "Sv": "2+",
                "W": "14",
                "Ld": "6+",
                "OC": "5",
                "Invulnerable Save": "4+",
            },
            "weapons": {
                "ranged_weapons": [
                    {
                        "name": "The Wailing Doom",
                        "range": '12"',
                        "a": "1",
                        "bs": "2+",
                        "s": "16",
                        "ap": "-4",
                        "d": "D6+2",
                        "abilities": ["sustained hits d3"],
                    }
                ],
                "melee_weapons": [
                    {
                        "name": "The Wailing Doom - strike",
                        "range": "Melee",
                        "a": "6",
                        "ws": "2+",
                        "s": "16",
                        "ap": "-4",
                        "d": "D6+2",
                        "abilities": [],
                    }
                ],
            },
            "abilities": {
                "core": ["Deadly Demise D3"],
                "faction": ["Battle Focus"],
                "datasheet": [
                    {"type": "rule", "name": "Molten Form", "text": "Halve damage received."}
                ],
                "other": [],
            },
            "unit_composition": [
                {"type": "list", "items": ["1 Avatar of Khaine - EPIC HERO"]},
                {
                    "type": "statement",
                    "label": "This model is equipped with",
                    "text": "the Wailing Doom",
                },
                {"type": "points", "rows": [{"label": "1 model", "points": "280"}]},
            ],
            "keywords": ["MONSTER", "AELDARI"],
            "faction_keywords": ["ASURYANI"],
            "sections": [
                {
                    "title": "DAMAGED: 1-5 WOUNDS REMAINING",
                    "entries": [{"type": "text", "text": "Subtract 1 from Hit rolls."}],
                },
                {
                    "title": "WARGEAR OPTIONS",
                    "entries": [
                        {
                            "type": "option_group",
                            "label": "1 model's sword can be replaced with one of the following:",
                            "items": ["1 axe", "1 spear"],
                        },
                        {
                            "type": "option_group",
                            "label": "The Exarch can be replaced with 1 twin blades, or two different weapons from the following list:",
                            "items": ["1 pistol", "1 blade"],
                        },
                    ],
                },
                {
                    "title": "LEADER",
                    "entries": [{"type": "list", "items": ["Example Unit"]}],
                },
            ],
        }

        unit, diagnostics = build_builder_catalog.normalize_card("aeldari", card)
        self.assertEqual(unit["unitId"], "avatar-of-khaine")
        self.assertEqual(unit["stats"]["invulnerableSave"], "4+")
        self.assertEqual(unit["weapons"]["ranged"][0]["skillType"], "BS")
        self.assertEqual(unit["pointsOptions"][0]["points"], 280)
        self.assertEqual(unit["pointsOptions"][0]["selectionKind"], "models")
        self.assertEqual(unit["selectionMode"], "parsed")
        self.assertEqual(unit["composition"]["modelCountOptions"][0]["minModels"], 1)
        self.assertEqual(unit["wargear"]["options"][0]["selectionMode"], "single")
        self.assertEqual(unit["wargear"]["options"][0]["action"], "replace")
        self.assertTrue(unit["wargear"]["hasManualOptions"])
        self.assertEqual(unit["renderBlocks"][0]["displayStyle"], "damaged")
        self.assertEqual(unit["renderBlocks"][1]["title"], "LEADER")
        self.assertEqual(diagnostics["missingStats"], [])
        self.assertTrue(diagnostics["manualWargear"])
        self.assertFalse(unit["quality"]["hasMissingStats"])

    def test_parse_wargear_prompt_supports_fixed_replacements(self):
        fixed_replace = build_builder_catalog.parse_wargear_prompt(
            "This model’s witchblade can be replaced with 1 singing spear."
        )
        self.assertEqual(fixed_replace["selectionMode"], "single")
        self.assertEqual(fixed_replace["action"], "replace")
        self.assertEqual(fixed_replace["choices"][0]["label"], "1 singing spear")

        unit_wide_replace = build_builder_catalog.parse_wargear_prompt(
            "All Eliminators in this unit can each have their bolt sniper rifle replaced with 1 las fusil."
        )
        self.assertEqual(unit_wide_replace["selectionMode"], "single")
        self.assertEqual(unit_wide_replace["action"], "replace")
        self.assertEqual(unit_wide_replace["target"], "All Eliminators in this unit")
        self.assertEqual(unit_wide_replace["choices"][0]["label"], "1 las fusil")

        unit_wide_equip = build_builder_catalog.parse_wargear_prompt(
            "All models in this unit can each be equipped with 1 grapnel launcher."
        )
        self.assertEqual(unit_wide_equip["selectionMode"], "single")
        self.assertEqual(unit_wide_equip["action"], "equip")
        self.assertEqual(unit_wide_equip["choices"][0]["label"], "1 grapnel launcher")

    def test_build_composition_parses_upgrade_point_labels(self):
        composition = build_builder_catalog.build_composition(
            [
                {"type": "list", "items": ["3 Outriders"]},
                {"type": "list", "items": ["0-1 Invader ATV"]},
                {
                    "type": "points",
                    "rows": [
                        {"label": "3 models", "points": "80"},
                        {"label": "Invader ATV", "points": "+80"},
                    ],
                },
            ]
        )

        self.assertEqual(composition["selectionMode"], "parsed")
        self.assertEqual(composition["pointsOptions"][0]["modelCount"], 3)
        self.assertEqual(composition["pointsOptions"][0]["selectionKind"], "models")
        self.assertEqual(composition["pointsOptions"][1]["modelCount"], 1)
        self.assertEqual(composition["pointsOptions"][1]["selectionKind"], "upgrade")

    def test_build_composition_parses_mixed_point_labels(self):
        composition = build_builder_catalog.build_composition(
            [
                {"type": "list", "items": ["3-6 Wolf Guard Headtakers", "0-6 Hunting Wolves"]},
                {
                    "type": "points",
                    "rows": [
                        {"label": "3 Wolf Guard Headtakers", "points": "85"},
                        {"label": "3 Wolf Guard Headtakers and 3 Hunting Wolves", "points": "110"},
                    ],
                },
            ]
        )

        self.assertEqual(composition["selectionMode"], "parsed")
        self.assertEqual(composition["pointsOptions"][0]["selectionKind"], "models")
        self.assertEqual(composition["pointsOptions"][0]["modelCount"], 3)
        self.assertEqual(composition["pointsOptions"][1]["selectionKind"], "mixed")
        self.assertEqual(composition["pointsOptions"][1]["modelCount"], 6)

    def test_build_all_writes_manifest_catalog_and_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            output_root = Path(tmpdir) / "out"
            faction_dir = source_root / "test-faction"
            faction_dir.mkdir(parents=True)

            unit_one = {
                "source": {
                    "url": "http://example/One",
                    "faction_slug": "test-faction",
                    "datasheet_slug": "One",
                },
                "name": "Unit One",
                "characteristics": {
                    "M": '6"',
                    "T": "4",
                    "Sv": "3+",
                    "W": "2",
                    "Ld": "7+",
                    "OC": "1",
                },
                "weapons": {"ranged_weapons": [], "melee_weapons": []},
                "abilities": {"core": [], "faction": [], "datasheet": [], "other": []},
                "unit_composition": [
                    {"type": "list", "items": ["5 Unit One"]},
                    {"type": "points", "rows": [{"label": "5 models", "points": "95"}]},
                ],
                "keywords": ["INFANTRY"],
                "faction_keywords": ["TEST"],
                "sections": [],
            }
            unit_two = {
                "source": {
                    "url": "http://example/Two",
                    "faction_slug": "test-faction",
                    "datasheet_slug": "Two",
                },
                "name": "Unit Two",
                "characteristics": {},
                "weapons": {"ranged_weapons": [], "melee_weapons": []},
                "abilities": {"core": [], "faction": [], "datasheet": [], "other": []},
                "unit_composition": [
                    {"type": "list", "items": ["1 Unit Two"]},
                    {"type": "points", "rows": [{"label": "Attack Bike", "points": "70"}]},
                ],
                "keywords": ["BIKER"],
                "faction_keywords": ["TEST"],
                "sections": [],
            }

            (faction_dir / "index.json").write_text(json.dumps([unit_one, unit_two]), encoding="utf-8")

            manifest = build_builder_catalog.build_all(source_root, output_root, clean=True)
            self.assertEqual(manifest["report"]["totals"]["factionCount"], 1)
            self.assertEqual(manifest["report"]["totals"]["unitCount"], 2)
            self.assertEqual(manifest["report"]["totals"]["missingStatsCount"], 1)
            self.assertEqual(manifest["report"]["totals"]["manualSelectionCount"], 0)
            self.assertEqual(manifest["report"]["totals"]["manualWargearCount"], 0)
            self.assertTrue((output_root / "catalogs" / "test-faction.json").exists())
            self.assertTrue((output_root / "reports" / "build-report.json").exists())
            self.assertTrue((output_root / "manifest.json").exists())

    def test_real_repo_samples_build_expected_shape(self):
        samples = [
            ("aeldari", "Avatar of Khaine"),
            ("adeptus-custodes", "Aleya"),
            ("space-wolves", "Ragnar Blackmane"),
        ]
        for faction_slug, expected_name in samples:
            index_path = ROOT / "out" / "json" / faction_slug / "index.json"
            self.assertTrue(index_path.exists(), str(index_path))
            cards = json.loads(index_path.read_text(encoding="utf-8"))
            unit, _ = build_builder_catalog.normalize_card(faction_slug, cards[0])
            self.assertIn("unitId", unit)
            self.assertIn("pointsOptions", unit)
            self.assertIn("renderBlocks", unit)
            self.assertIn("stats", unit)
            names = [card["name"] for card in cards]
            self.assertIn(expected_name, names)

    def test_real_repo_problem_units_parse_without_manual_labels(self):
        samples = [
            ("space-marines", "Bike-Squad.json", "Attack Bike", "upgrade", 1),
            ("space-marines", "Outrider-Squad.json", "Invader ATV", "upgrade", 1),
            ("aeldari", "Shadow-Spectres.json", "Shadow Spectre Exarch", "upgrade", 1),
            (
                "space-wolves",
                "Wolf-Guard-Headtakers.json",
                "3 Wolf Guard Headtakers and 3 Hunting Wolves",
                "mixed",
                6,
            ),
        ]

        for faction_slug, filename, option_label, selection_kind, model_count in samples:
            card = json.loads((ROOT / "out" / "json" / faction_slug / filename).read_text(encoding="utf-8"))
            unit, diagnostics = build_builder_catalog.normalize_card(faction_slug, card)
            option = next(entry for entry in unit["pointsOptions"] if entry["label"] == option_label)
            self.assertEqual(unit["selectionMode"], "parsed")
            self.assertFalse(diagnostics["manualSelection"])
            self.assertEqual(option["selectionKind"], selection_kind)
            self.assertEqual(option["modelCount"], model_count)

    def test_real_repo_tactical_squad_has_wargear_options(self):
        card = json.loads((ROOT / "out" / "json" / "space-marines" / "Tactical-Squad.json").read_text(encoding="utf-8"))
        unit, _ = build_builder_catalog.normalize_card("space-marines", card)
        self.assertTrue(unit["wargear"]["options"])
        self.assertEqual(unit["wargear"]["options"][0]["selectionMode"], "single")
        self.assertTrue(unit["wargear"]["hasManualOptions"])

    def test_real_repo_fixed_wargear_prompt_is_structured(self):
        card = json.loads((ROOT / "out" / "json" / "aeldari" / "Farseer.json").read_text(encoding="utf-8"))
        unit, diagnostics = build_builder_catalog.normalize_card("aeldari", card)
        self.assertEqual(unit["wargear"]["options"][0]["selectionMode"], "single")
        self.assertEqual(unit["wargear"]["options"][0]["choices"][0]["label"], "1 singing spear")
        self.assertFalse(diagnostics["manualWargear"])


class BuilderAppSmokeTests(unittest.TestCase):
    def test_builder_page_references_generated_manifest_and_renderer(self):
        html_path = ROOT / "docs" / "builder" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("./data/manifest.json", html)
        self.assertIn("./card_renderer.js", html)
        self.assertIn("./roster_store.js", html)
        self.assertIn("WahBuilderCardRenderer.renderCard", html)
        self.assertIn("Print roster cards", html)
        self.assertIn("Import JSON", html)
        self.assertIn("Export JSON", html)
        self.assertIn("Saved rosters", html)
        self.assertIn('window.location.protocol === "file:"', html)


if __name__ == "__main__":
    unittest.main()
