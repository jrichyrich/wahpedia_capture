const test = require("node:test");
const assert = require("node:assert/strict");

const Store = require("../docs/builder/roster_store.js");

function createMemoryStorage() {
    const map = new Map();
    return {
        getItem(key) {
            return map.has(key) ? map.get(key) : null;
        },
        setItem(key, value) {
            map.set(key, String(value));
        },
        removeItem(key) {
            map.delete(key);
        },
    };
}

function sampleCatalog() {
    return {
        faction: { slug: "aeldari", name: "Aeldari" },
        units: [
            {
                unitId: "avatar-of-khaine",
                name: "Avatar of Khaine",
                pointsOptions: [
                    { id: "1-model", label: "1 model", points: 280, selectionKind: "models" },
                    { id: "2-models", label: "2 models", points: 560, selectionKind: "models" },
                    { id: "exarch-upgrade", label: "Exarch", points: 30, selectionKind: "upgrade" },
                ],
                wargear: {
                    options: [
                        {
                            id: "relic-weapon",
                            label: "Relic weapon",
                            target: "Exarch",
                            selectionMode: "single",
                            choices: [
                                { id: "axe", label: "Axe" },
                                { id: "spear", label: "Spear" },
                            ],
                        },
                        {
                            id: "heavy-weapon-allocation",
                            label: "Any number of models can each have their catapult replaced with one of the following:",
                            target: "catapult",
                            action: "replace",
                            selectionMode: "allocation",
                            allocationLimit: "modelCount",
                            choices: [
                                { id: "dark-lance", label: "1 dark lance" },
                                { id: "scatter-laser", label: "1 scatter laser" },
                            ],
                        },
                    ],
                },
            },
        ],
    };
}

test("saveRosterToStorage persists payload and active id", () => {
    const storage = createMemoryStorage();
    const roster = Store.serializeRuntimeRoster({
        id: "roster-1",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Swordwind",
        entries: [
            {
                unitId: "avatar-of-khaine",
                optionId: "1-model",
                optionIndex: 0,
                upgradeOptionIds: ["exarch-upgrade"],
                quantity: 1,
                wargearSelections: {
                    "relic-weapon": "spear",
                    "heavy-weapon-allocation": { mode: "allocation", counts: { "dark-lance": 1 } },
                },
            },
        ],
    });

    const result = Store.saveRosterToStorage(storage, roster);
    assert.equal(result.ok, true);
    assert.equal(Store.getActiveRosterId(storage), "roster-1");
    assert.equal(Store.listSavedRosters(storage).length, 1);

    const loaded = Store.loadRosterFromStorage(storage, "roster-1");
    assert.equal(loaded.name, "Swordwind");
    assert.equal(loaded.entries[0].optionId, "1-model");
    assert.deepEqual(loaded.entries[0].upgradeOptionIds, ["exarch-upgrade"]);
    assert.equal(loaded.entries[0].wargearSelections["relic-weapon"], "spear");
    assert.equal(loaded.entries[0].wargearSelections["heavy-weapon-allocation"].counts["dark-lance"], 1);
});

test("import/export round trips roster JSON", () => {
    const json = Store.exportRosterJson({
        id: "roster-2",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Imported Roster",
        entries: [{
            unitId: "avatar-of-khaine",
            optionId: "1-model",
            upgradeOptionIds: ["exarch-upgrade"],
            quantity: 2,
            wargearSelections: {
                "relic-weapon": "axe",
                "heavy-weapon-allocation": { mode: "allocation", counts: { "scatter-laser": 2 } },
            },
        }],
    });

    const imported = Store.importRosterJson(json);
    assert.equal(imported.name, "Imported Roster");
    assert.equal(imported.factionSlug, "aeldari");
    assert.equal(imported.entries[0].quantity, 2);
    assert.deepEqual(imported.entries[0].upgradeOptionIds, ["exarch-upgrade"]);
    assert.equal(imported.entries[0].wargearSelections["relic-weapon"], "axe");
    assert.equal(imported.entries[0].wargearSelections["heavy-weapon-allocation"].counts["scatter-laser"], 2);
    assert.notEqual(imported.id, "roster-2");
});

test("deriveResolvedRoster resolves by optionId and totals valid entries", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-3",
            factionSlug: "aeldari",
            name: "Resolved",
            entries: [
                {
                    unitId: "avatar-of-khaine",
                    optionId: "2-models",
                    optionIndex: 0,
                    upgradeOptionIds: ["exarch-upgrade"],
                    quantity: 2,
                    wargearSelections: {
                        "relic-weapon": "spear",
                        "heavy-weapon-allocation": { mode: "allocation", counts: { "dark-lance": 2 } },
                    },
                },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.entries[0].selectedOption.id, "2-models");
    assert.deepEqual(resolved.entries[0].selectedUpgrades.map((option) => option.id), ["exarch-upgrade"]);
    assert.equal(resolved.entries[0].wargearSelections[0].selectedChoice.id, "spear");
    assert.equal(resolved.entries[0].wargearSelections[1].selectedChoices[0].choice.id, "dark-lance");
    assert.equal(resolved.entries[0].wargearSelections[1].selectedChoices[0].count, 2);
    assert.equal(resolved.entries[0].linePoints, 1180);
    assert.equal(resolved.totalPoints, 1180);
    assert.equal(resolved.invalidEntries.length, 0);
});

test("deriveResolvedRoster upgrades legacy upgrade-only selections into additive points", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-legacy",
            factionSlug: "aeldari",
            name: "Legacy",
            entries: [
                {
                    unitId: "avatar-of-khaine",
                    optionId: "exarch-upgrade",
                    optionIndex: 2,
                    quantity: 1,
                    wargearSelections: {},
                },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.entries[0].selectedOption.id, "1-model");
    assert.deepEqual(resolved.entries[0].selectedUpgrades.map((option) => option.id), ["exarch-upgrade"]);
    assert.equal(resolved.entries[0].linePoints, 310);
    assert.equal(resolved.invalidEntries.length, 0);
});

test("deriveResolvedRoster degrades gracefully when faction, unit, or option is missing", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-4",
            factionSlug: "space-marines",
            name: "Broken",
            entries: [
                { unitId: "missing-unit", optionId: "missing-option", quantity: 1, wargearSelections: { "relic-weapon": "axe" } },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.totalPoints, 0);
    assert.equal(resolved.validEntries.length, 0);
    assert.match(resolved.invalidEntries[0].issues[0], /Saved faction is not available/);
    assert.match(resolved.invalidEntries[0].issues.join(" "), /Unit not found/);
});
