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

test("renderCard renders inline quick-swap controls only for simple single-choice wargear", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Allarus Custodians",
        stats: { M: '5"', T: "7", Sv: "2+", W: "4", Ld: "6+", OC: "2" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "3-models", label: "3 models", points: 165, selectionKind: "models", modelCount: 3 }],
        wargear: {
            options: [
                {
                    id: "spear-swap",
                    label: "This model’s guardian spear can be replaced with 1 castellan axe.",
                    target: "guardian spear",
                    selectionMode: "single",
                    choices: [{ id: "castellan-axe", label: "1 castellan axe" }],
                },
                {
                    id: "catapult-allocation",
                    label: "Any number of models can each have their twin shuriken catapult replaced with one of the following:",
                    target: "twin shuriken catapult",
                    selectionMode: "allocation",
                    choices: [{ id: "shield-blade", label: "1 shield blade" }],
                },
                {
                    id: "sergeant-armory",
                    label: "Two different options can be selected.",
                    target: "armory",
                    selectionMode: "multi",
                    choices: [{ id: "weapon-a", label: "1 weapon a" }],
                },
                {
                    id: "exarch-conditional",
                    label: "If this unit’s Dire Avenger Exarch is equipped with 1 Avenger shuriken catapult, it can be equipped with 1 additional Avenger shuriken catapult.",
                    target: "If this unit’s Dire Avenger Exarch is equipped with 1 Avenger shuriken catapult, it",
                    selectionMode: "single",
                    choices: [{ id: "extra-catapult", label: "1 additional Avenger shuriken catapult" }],
                },
            ],
        },
        weapons: { ranged: [], melee: [] },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["3 Allarus Custodians"] },
        keywords: ["INFANTRY"],
        factionKeywords: ["ADEPTUS CUSTODES"],
    };

    const html = renderer.renderCard(unit, {
        instanceId: "entry-1",
        interactiveInlineSelection: true,
        selectedOption: unit.pointsOptions[0],
        selectedWargear: [
            {
                group: unit.wargear.options[0],
                selectedChoice: { id: "castellan-axe", label: "1 castellan axe" },
            },
        ],
        manualWargearGroups: [],
    });

    assert.match(html, /Quick swaps/);
    assert.match(html, /data-action="card-inline-select"/);
    assert.match(html, /data-group-id="spear-swap"/);
    assert.match(html, /aria-pressed="true"/);
    assert.match(html, /Full configuration/);
    assert.match(html, /guardian spear/);
    assert.match(html, /Swap/);
    assert.doesNotMatch(html, /catapult-allocation/);
    assert.doesNotMatch(html, /wargear-count/);
    assert.doesNotMatch(html, /wargear-multi-toggle/);
    assert.doesNotMatch(html, /Dire Avenger Exarch/);
    assert.doesNotMatch(html, /extra-catapult/);
});

test("renderCard includes selected enhancement in header and current loadout", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Autarch",
        stats: { M: '7"', T: "3", Sv: "3+", W: "4", Ld: "6+", OC: "2" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "1-model", label: "1 model", points: 90, selectionKind: "models" }],
        weapons: { ranged: [], melee: [] },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["1 Autarch"] },
        keywords: ["INFANTRY", "CHARACTER"],
        factionKeywords: ["AELDARI"],
    };

    const html = renderer.renderCard(unit, {
        selectedOption: unit.pointsOptions[0],
        selectedEnhancement: {
            id: "phoenix-gem",
            name: "Phoenix Gem",
            points: 35,
            body: "Character model only.",
        },
        manualWargearGroups: [],
    });

    assert.match(html, /Enhancement: Phoenix Gem/);
    assert.match(html, /Character model only/);
    assert.match(html, /enhancement/);
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

