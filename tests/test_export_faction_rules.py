import importlib.util
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "export_faction_rules.py"

spec = importlib.util.spec_from_file_location("export_faction_rules", MODULE_PATH)
export_faction_rules = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(export_faction_rules)


def faction_fixture(detachment_name: str, army_rule_name: str, enhancement_name: str, stratagem_name: str) -> str:
    return f"""
    <html>
      <body>
        <h2>Introduction</h2>
        <div>Intro text.</div>
        <h2>Army Rules</h2>
        <div>
          <h3>{army_rule_name}</h3>
          <div>Army rule body text.</div>
        </div>
        <h2>{detachment_name}</h2>
        <div>This detachment rewards aggressive play.</div>
        <div class="Columns2">
          <h3>Detachment Rule</h3>
          <h4>Battle Temper</h4>
          <div>Detachment rule body text.</div>
          <h3>Enhancements</h3>
          <table>
            <tr><td>{enhancement_name}</td><td>25 pts</td><td>Character model only. Gain a bonus.</td></tr>
          </table>
        </div>
        <div class="BreakInsideAvoid">
          <h3>Stratagems</h3>
          <div>
            {stratagem_name}
            <div>1CP</div>
            <div>{detachment_name} – Battle Tactic Stratagem</div>
            <div>WHEN: Your opponent's Shooting phase, just after an enemy unit has selected its targets.</div>
            <div>TARGET: One CHARACTER unit from your army.</div>
            <div>EFFECT: Until the end of the phase, improve invulnerable saves by 1.</div>
          </div>
        </div>
      </body>
    </html>
    """


def wahapedia_markup_fixture() -> str:
    return """
    <html>
      <body>
        <h2>Introduction</h2>
        <div>Intro text.</div>
        <h2>Army Rules</h2>
        <div>
          <h3>Martial Ka'tah</h3>
          <div>Army rule body text.</div>
        </div>
        <h2>Shield Host</h2>
        <div>This detachment rewards aggressive play.</div>
        <div class="BreakInsideAvoid">
          <h3>Stratagems</h3>
          <div class="str10Wrap BreakInsideAvoid str10ColorYour">
            <div class="str10Name">MULTIPOTENTIALITY</div>
            <div class="str10Border">
              <div class="str10DiamondWrap">1CP</div>
              <div class="str10Type">Shield Host – Strategic Ploy Stratagem</div>
              <div class="str10Legend ShowFluff">Flavor text.</div>
              <div class="str10Text">
                <span class="str10ColorYour">WHEN:</span>
                Your <a>Movement phase</a>.
                <span class="str10ColorYour">TARGET:</span>
                One ADEPTUS CUSTODES unit from your army that Fell Back this phase.
                <span class="str10ColorYour">EFFECT:</span>
                Until the end of your turn, that unit is eligible to shoot and declare a charge in a turn in which it Fell Back.
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """


class ExportFactionRulesTests(unittest.TestCase):
    def test_parse_adeptus_custodes_fixture(self):
        rules = export_faction_rules.parse_faction_page_html(
            faction_fixture("Shield Host", "Martial Ka'tah", "From the Hall of Armouries", "Arcane Genetic Alchemy"),
            source_url="http://example/adeptus-custodes",
        )
        self.assertEqual(rules["armyRules"][0]["name"], "Martial Ka'tah")
        self.assertEqual(rules["detachments"][0]["name"], "Shield Host")
        self.assertEqual(rules["detachments"][0]["enhancements"][0]["points"], 25)
        self.assertEqual(rules["detachments"][0]["stratagems"][0]["cp"], 1)

    def test_parse_space_wolves_fixture(self):
        rules = export_faction_rules.parse_faction_page_html(
            faction_fixture("Champions of Fenris", "Oath of Moment", "Black Death", "Pack Hunters"),
            source_url="http://example/space-wolves",
        )
        self.assertEqual(rules["detachments"][0]["id"], "champions-of-fenris")
        self.assertEqual(rules["detachments"][0]["rule"]["name"], "Battle Temper")
        self.assertEqual(rules["detachments"][0]["stratagems"][0]["kind"], "Battle Tactic")
        self.assertEqual(rules["detachments"][0]["stratagems"][0]["phaseTags"], ["shooting", "opponent"])

    def test_parse_non_imperium_fixture(self):
        rules = export_faction_rules.parse_faction_page_html(
            faction_fixture("Skysplinter Assault", "Power from Pain", "Nightmare Shroud", "Prey on the Weak"),
            source_url="http://example/drukhari",
        )
        self.assertEqual(rules["armyRules"][0]["sourceUrl"], "http://example/drukhari")
        self.assertEqual(rules["detachments"][0]["enhancements"][0]["eligibilityText"], "Character model only.")
        self.assertEqual(rules["detachments"][0]["stratagems"][0]["target"], "One CHARACTER unit from your army.")

    def test_parse_wahapedia_markup_stratagem_name_from_wrapper(self):
        soup = BeautifulSoup(wahapedia_markup_fixture(), "html.parser")
        section = soup.find("div", class_="BreakInsideAvoid")
        stratagem = export_faction_rules.parse_stratagems(section)[0]
        self.assertEqual(stratagem["name"], "MULTIPOTENTIALITY")
        self.assertEqual(stratagem["cp"], 1)
        self.assertEqual(stratagem["kind"], "Strategic Ploy")


if __name__ == "__main__":
    unittest.main()
