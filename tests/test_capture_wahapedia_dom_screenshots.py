import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "capture_wahapedia_dom_screenshots.py"

spec = importlib.util.spec_from_file_location("capture_wahapedia_dom_screenshots", MODULE_PATH)
capture_wahapedia_dom_screenshots = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(capture_wahapedia_dom_screenshots)


class CaptureWahapediaDomScreenshotsTests(unittest.TestCase):
    def test_cooldown_from_jina_error_parses_reader_timestamp(self):
        value = capture_wahapedia_dom_screenshots.cooldown_from_jina_error(
            "Anonymous access to domain wahapedia.ru blocked until "
            "Fri May 29 2026 19:02:41 GMT+0000 (Coordinated Universal Time) due to previous abuse"
        )

        self.assertEqual(value, datetime(2026, 5, 29, 19, 2, 41, tzinfo=timezone.utc))

    def test_find_datasheet_crop_box_discards_page_chrome_and_footer(self):
        image = Image.new("RGB", (1280, 900), (238, 238, 238))
        draw = ImageDraw.Draw(image)
        draw.rectangle((116, 40, 1137, 105), fill=(255, 255, 255))
        draw.rectangle((116, 145, 1115, 360), fill=(255, 255, 255))
        draw.rectangle((116, 190, 1115, 240), fill=(16, 16, 16))
        draw.rectangle((116, 300, 720, 348), fill=(2, 82, 112))
        draw.rectangle((116, 700, 1115, 850), fill=(255, 255, 255))
        draw.rectangle((1170, 860, 1240, 895), fill=(20, 20, 20))

        left, top, right, bottom = capture_wahapedia_dom_screenshots.find_datasheet_crop_box(image)

        self.assertLessEqual(left, 116)
        self.assertGreaterEqual(right, 1115)
        self.assertEqual(top, 190)
        self.assertGreater(bottom, 340)
        self.assertLess(bottom, 650)

    def test_find_datasheet_crop_box_stops_before_feature_sections(self):
        image = Image.new("RGB", (1280, 1100), (238, 238, 238))
        draw = ImageDraw.Draw(image)
        draw.rectangle((116, 145, 1115, 900), fill=(255, 255, 255))
        draw.rectangle((116, 190, 1115, 240), fill=(16, 16, 16))
        draw.rectangle((116, 360, 720, 388), fill=(3, 74, 105))
        for y in range(430, 700, 70):
            draw.rectangle((140, y, 640, y + 8), fill=(20, 20, 20))
        draw.rectangle((116, 720, 1115, 780), fill=(255, 255, 255))
        draw.rectangle((116, 820, 720, 850), fill=(3, 74, 105))
        for y in range(865, 1015, 42):
            draw.rectangle((136, y, 700, y + 34), fill=(0, 112, 151))

        _, _, _, bottom = capture_wahapedia_dom_screenshots.find_datasheet_crop_box(image)

        self.assertGreater(bottom, 760)
        self.assertLessEqual(bottom, 820)

    def test_crop_datasheet_screenshot_can_trim_already_cropped_card(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.png"
            destination = Path(tmpdir) / "destination.png"
            image = Image.new("RGB", (1000, 900), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 999, 58), fill=(3, 74, 105))
            draw.rectangle((10, 320, 620, 348), fill=(3, 74, 105))
            draw.rectangle((10, 610, 620, 640), fill=(3, 74, 105))
            for y in range(655, 800, 42):
                draw.rectangle((28, y, 600, y + 34), fill=(0, 112, 151))
            image.save(source)

            capture_wahapedia_dom_screenshots.crop_datasheet_screenshot(source, destination)

            cropped = Image.open(destination)
            self.assertEqual(cropped.width, 1000)
            self.assertLessEqual(cropped.height, 610)
            self.assertGreater(cropped.height, 550)

    def test_capture_all_fetches_from_manifest_and_crops_pageshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "out" / "source"
            source_root.mkdir(parents=True)
            (source_root / "imperial-knights-links.json").write_text(
                '[{"name":"Canis Rex","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/Canis-Rex"}]',
                encoding="utf-8",
            )
            args = SimpleNamespace(
                output_slug="imperial-knights",
                source_root="out/source",
                out_root="out/factions",
                card_slug=[],
                raw_dir="out/raw-dom",
                mode="pageshot",
                no_crop=False,
                timeout=1,
                attempts=1,
                delay=0,
                skip_existing=False,
            )
            screenshot = Image.new("RGB", (1280, 500), (238, 238, 238))
            draw = ImageDraw.Draw(screenshot)
            draw.rectangle((116, 145, 1115, 360), fill=(255, 255, 255))
            draw.rectangle((116, 190, 1115, 240), fill=(16, 16, 16))
            raw_path = root / "fixture.png"
            screenshot.save(raw_path)

            with mock.patch.object(Path, "cwd", return_value=root), mock.patch.object(
                capture_wahapedia_dom_screenshots,
                "fetch_jina_screenshot",
                return_value=raw_path.read_bytes(),
            ) as fetch_jina_screenshot:
                result = capture_wahapedia_dom_screenshots.capture_all(args)

            self.assertEqual(result, 0)
            self.assertTrue((root / "out" / "factions" / "imperial-knights" / "Canis-Rex.png").exists())
            fetch_jina_screenshot.assert_called_once()
            self.assertEqual(fetch_jina_screenshot.call_args.args[0], "http://wahapedia.ru/wh40k10ed/factions/imperial-knights/Canis-Rex")

    def test_capture_all_stops_after_temporary_jina_block(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "out" / "source"
            source_root.mkdir(parents=True)
            (source_root / "imperial-knights-links.json").write_text(
                """
                [
                  {"name":"One","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/One"},
                  {"name":"Two","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/Two"}
                ]
                """,
                encoding="utf-8",
            )
            args = SimpleNamespace(
                output_slug="imperial-knights",
                source_root="out/source",
                out_root="out/factions",
                card_slug=[],
                raw_dir=None,
                mode="pageshot",
                no_crop=False,
                timeout=1,
                attempts=1,
                delay=0,
                skip_existing=False,
            )

            with mock.patch.object(Path, "cwd", return_value=root), mock.patch.object(
                capture_wahapedia_dom_screenshots,
                "fetch_jina_screenshot",
                side_effect=capture_wahapedia_dom_screenshots.JinaTemporaryBlockError("blocked until later"),
            ) as fetch_jina_screenshot:
                result = capture_wahapedia_dom_screenshots.capture_all(args)

            self.assertEqual(result, 1)
            fetch_jina_screenshot.assert_called_once()
            failures = (source_root / "imperial-knights-dom-screenshot-failures.json").read_text(
                encoding="utf-8"
            )
            self.assertIn("blocked until later", failures)

    def test_capture_all_can_skip_existing_screenshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "out" / "source"
            source_root.mkdir(parents=True)
            output_dir = root / "out" / "factions" / "imperial-knights"
            output_dir.mkdir(parents=True)
            (output_dir / "One.png").write_bytes(b"existing")
            (source_root / "imperial-knights-links.json").write_text(
                '[{"name":"One","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/One"}]',
                encoding="utf-8",
            )
            args = SimpleNamespace(
                output_slug="imperial-knights",
                source_root="out/source",
                out_root="out/factions",
                card_slug=[],
                raw_dir=None,
                mode="pageshot",
                no_crop=False,
                timeout=1,
                attempts=1,
                delay=0,
                skip_existing=True,
            )

            with mock.patch.object(Path, "cwd", return_value=root), mock.patch.object(
                capture_wahapedia_dom_screenshots,
                "fetch_jina_screenshot",
            ) as fetch_jina_screenshot:
                result = capture_wahapedia_dom_screenshots.capture_all(args)

            self.assertEqual(result, 0)
            fetch_jina_screenshot.assert_not_called()

    def test_capture_until_complete_captures_one_and_copies_to_docs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "out" / "source"
            source_root.mkdir(parents=True)
            (source_root / "imperial-knights-links.json").write_text(
                '[{"name":"One","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/One"}]',
                encoding="utf-8",
            )
            args = SimpleNamespace(
                output_slug="imperial-knights",
                source_root="out/source",
                out_root="out/factions",
                card_slug=[],
                raw_dir="out/raw-dom/imperial-knights",
                mode="pageshot",
                no_crop=False,
                timeout=1,
                attempts=1,
                delay=0,
                skip_existing=False,
                cooldown_buffer_seconds=0,
                docs_source_cards_root="docs/builder/data/source-cards",
            )
            screenshot = Image.new("RGB", (1280, 500), (238, 238, 238))
            draw = ImageDraw.Draw(screenshot)
            draw.rectangle((116, 145, 1115, 360), fill=(255, 255, 255))
            draw.rectangle((116, 190, 1115, 240), fill=(16, 16, 16))
            raw_path = root / "fixture.png"
            screenshot.save(raw_path)

            with mock.patch.object(Path, "cwd", return_value=root), mock.patch.object(
                capture_wahapedia_dom_screenshots,
                "fetch_jina_screenshot",
                return_value=raw_path.read_bytes(),
            ):
                result = capture_wahapedia_dom_screenshots.capture_until_complete(args)

            self.assertEqual(result, 0)
            self.assertTrue((root / "out" / "raw-dom" / "imperial-knights" / "One.png").exists())
            self.assertTrue((root / "out" / "factions" / "imperial-knights" / "One.png").exists())
            self.assertTrue(
                (root / "docs" / "builder" / "data" / "source-cards" / "imperial-knights" / "One.png").exists()
            )

    def test_capture_next_missing_once_skips_raw_cache_and_copies_to_docs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "out" / "source"
            source_root.mkdir(parents=True)
            raw_dir = root / "out" / "raw-dom" / "imperial-knights"
            raw_dir.mkdir(parents=True)
            (raw_dir / "One.png").write_bytes(b"existing")
            (source_root / "imperial-knights-links.json").write_text(
                """
                [
                  {"name":"One","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/One"},
                  {"name":"Two","href":"http://wahapedia.ru/wh40k10ed/factions/imperial-knights/Two"}
                ]
                """,
                encoding="utf-8",
            )
            args = SimpleNamespace(
                output_slug="imperial-knights",
                source_root="out/source",
                out_root="out/factions",
                card_slug=[],
                raw_dir="out/raw-dom/imperial-knights",
                mode="pageshot",
                no_crop=False,
                timeout=1,
                attempts=1,
                delay=0,
                skip_existing=False,
                cooldown_buffer_seconds=0,
                docs_source_cards_root="docs/builder/data/source-cards",
            )
            screenshot = Image.new("RGB", (1280, 500), (238, 238, 238))
            draw = ImageDraw.Draw(screenshot)
            draw.rectangle((116, 145, 1115, 360), fill=(255, 255, 255))
            draw.rectangle((116, 190, 1115, 240), fill=(16, 16, 16))
            raw_path = root / "fixture.png"
            screenshot.save(raw_path)

            with mock.patch.object(Path, "cwd", return_value=root), mock.patch.object(
                capture_wahapedia_dom_screenshots,
                "fetch_jina_screenshot",
                return_value=raw_path.read_bytes(),
            ) as fetch_jina_screenshot:
                result = capture_wahapedia_dom_screenshots.capture_next_missing_once(args)

            self.assertEqual(result, 0)
            fetch_jina_screenshot.assert_called_once()
            self.assertEqual(
                fetch_jina_screenshot.call_args.args[0],
                "http://wahapedia.ru/wh40k10ed/factions/imperial-knights/Two",
            )
            self.assertTrue((root / "out" / "raw-dom" / "imperial-knights" / "Two.png").exists())
            self.assertTrue(
                (root / "docs" / "builder" / "data" / "source-cards" / "imperial-knights" / "Two.png").exists()
            )


if __name__ == "__main__":
    unittest.main()
