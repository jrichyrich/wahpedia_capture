const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadRenderer() {
    const scriptPath = path.join(__dirname, "..", "docs", "builder", "card_renderer.js");
    const source = fs.readFileSync(scriptPath, "utf8");
    const context = {
        window: {},
        globalThis: {},
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(source, context);
    return context.window.WahBuilderCardRenderer;
}

test("renderCard shows current loadout chips and weapon highlight badges", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Farseer",
        stats: { M: '7"', T: "3", Sv: "6+", W: "3", Ld: "6+", OC: "1", invulnerableSave: "4+" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "1-model", label: "1 model", points: 70, selectionKind: "models" }],
        weapons: {
            ranged: [
                { name: "Shuriken pistol", range: '12"', a: "1", skill: "3+", s: "4", ap: "-1", d: "1", abilities: [] },
                { name: "Singing spear", range: '12"', a: "1", skill: "3+", s: "9", ap: "-2", d: "3", abilities: [] },
            ],
            melee: [
                { name: "Singing spear", range: "Melee", a: "3", skill: "3+", s: "9", ap: "-2", d: "3", abilities: [] },
                { name: "Witchblade", range: "Melee", a: "3", skill: "3+", s: "3", ap: "0", d: "D3", abilities: [] },
            ],
        },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["1 Farseer"] },
        keywords: ["INFANTRY", "PSYKER"],
        factionKeywords: ["AELDARI"],
    };

    const html = renderer.renderCard(unit, {
        selectedOption: unit.pointsOptions[0],
        selectedUpgrades: [{ id: "relic", label: "Runes of Witnessing", points: 15, selectionKind: "upgrade" }],
        selectedWargear: [
            {
                group: { target: "This model’s witchblade", label: "Witchblade swap" },
                selectedChoice: { id: "spear", label: "1 singing spear" },
            },
        ],
        manualWargearGroups: [],
    });

    assert.match(html, /Current Loadout/);
    assert.match(html, /Runes of Witnessing/);
    assert.match(html, /weapon-choice-badge-selected/);
    assert.match(html, /weapon-choice-badge-replaced/);
    assert.match(html, /Singing spear/);
    assert.match(html, /Witchblade/);
});
