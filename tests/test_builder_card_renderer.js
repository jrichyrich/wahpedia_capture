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

test("renderCard print-clean mode hides replaced weapon rows when selection is resolved", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Farseer",
        stats: { M: '7"', T: "3", Sv: "6+", W: "3", Ld: "6+", OC: "1" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "1-model", label: "1 model", points: 70, selectionKind: "models" }],
        weapons: {
            ranged: [{ name: "Singing spear", range: '12"', a: "1", skill: "3+", s: "9", ap: "-2", d: "3", abilities: [] }],
            melee: [
                { name: "Singing spear", range: "Melee", a: "3", skill: "3+", s: "9", ap: "-2", d: "3", abilities: [] },
                { name: "Witchblade", range: "Melee", a: "3", skill: "3+", s: "3", ap: "0", d: "D3", abilities: [] },
            ],
        },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["1 Farseer"] },
        keywords: [],
        factionKeywords: ["AELDARI"],
    };

    const html = renderer.renderCard(unit, {
        renderMode: "print-clean",
        selectedOption: unit.pointsOptions[0],
        selectedWargear: [
            {
                group: { target: "This model’s witchblade", label: "Witchblade swap" },
                selectedChoice: { id: "spear", label: "1 singing spear" },
            },
        ],
        manualWargearGroups: [],
    });

    assert.match(html, /Current Loadout/);
    assert.match(html, /Singing spear/);
    assert.doesNotMatch(html, /Witchblade/);
    assert.doesNotMatch(html, /weapon-choice-badge-replaced/);
});

test("renderCard uses additive loadout wording for equip-style wargear", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Anathema Psykana Rhino",
        stats: { M: '12"', T: "9", Sv: "3+", W: "10", Ld: "6+", OC: "2" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "1-model", label: "1 model", points: 75, selectionKind: "models" }],
        weapons: {
            ranged: [
                { name: "Hunter-killer missile one shot", range: '48"', a: "1", skill: "2+", s: "14", ap: "-3", d: "D6", abilities: [] },
                { name: "Storm bolter", range: '24"', a: "2", skill: "3+", s: "4", ap: "0", d: "1", abilities: [] },
            ],
            melee: [
                { name: "Armoured tracks", range: "Melee", a: "3", skill: "4+", s: "6", ap: "0", d: "1", abilities: [] },
            ],
        },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["1 Anathema Psykana Rhino"] },
        keywords: ["VEHICLE"],
        factionKeywords: ["ADEPTUS CUSTODES"],
    };

    const html = renderer.renderCard(unit, {
        selectedOption: unit.pointsOptions[0],
        selectedWargear: [
            {
                group: { target: "This model", label: "This model", action: "equip" },
                selectedChoice: { id: "hunter-killer", label: "1 hunter-killer missile" },
            },
        ],
        manualWargearGroups: [],
    });

    assert.match(html, /Current Loadout/);
    assert.match(html, /1 hunter-killer missile/);
    assert.match(html, /Equipped on This model/);
    assert.match(html, /weapon-choice-badge-selected/);
    assert.doesNotMatch(html, /Replaces This model/);
});
