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
        self.assertEqual(unit["wargear"]["options"][1]["selectionMode"], "multi")
        self.assertEqual(unit["wargear"]["options"][1]["pickCount"], 2)
        self.assertEqual(unit["wargear"]["options"][1]["choices"][0]["pickCost"], 2)
        self.assertFalse(unit["wargear"]["hasManualOptions"])
        self.assertEqual(unit["renderBlocks"][0]["displayStyle"], "damaged")
        self.assertEqual(unit["renderBlocks"][1]["title"], "LEADER")
        self.assertEqual(diagnostics["missingStats"], [])
        self.assertFalse(diagnostics["manualWargear"])
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

        conditional_equip = build_builder_catalog.parse_wargear_prompt(
            "1 Kasrkin Trooper equipped with a hot-shot lasgun can be equipped with 1 vox-caster (that model’s hot-shot lasgun cannot be replaced)."
        )
        self.assertEqual(conditional_equip["selectionMode"], "single")
        self.assertEqual(conditional_equip["eligibilityText"], "equipped with hot-shot lasgun")
        self.assertEqual(conditional_equip["choices"][0]["label"], "1 vox-caster")

        token_option = build_builder_catalog.parse_wargear_prompt(
            "For every 5 models in this unit, it can have 1 Aspect Shrine token."
        )
        self.assertEqual(token_option["selectionMode"], "allocation")
        self.assertEqual(token_option["choices"][0]["label"], "1 Aspect Shrine token")
        self.assertEqual(token_option["allocationLimit"], {"kind": "ratio", "perModels": 5, "maxPerStep": 1})

        hybrid_multi = build_builder_catalog.parse_wargear_prompt(
            "The Tactical Sergeant’s bolt pistol and boltgun can be replaced with 1 twin lightning claws, or two different weapons from the following list:*",
            ["1 bolt pistol", "1 power weapon"],
        )
        self.assertEqual(hybrid_multi["selectionMode"], "multi")
        self.assertEqual(hybrid_multi["pickCount"], 2)
        self.assertTrue(hybrid_multi["requireDistinct"])
        self.assertEqual(hybrid_multi["choices"][0]["label"], "1 twin lightning claws")
        self.assertEqual(hybrid_multi["choices"][0]["pickCost"], 2)

    def test_parse_wargear_prompt_supports_counted_allocations(self):
        allocation = build_builder_catalog.parse_wargear_prompt(
            "Any number of models can each have their twin shuriken catapult replaced with one of the following:"
        )
        self.assertEqual(allocation["selectionMode"], "allocation")
        self.assertEqual(allocation["action"], "replace")
        self.assertEqual(allocation["actor"], "Any number of models")
        self.assertEqual(allocation["target"], "twin shuriken catapult")
        self.assertEqual(allocation["allocationLimit"], {"kind": "modelCount"})

        up_to = build_builder_catalog.parse_wargear_prompt(
            "Up to 2 Storm Guardians can each have their bolt pistol replaced with one of the following:"
        )
        self.assertEqual(up_to["selectionMode"], "allocation")
        self.assertEqual(up_to["allocationLimit"], {"kind": "static", "max": 2})
        self.assertEqual(up_to["target"], "bolt pistol")

        for_every = build_builder_catalog.parse_wargear_prompt(
            "For every 5 models in this unit, 1 model’s Corsair firearm can be replaced with one of the following:"
        )
        self.assertEqual(for_every["selectionMode"], "allocation")
        self.assertEqual(for_every["allocationLimit"], {"kind": "ratio", "perModels": 5, "maxPerStep": 1})
        self.assertEqual(for_every["target"], "Corsair firearm")

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
            docs_root = Path(tmpdir) / "docs"
            source_cards_root = Path(tmpdir) / "cards"
            faction_dir = source_root / "test-faction"
            faction_dir.mkdir(parents=True)
            (source_cards_root / "test-faction").mkdir(parents=True)

            unit_one = {
                "exportSchemaVersion": 1,
                "parserVersion": "2026-03-19-durable-normalization-v1",
                "source": {
                    "url": "http://example/One",
                    "normalizedUrl": "http://example/One",
                    "canonicalSourceId": "wahapedia:one",
                    "faction_slug": "test-faction",
                    "datasheet_slug": "One",
                    "output_slug": "test-faction",
                    "fetchedAt": "2026-03-19T00:00:00+00:00",
                    "contentHash": "hash-one",
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
                "exportSchemaVersion": 1,
                "parserVersion": "2026-03-19-durable-normalization-v1",
                "source": {
                    "url": "http://example/Two",
                    "normalizedUrl": "http://example/Two",
                    "canonicalSourceId": "wahapedia:two",
                    "faction_slug": "test-faction",
                    "datasheet_slug": "Two",
                    "output_slug": "test-faction",
                    "fetchedAt": "2026-03-19T00:00:00+00:00",
                    "contentHash": "hash-two",
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
            (source_root / "export-manifest.json").write_text(
                json.dumps(
                    {
                        "exportSchemaVersion": 1,
                        "parserVersion": "2026-03-19-durable-normalization-v1",
                        "records": [
                            {
                                "outputSlug": "test-faction",
                                "datasheetSlug": "One",
                                "canonicalSourceId": "wahapedia:one",
                                "normalizedSourceUrl": "http://example/One",
                                "exportSchemaVersion": 1,
                                "parserVersion": "2026-03-19-durable-normalization-v1",
                                "sourceContentHash": "hash-one",
                                "sharedCoreHash": "shared-one",
                                "exportedSectionTitles": [],
                                "quality": {},
                            },
                            {
                                "outputSlug": "test-faction",
                                "datasheetSlug": "Two",
                                "canonicalSourceId": "wahapedia:two",
                                "normalizedSourceUrl": "http://example/Two",
                                "exportSchemaVersion": 1,
                                "parserVersion": "2026-03-19-durable-normalization-v1",
                                "sourceContentHash": "hash-two",
                                "sharedCoreHash": "shared-two",
                                "exportedSectionTitles": [],
                                "quality": {},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (source_cards_root / "test-faction" / "One.png").write_bytes(b"fake-png")

            manifest = build_builder_catalog.build_all(
                source_root,
                output_root,
                clean=True,
                source_cards_root=source_cards_root,
            )
            self.assertEqual(manifest["report"]["totals"]["factionCount"], 1)
            self.assertEqual(manifest["report"]["totals"]["unitCount"], 2)
            self.assertEqual(manifest["report"]["totals"]["missingStatsCount"], 1)
            self.assertEqual(manifest["report"]["totals"]["manualSelectionCount"], 0)
            self.assertEqual(manifest["report"]["totals"]["manualWargearCount"], 0)
            self.assertEqual(manifest["report"]["totals"]["sourceCardCopiedCount"], 1)
            self.assertEqual(manifest["report"]["totals"]["sourceCardMissingCount"], 1)
            self.assertTrue((output_root / "catalogs" / "test-faction.json").exists())
            self.assertTrue((output_root / "reports" / "build-report.json").exists())
            self.assertTrue((output_root / "manifest.json").exists())
            self.assertFalse((output_root / "source-cards").exists())
            self.assertEqual(manifest["factions"][0]["sourceCardCopiedCount"], 1)
            self.assertEqual(manifest["factions"][0]["sourceCardMissingCount"], 1)
            self.assertEqual(
                manifest["report"]["factions"][0]["missingSourceCards"][0]["name"],
                "Unit Two",
            )
            build_builder_catalog.publish_docs_data(output_root, docs_root)
            build_builder_catalog.publish_source_cards(docs_root, source_cards_root)
            self.assertTrue((docs_root / "source-cards" / "test-faction" / "One.png").exists())

    def test_build_all_fails_on_stale_export_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            output_root = Path(tmpdir) / "out"
            source_cards_root = Path(tmpdir) / "cards"
            faction_dir = source_root / "test-faction"
            faction_dir.mkdir(parents=True)
            source_cards_root.mkdir(parents=True)

            card = {
                "exportSchemaVersion": 0,
                "parserVersion": "old-parser",
                "source": {
                    "url": "http://example/One",
                    "normalizedUrl": "http://example/One",
                    "canonicalSourceId": "wahapedia:one",
                    "faction_slug": "test-faction",
                    "datasheet_slug": "One",
                    "output_slug": "test-faction",
                },
                "name": "Unit One",
                "characteristics": {"M": '6"', "T": "4", "Sv": "3+", "W": "2", "Ld": "7+", "OC": "1"},
                "weapons": {"ranged_weapons": [], "melee_weapons": []},
                "abilities": {"core": [], "faction": [], "datasheet": [], "other": []},
                "unit_composition": [{"type": "list", "items": ["5 Unit One"]}],
                "keywords": ["INFANTRY"],
                "faction_keywords": ["TEST"],
                "sections": [],
            }
            (faction_dir / "index.json").write_text(json.dumps([card]), encoding="utf-8")
            (source_root / "export-manifest.json").write_text(
                json.dumps(
                    {
                        "exportSchemaVersion": 0,
                        "parserVersion": "old-parser",
                        "records": [
                            {
                                "outputSlug": "test-faction",
                                "datasheetSlug": "One",
                                "canonicalSourceId": "wahapedia:one",
                                "normalizedSourceUrl": "http://example/One",
                                "exportSchemaVersion": 0,
                                "parserVersion": "old-parser",
                                "sharedCoreHash": "hash-one",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "schema version mismatch"):
                build_builder_catalog.build_all(source_root, output_root, source_cards_root=source_cards_root)

    def test_build_all_fails_on_duplicate_source_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            output_root = Path(tmpdir) / "out"
            source_cards_root = Path(tmpdir) / "cards"
            for faction_slug in ("space-marines", "ultramarines"):
                faction_dir = source_root / faction_slug
                faction_dir.mkdir(parents=True)
                card = {
                    "exportSchemaVersion": 1,
                    "parserVersion": "2026-03-19-durable-normalization-v1",
                    "source": {
                        "url": "http://example/shared",
                        "normalizedUrl": "http://example/shared",
                        "canonicalSourceId": "wahapedia:shared",
                        "faction_slug": faction_slug,
                        "datasheet_slug": "Terminator-Squad",
                        "output_slug": faction_slug,
                    },
                    "name": "Terminator Squad",
                    "characteristics": {"M": '5"', "T": "5", "Sv": "2+", "W": "3", "Ld": "6+", "OC": "1"},
                    "weapons": {"ranged_weapons": [], "melee_weapons": []},
                    "abilities": {"core": [], "faction": [], "datasheet": [], "other": []},
                    "unit_composition": [{"type": "list", "items": ["5 Terminators"]}],
                    "keywords": ["INFANTRY"],
                    "faction_keywords": ["ADEPTUS ASTARTES"],
                    "sections": [],
                }
                (faction_dir / "index.json").write_text(json.dumps([card]), encoding="utf-8")

            (source_root / "export-manifest.json").write_text(
                json.dumps(
                    {
                        "exportSchemaVersion": 1,
                        "parserVersion": "2026-03-19-durable-normalization-v1",
                        "records": [
                            {
                                "outputSlug": "space-marines",
                                "datasheetSlug": "Terminator-Squad",
                                "canonicalSourceId": "wahapedia:shared",
                                "normalizedSourceUrl": "http://example/shared",
                                "exportSchemaVersion": 1,
                                "parserVersion": "2026-03-19-durable-normalization-v1",
                                "sharedCoreHash": "hash-a",
                            },
                            {
                                "outputSlug": "ultramarines",
                                "datasheetSlug": "Terminator-Squad",
                                "canonicalSourceId": "wahapedia:shared",
                                "normalizedSourceUrl": "http://example/shared",
                                "exportSchemaVersion": 1,
                                "parserVersion": "2026-03-19-durable-normalization-v1",
                                "sharedCoreHash": "hash-b",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate canonical-source drift detected"):
                build_builder_catalog.build_all(
                    source_root,
                    output_root,
                    factions=["space-marines", "ultramarines"],
                    source_cards_root=source_cards_root,
                )

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
        multi_group = next(group for group in unit["wargear"]["options"] if group["selectionMode"] == "multi")
        self.assertEqual(multi_group["pickCount"], 2)
        self.assertFalse(unit["wargear"]["hasManualOptions"])

    def test_real_repo_marine_family_regressions_regain_wargear_sections(self):
        samples = [
            ("space-marines", "Terminator-Squad.json"),
            ("space-marines", "Devastator-Squad.json"),
            ("ultramarines", "Intercessor-Squad.json"),
            ("ultramarines", "Terminator-Squad.json"),
            ("ultramarines", "Devastator-Squad.json"),
            ("dark-angels", "Terminator-Squad.json"),
            ("space-wolves", "Captain.json"),
            ("space-wolves", "Intercessor-Squad.json"),
            ("space-wolves", "Terminator-Squad.json"),
        ]

        for faction_slug, filename in samples:
            card = json.loads((ROOT / "out" / "json" / faction_slug / filename).read_text(encoding="utf-8"))
            section_titles = [section["title"] for section in card.get("sections", [])]
            self.assertIn("WARGEAR OPTIONS", section_titles, filename)
            unit, diagnostics = build_builder_catalog.normalize_card(faction_slug, card)
            self.assertTrue(
                unit["wargear"]["options"] or unit["wargear"]["manualNotes"] or diagnostics["manualWargear"],
                filename,
            )

    def test_real_repo_fixed_wargear_prompt_is_structured(self):
        card = json.loads((ROOT / "out" / "json" / "aeldari" / "Farseer.json").read_text(encoding="utf-8"))
        unit, diagnostics = build_builder_catalog.normalize_card("aeldari", card)
        self.assertEqual(unit["wargear"]["options"][0]["selectionMode"], "single")
        self.assertEqual(unit["wargear"]["options"][0]["choices"][0]["label"], "1 singing spear")
        self.assertFalse(diagnostics["manualWargear"])

    def test_real_repo_cloud_dancer_band_uses_allocation_wargear(self):
        card = json.loads((ROOT / "out" / "json" / "aeldari" / "Corsair-Cloud-Dancer-Band.json").read_text(encoding="utf-8"))
        unit, diagnostics = build_builder_catalog.normalize_card("aeldari", card)
        allocation_group = unit["wargear"]["options"][0]
        self.assertEqual(allocation_group["selectionMode"], "allocation")
        self.assertEqual(allocation_group["action"], "replace")
        self.assertEqual(allocation_group["target"], "twin shuriken catapult")
        self.assertEqual(allocation_group["choices"][0]["label"], "1 dark lance")
        self.assertFalse(diagnostics["manualWargear"])

    def test_real_repo_bike_squad_and_corsairs_use_structured_allocations(self):
        bike_card = json.loads((ROOT / "out" / "json" / "dark-angels" / "Bike-Squad.json").read_text(encoding="utf-8"))
        bike_unit, bike_diag = build_builder_catalog.normalize_card("dark-angels", bike_card)
        bike_group = next(group for group in bike_unit["wargear"]["options"] if "up to 2 space marine bikers" in group["label"].lower())
        self.assertEqual(bike_group["selectionMode"], "allocation")
        self.assertEqual(bike_group["allocationLimit"], {"kind": "static", "max": 2})
        self.assertFalse(bike_diag["manualWargear"])

        corsair_card = json.loads((ROOT / "out" / "json" / "aeldari" / "Corsair-Reaver-Band.json").read_text(encoding="utf-8"))
        corsair_unit, corsair_diag = build_builder_catalog.normalize_card("aeldari", corsair_card)
        corsair_group = next(group for group in corsair_unit["wargear"]["options"] if "for every 5 models" in group["label"].lower())
        self.assertEqual(corsair_group["selectionMode"], "allocation")
        self.assertEqual(corsair_group["allocationLimit"], {"kind": "ratio", "perModels": 5, "maxPerStep": 1})
        self.assertFalse(corsair_diag["manualWargear"])

    def test_real_repo_sampled_problem_units_use_structured_wargear(self):
        samples = [
            ("aeldari", "Dark-Reapers.json", lambda unit: next(group for group in unit["wargear"]["options"] if "aspect shrine token" in group["label"].lower())["selectionMode"] == "allocation"),
            ("astra-militarum", "Kasrkin.json", lambda unit: any(group.get("poolKey") == "kasrkin-trooper-hot-shot-lasgun" for group in unit["wargear"]["options"])),
            ("death-guard", "Plague-Marines.json", lambda unit: any(group.get("poolKey") == "plague-marine-boltgun" for group in unit["wargear"]["options"])),
            ("drukhari", "Talos.json", lambda unit: all(group["selectionMode"] == "allocation" for group in unit["wargear"]["options"])),
            ("dark-angels", "Devastator-Squad.json", lambda unit: any(group["selectionMode"] == "multi" for group in unit["wargear"]["options"])),
            ("aeldari", "Corsair-Skyreavers.json", lambda unit: all(group["selectionMode"] != "manual" for group in unit["wargear"]["options"])),
        ]

        for faction_slug, filename, predicate in samples:
            card = json.loads((ROOT / "out" / "json" / faction_slug / filename).read_text(encoding="utf-8"))
            unit, diagnostics = build_builder_catalog.normalize_card(faction_slug, card)
            self.assertTrue(predicate(unit), filename)
            self.assertFalse(diagnostics["manualWargear"], filename)

    def test_real_repo_manual_wargear_residual_count_stays_bounded_by_canonical_source(self):
        manual_units: dict[str, tuple[str, str]] = {}
        for faction_dir in sorted((ROOT / "out" / "json").iterdir()):
            if not faction_dir.is_dir():
                continue
            index_path = faction_dir / "index.json"
            if not index_path.exists():
                continue
            cards = json.loads(index_path.read_text(encoding="utf-8"))
            for card in cards:
                unit, diagnostics = build_builder_catalog.normalize_card(faction_dir.name, card)
                if diagnostics["manualWargear"]:
                    source = card.get("source", {})
                    canonical_key = source.get("canonicalSourceId") or source.get("url")
                    manual_units.setdefault(canonical_key, (faction_dir.name, unit["name"]))

        self.assertLessEqual(len(manual_units), 10, sorted(manual_units.values()))


class BuilderAppSmokeTests(unittest.TestCase):
    def test_builder_page_references_generated_manifest_and_renderer(self):
        html_path = ROOT / "docs" / "builder" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("./data/manifest.json", html)
        self.assertIn("./card_renderer.js?v=", html)
        self.assertIn("./roster_store.js?v=", html)
        self.assertIn("./app.js?v=", html)
        self.assertIn("WahBuilderCardRenderer.renderCard", html)
        self.assertIn("Print roster cards", html)
        self.assertIn("Import JSON", html)
        self.assertIn("Export JSON", html)
        self.assertIn("Saved rosters", html)
        self.assertIn("battle-size-select", html)
        self.assertIn("legality-summary", html)
        self.assertIn('data-action="warlord-select"', html)
        self.assertIn('data-action="attachment-select"', html)
        self.assertIn('data-action="embark-select"', html)
        self.assertIn('data-action="wargear-multi-toggle"', html)
        self.assertIn("Legal foundation checks passed", html)
        self.assertIn('window.location.protocol === "file:"', html)
        self.assertIn("Original Wahapedia", html)
        self.assertIn("./data/source-cards/", html)


if __name__ == "__main__":
    unittest.main()
