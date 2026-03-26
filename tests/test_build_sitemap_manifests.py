import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

SITEMAP_MODULE_PATH = ROOT / "scripts" / "build_sitemap_manifests.py"
sitemap_spec = importlib.util.spec_from_file_location(
    "build_sitemap_manifests",
    SITEMAP_MODULE_PATH,
)
build_sitemap_manifests = importlib.util.module_from_spec(sitemap_spec)
assert sitemap_spec.loader is not None
sitemap_spec.loader.exec_module(build_sitemap_manifests)

BUILD_SITE_MODULE_PATH = ROOT / "scripts" / "build_builder_site.py"
build_site_spec = importlib.util.spec_from_file_location(
    "build_builder_site",
    BUILD_SITE_MODULE_PATH,
)
build_builder_site = importlib.util.module_from_spec(build_site_spec)
assert build_site_spec.loader is not None
build_site_spec.loader.exec_module(build_builder_site)

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "wahapedia_sitemap.xml"


class BuildSitemapManifestsTests(unittest.TestCase):
    def setUp(self):
        self.fixture_xml = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_manifests_from_sitemap_keeps_only_canonical_datasheets(self):
        manifests = build_sitemap_manifests.manifests_from_sitemap(self.fixture_xml)

        self.assertEqual(
            manifests["aeldari"],
            [
                {
                    "name": "",
                    "href": "http://wahapedia.ru/wh40k10ed/factions/aeldari/Avatar-of-Khaine",
                },
                {
                    "name": "",
                    "href": "http://wahapedia.ru/wh40k10ed/factions/aeldari/Wardens-of-Ultramar-1",
                },
            ],
        )
        self.assertEqual(
            manifests["leagues-of-votann"],
            [
                {
                    "name": "",
                    "href": "http://wahapedia.ru/wh40k10ed/factions/leagues-of-votann/Berehk-Stornbröw",
                }
            ],
        )
        self.assertEqual(
            manifests["space-marines"],
            [
                {
                    "name": "",
                    "href": "http://wahapedia.ru/wh40k10ed/factions/space-marines/Captain-Titus",
                }
            ],
        )

    def test_selected_manifests_rejects_noncanonical_output_slug(self):
        manifests = build_sitemap_manifests.manifests_from_sitemap(self.fixture_xml)
        with self.assertRaises(SystemExit) as context:
            build_sitemap_manifests.selected_manifests(
                manifests,
                ["space-wolves"],
            )
        self.assertIn("browser-based manifest generation path", str(context.exception))

    def test_write_manifests_writes_existing_manifest_shape(self):
        manifests = build_sitemap_manifests.selected_manifests(
            build_sitemap_manifests.manifests_from_sitemap(self.fixture_xml),
            ["aeldari"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            written = build_sitemap_manifests.write_manifests(manifests, Path(tmpdir))
            self.assertEqual(len(written), 1)
            payload = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                [
                    {
                        "name": "",
                        "href": "http://wahapedia.ru/wh40k10ed/factions/aeldari/Avatar-of-Khaine",
                    },
                    {
                        "name": "",
                        "href": "http://wahapedia.ru/wh40k10ed/factions/aeldari/Wardens-of-Ultramar-1",
                    },
                ],
            )


class BuildBuilderSiteHookTests(unittest.TestCase):
    def test_main_invokes_sitemap_refresh_only_when_requested(self):
        args = SimpleNamespace(
            export_output_slug=[],
            refresh_sitemap_manifest=["aeldari", "adeptus-custodes"],
            build_faction=[],
            clean=False,
            render_example_html=False,
            export_workers=4,
        )

        with mock.patch.object(build_builder_site, "parse_args", return_value=args), mock.patch.object(
            build_builder_site,
            "discover_impacted_output_slugs",
            return_value=[],
        ), mock.patch.object(build_builder_site, "run_command") as run_command:
            build_builder_site.main()

        self.assertEqual(
            run_command.call_args_list[0].args[0],
            [
                build_builder_site.PYTHON,
                "scripts/build_sitemap_manifests.py",
                "--output-slug",
                "aeldari",
                "--output-slug",
                "adeptus-custodes",
            ],
        )

    def test_main_preserves_existing_behavior_without_sitemap_refresh(self):
        args = SimpleNamespace(
            export_output_slug=["aeldari"],
            refresh_sitemap_manifest=[],
            build_faction=[],
            clean=False,
            render_example_html=False,
            export_workers=4,
        )

        with mock.patch.object(build_builder_site, "parse_args", return_value=args), mock.patch.object(
            build_builder_site,
            "discover_impacted_output_slugs",
            return_value=["aeldari"],
        ), mock.patch.object(build_builder_site, "run_command") as run_command:
            build_builder_site.main()

        called_commands = [call.args[0] for call in run_command.call_args_list]
        self.assertNotIn(
            [build_builder_site.PYTHON, "scripts/build_sitemap_manifests.py"],
            called_commands,
        )
        self.assertEqual(
            called_commands[0],
            [
                build_builder_site.PYTHON,
                "scripts/export_datasheet_json.py",
                "--output-slug",
                "aeldari",
                "--workers",
                "4",
            ],
        )


if __name__ == "__main__":
    unittest.main()