test("renderCard shows counted allocation loadout selections", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Corsair Cloud Dancer Band",
        stats: { M: '14"', T: "4", Sv: "3+", W: "2", Ld: "6+", OC: "2" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "3-models", label: "3 models", points: 105, selectionKind: "models", modelCount: 3 }],
        weapons: {
            ranged: [
                { name: "Twin shuriken catapult", range: '18"', a: "2", skill: "3+", s: "4", ap: "-1", d: "1", abilities: [] },
                { name: "Dark lance", range: '36"', a: "1", skill: "3+", s: "12", ap: "-3", d: "D6+2", abilities: [] },
                { name: "Scatter laser", range: '36"', a: "6", skill: "3+", s: "5", ap: "0", d: "1", abilities: [] },
            ],
            melee: [{ name: "Close combat weapon", range: "Melee", a: "2", skill: "3+", s: "3", ap: "0", d: "1", abilities: [] }],
        },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        renderBlocks: [],
        composition: { rawLines: ["3 Corsair Cloud Dancers"] },
        keywords: ["MOUNTED"],
        factionKeywords: ["AELDARI"],
    };

    const html = renderer.renderCard(unit, {
        selectedOption: unit.pointsOptions[0],
        selectedWargear: [
            {
                group: {
                    target: "twin shuriken catapult",
                    label: "Any number of models can each have their twin shuriken catapult replaced with one of the following:",
                    action: "replace",
                    selectionMode: "allocation",
                },
                selectedChoices: [
                    { choice: { id: "dark-lance", label: "1 dark lance" }, count: 2 },
                    { choice: { id: "scatter-laser", label: "1 scatter laser" }, count: 1 },
                ],
            },
        ],
        manualWargearGroups: [],
    });

    assert.match(html, /2x dark lance/);
    assert.match(html, /1 scatter laser/);
    assert.match(html, /Replaces twin shuriken catapult/);
    assert.match(html, /weapon-choice-badge-selected/);
    assert.match(html, /weapon-choice-badge-replaced/);
});

test("renderCard renders ordered source sections for abilities and unit composition", () => {
    const renderer = loadRenderer();
    const unit = {
        name: "Avatar of Khaine",
        stats: { M: '10"', T: "11", Sv: "2+", W: "14", Ld: "6+", OC: "5", invulnerableSave: "4+" },
        quality: { missingStats: [] },
        selectionMode: "parsed",
        pointsOptions: [{ id: "1-model", label: "1 model", points: 280, selectionKind: "models" }],
        weapons: {
            ranged: [{ name: "The Wailing Doom", range: '12"', a: "1", skill: "2+", s: "16", ap: "-4", d: "D6+2", abilities: ["Sustained Hits D3"] }],
            melee: [
                { name: "The Wailing Doom - strike", range: "Melee", a: "6", skill: "2+", s: "16", ap: "-4", d: "D6+2", abilities: [] },
                { name: "The Wailing Doom - sweep", range: "Melee", a: "12", skill: "2+", s: "8", ap: "-2", d: "2", abilities: [] },
            ],
        },
        abilities: { core: [], faction: [], datasheet: [], other: [] },
        composition: {
            rawLines: ["1 Avatar of Khaine - EPIC HERO"],
            statements: [{ label: "This model is equipped with", text: "the Wailing Doom" }],
        },
        renderSections: [
            {
                title: "ABILITIES",
                displayStyle: "section",
                entries: [
                    { type: "tagged_list", label: "CORE", items: ["Deadly Demise D3"] },
                    { type: "tagged_list", label: "FACTION", items: ["Battle Focus"] },
                    { type: "rule", name: "Molten Form", text: "Halve the Damage characteristic of each allocated attack." },
                    { type: "rule", name: "The Bloody-Handed (Aura)", text: "Add 1 to Advance and Charge rolls." },
                ],
            },
            {
                title: "UNIT COMPOSITION",
                displayStyle: "section",
                entries: [
                    { type: "list", items: ["1 Avatar of Khaine - EPIC HERO"] },
                    { type: "statement", label: "This model is equipped with", text: "the Wailing Doom" },
                    { type: "points", rows: [{ label: "1 model", points: "280" }] },
                ],
            },
            {
                title: "DAMAGED: 1-5 WOUNDS REMAINING",
                displayStyle: "damaged",
                entries: [{ type: "text", text: "Subtract 1 from the Hit roll." }],
            },
        ],
        keywords: ["MONSTER", "CHARACTER"],
        factionKeywords: ["ASURYANI"],
    };

    const html = renderer.renderCard(unit, {
        selectedOption: unit.pointsOptions[0],
        manualWargearGroups: [],
    });

    assert.match(html, /CORE:/);
    assert.match(html, /FACTION:/);
    assert.match(html, /Molten Form/);
    assert.match(html, /The Bloody-Handed \(Aura\)/);
    assert.match(html, /1 Avatar of Khaine - EPIC HERO/);
    assert.match(html, /This model is equipped with/);
    assert.match(html, /the Wailing Doom/);
    assert.match(html, /Faction Keywords:/);
    assert.match(html, /ASURYANI/);
    assert.doesNotMatch(html, /No composition data/);
});
