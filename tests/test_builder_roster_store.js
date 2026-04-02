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
        rules: {
            armyRules: [
                {
                    id: "strands-of-fate",
                    name: "Strands of Fate",
                    body: "Example army rule.",
                    sourceUrl: "http://example/aeldari",
                },
            ],
            detachments: [
                {
                    id: "battle-host",
                    name: "Battle Host",
                    summary: "Generalist detachment.",
                    rule: {
                        name: "Battle Host",
                        body: "Example detachment rule.",
                    },
                    restrictionsText: [],
                    enhancements: [
                        {
                            id: "phoenix-gem",
                            name: "Phoenix Gem",
                            points: 35,
                            body: "Character model only.",
                            eligibilityText: "Character model only.",
                        },
                        {
                            id: "fates-messenger",
                            name: "Fate's Messenger",
                            points: 15,
                            body: "Character model only.",
                            eligibilityText: "Character model only.",
                        },
                        {
                            id: "reader-of-the-runes",
                            name: "Reader of the Runes",
                            points: 20,
                            body: "Character model only.",
                            eligibilityText: "Character model only.",
                        },
                    ],
                    stratagems: [
                        {
                            id: "lightning-fast-reactions",
                            name: "Lightning-fast Reactions",
                            cp: 1,
                            kind: "Battle Tactic",
                            when: "Your opponent's Shooting phase, just after an enemy unit has selected its targets.",
                            target: "One AELDARI INFANTRY unit from your army.",
                            effect: "Example effect.",
                            phaseTags: ["shooting", "opponent"],
                            keywordHints: ["AELDARI INFANTRY"],
                        },
                    ],
                },
            ],
        },
        units: [
            {
                unitId: "avatar-of-khaine",
                name: "Avatar of Khaine",
                keywords: ["MONSTER", "CHARACTER"],
                factionKeywords: ["AELDARI"],
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
                        {
                            id: "armory",
                            label: "The Exarch’s sidearm can be replaced with 1 twin blades, or two different weapons from the following list:",
                            target: "sidearm",
                            action: "replace",
                            selectionMode: "multi",
                            pickCount: 2,
                            requireDistinct: true,
                            choices: [
                                { id: "twin-blades", label: "1 twin blades", pickCost: 2 },
                                { id: "shuriken-pistol", label: "1 shuriken pistol" },
                                { id: "power-blade", label: "1 power blade" },
                            ],
                        },
                        {
                            id: "marksman-rifle",
                            label: "1 trooper’s catapult can be replaced with 1 marksman rifle.",
                            target: "catapult",
                            action: "replace",
                            selectionMode: "single",
                            poolKey: "trooper-catapult",
                            poolLimit: { kind: "static", max: 1 },
                            choices: [
                                { id: "marksman-rifle-choice", label: "1 marksman rifle" },
                            ],
                        },
                        {
                            id: "vox-caster",
                            label: "1 trooper equipped with a catapult can be equipped with 1 vox-caster.",
                            target: "trooper",
                            action: "equip",
                            selectionMode: "single",
                            eligibilityText: "equipped with catapult",
                            poolKey: "trooper-catapult",
                            poolLimit: { kind: "static", max: 1 },
                            choices: [
                                { id: "vox-caster-choice", label: "1 vox-caster" },
                            ],
                        },
                    ],
                },
            },
            {
                unitId: "guardian-defenders",
                name: "Guardian Defenders",
                keywords: ["INFANTRY", "BATTLELINE"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "10-models", label: "10 models", points: 100, selectionKind: "models", modelCount: 10 },
                ],
                wargear: { options: [] },
                composition: {
                    modelCountOptions: [{ label: "10 Guardians", minModels: 10, maxModels: 10 }],
                    statements: [],
                },
            },
            {
                unitId: "troupe",
                name: "Troupe",
                keywords: ["INFANTRY"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "5-models", label: "5 models", points: 85, selectionKind: "models", modelCount: 5 },
                    { id: "11-models", label: "11 models", points: 190, selectionKind: "models", modelCount: 11 },
                ],
                wargear: {
                    options: [
                        {
                            id: "pistol-upgrade-small",
                            label: "If this unit contains 9 or fewer models:",
                            target: "shuriken pistol",
                            action: "replace",
                            selectionMode: "allocation",
                            allocationLimit: { kind: "static", max: 2 },
                            availability: { kind: "modelCountRange", minModels: null, maxModels: 9 },
                            choices: [
                                { id: "neuro-disruptor", label: "1 neuro disruptor" },
                                { id: "fusion-pistol", label: "1 fusion pistol" },
                            ],
                        },
                        {
                            id: "pistol-upgrade-large",
                            label: "If this unit contains 10 or more models:",
                            target: "shuriken pistol",
                            action: "replace",
                            selectionMode: "allocation",
                            allocationLimit: { kind: "static", max: 4 },
                            availability: { kind: "modelCountRange", minModels: 10, maxModels: null },
                            choices: [
                                { id: "neuro-disruptor", label: "1 neuro disruptor" },
                                { id: "fusion-pistol", label: "1 fusion pistol" },
                            ],
                        },
                    ],
                },
                composition: {
                    modelCountOptions: [
                        { label: "5 Troupe models", minModels: 5, maxModels: 5 },
                        { label: "11 Troupe models", minModels: 11, maxModels: 11 },
                    ],
                    statements: [],
                },
            },
            {
                unitId: "autarch",
                name: "Autarch",
                keywords: ["INFANTRY", "CHARACTER"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "1-model", label: "1 model", points: 90, selectionKind: "models", modelCount: 1 },
                ],
                renderBlocks: [
                    {
                        title: "LEADER",
                        entries: [{ type: "list", items: ["Guardian Defenders"] }],
                    },
                ],
                wargear: { options: [] },
                composition: {
                    modelCountOptions: [{ label: "1 Autarch", minModels: 1, maxModels: 1 }],
                    statements: [],
                },
            },
            {
                unitId: "wave-serpent",
                name: "Wave Serpent",
                keywords: ["VEHICLE", "TRANSPORT", "DEDICATED TRANSPORT"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "1-model", label: "1 model", points: 120, selectionKind: "models", modelCount: 1 },
                ],
                wargear: { options: [] },
                renderBlocks: [
                    {
                        title: "TRANSPORT",
                        entries: [{ type: "text", text: "This model has a transport capacity of 12 AELDARI INFANTRY models. Each WRAITHGUARD model takes up the space of 2 models." }],
                    },
                ],
                composition: {
                    modelCountOptions: [{ label: "1 Wave Serpent", minModels: 1, maxModels: 1 }],
                    statements: [],
                },
            },
            {
                unitId: "prince-yriel",
                name: "Prince Yriel",
                keywords: ["INFANTRY", "CHARACTER", "EPIC HERO"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "1-model", label: "1 model", points: 100, selectionKind: "models", modelCount: 1 },
                ],
                wargear: { options: [] },
                composition: {
                    modelCountOptions: [{ label: "1 Prince Yriel", minModels: 1, maxModels: 1 }],
                    statements: [],
                },
            },
            {
                unitId: "fire-prism",
                name: "Fire Prism",
                keywords: ["VEHICLE"],
                factionKeywords: ["AELDARI"],
                pointsOptions: [
                    { id: "1-model", label: "1 model", points: 180, selectionKind: "models", modelCount: 1 },
                ],
                wargear: { options: [] },
                composition: {
                    modelCountOptions: [{ label: "1 Fire Prism", minModels: 1, maxModels: 1 }],
                    statements: [],
                },
            },
        ],
    };
}

function legalArmy(warlordInstanceId = "entry-1", battleSize = "strike-force", detachmentId = "battle-host") {
    return {
        battleSize,
        warlordInstanceId,
        detachmentId,
    };
}

test("saveRosterToStorage persists payload and active id", () => {
    const storage = createMemoryStorage();
    const roster = Store.serializeRuntimeRoster({
        id: "roster-1",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Swordwind",
        builderSchemaVersion: 6,
        builderGeneratedAt: "2026-03-30T17:08:35+00:00",
        army: legalArmy(),
        entries: [
            {
                instanceId: "entry-1",
                unitId: "guardian-defenders",
                optionId: "10-models",
                optionIndex: 0,
                upgradeOptionIds: [],
                quantity: 1,
                wargearSelections: {},
                embarkedInInstanceId: "entry-3",
            },
            {
                instanceId: "entry-2",
                unitId: "autarch",
                optionId: "1-model",
                optionIndex: 0,
                upgradeOptionIds: ["exarch-upgrade"],
                quantity: 1,
                wargearSelections: {
                    "relic-weapon": "spear",
                    "heavy-weapon-allocation": { mode: "allocation", counts: { "dark-lance": 1 } },
                    armory: { mode: "multi", choiceIds: ["shuriken-pistol", "power-blade"] },
                },
                attachedToInstanceId: "entry-1",
            },
            {
                instanceId: "entry-3",
                unitId: "wave-serpent",
                optionId: "1-model",
                optionIndex: 0,
                upgradeOptionIds: [],
                quantity: 1,
                wargearSelections: {},
            },
        ],
    });

    const result = Store.saveRosterToStorage(storage, roster);
    assert.equal(result.ok, true);
    assert.equal(Store.getActiveRosterId(storage), "roster-1");
    assert.equal(Store.listSavedRosters(storage).length, 1);

    const loaded = Store.loadRosterFromStorage(storage, "roster-1");
    assert.equal(loaded.name, "Swordwind");
    assert.equal(loaded.army.battleSize, "strike-force");
    assert.equal(loaded.army.warlordInstanceId, "entry-1");
    assert.equal(loaded.army.detachmentId, "battle-host");
    assert.equal(loaded.builderSchemaVersion, 6);
    assert.equal(loaded.builderGeneratedAt, "2026-03-30T17:08:35+00:00");
    assert.equal(loaded.entries[0].embarkedInInstanceId, "entry-3");
    assert.equal(loaded.entries[1].attachedToInstanceId, "entry-1");
    assert.equal(loaded.entries[1].optionId, "1-model");
    assert.deepEqual(loaded.entries[1].upgradeOptionIds, ["exarch-upgrade"]);
    assert.equal(loaded.entries[1].wargearSelections["relic-weapon"], "spear");
    assert.equal(loaded.entries[1].wargearSelections["heavy-weapon-allocation"].counts["dark-lance"], 1);
    assert.deepEqual(loaded.entries[1].wargearSelections.armory.choiceIds, ["shuriken-pistol", "power-blade"]);
});

test("import/export round trips roster JSON", () => {
    const json = Store.exportRosterJson({
        id: "roster-2",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Imported Roster",
        builderSchemaVersion: 6,
        builderGeneratedAt: "2026-03-30T17:08:35+00:00",
        army: legalArmy(),
        entries: [{
            instanceId: "entry-1",
            unitId: "autarch",
            optionId: "1-model",
            upgradeOptionIds: ["exarch-upgrade"],
            quantity: 2,
            wargearSelections: {
                "relic-weapon": "axe",
                "heavy-weapon-allocation": { mode: "allocation", counts: { "scatter-laser": 2 } },
                armory: { mode: "multi", choiceIds: ["twin-blades"] },
            },
            attachedToInstanceId: "entry-2",
        }, {
            instanceId: "entry-2",
            unitId: "guardian-defenders",
            optionId: "10-models",
            quantity: 1,
            wargearSelections: {},
            embarkedInInstanceId: "entry-3",
        }, {
            instanceId: "entry-3",
            unitId: "wave-serpent",
            optionId: "1-model",
            quantity: 1,
            wargearSelections: {},
        }],
    });

    const imported = Store.importRosterJson(json);
    assert.equal(imported.name, "Imported Roster");
    assert.equal(imported.factionSlug, "aeldari");
    assert.equal(imported.builderSchemaVersion, 6);
    assert.equal(imported.builderGeneratedAt, "2026-03-30T17:08:35+00:00");
    assert.equal(imported.army.battleSize, "strike-force");
    assert.equal(imported.army.warlordInstanceId, "entry-1");
    assert.equal(imported.army.detachmentId, "battle-host");
    assert.equal(imported.entries[0].quantity, 2);
    assert.equal(imported.entries[0].attachedToInstanceId, "entry-2");
    assert.deepEqual(imported.entries[0].upgradeOptionIds, ["exarch-upgrade"]);
    assert.equal(imported.entries[0].wargearSelections["relic-weapon"], "axe");
    assert.equal(imported.entries[0].wargearSelections["heavy-weapon-allocation"].counts["scatter-laser"], 2);
    assert.deepEqual(imported.entries[0].wargearSelections.armory.choiceIds, ["twin-blades"]);
    assert.equal(imported.entries[1].embarkedInInstanceId, "entry-3");
    assert.notEqual(imported.id, "roster-2");
});

test("deriveResolvedRoster resolves by optionId and totals valid entries", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-3",
            factionSlug: "aeldari",
            name: "Resolved",
            army: legalArmy(),
            entries: [
                {
                    instanceId: "entry-1",
                    unitId: "avatar-of-khaine",
                    optionId: "2-models",
                    optionIndex: 0,
                    upgradeOptionIds: ["exarch-upgrade"],
                    quantity: 2,
                    wargearSelections: {
                        "relic-weapon": "spear",
                        "heavy-weapon-allocation": { mode: "allocation", counts: { "dark-lance": 2 } },
                        armory: { mode: "multi", choiceIds: ["shuriken-pistol", "power-blade"] },
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
    assert.deepEqual(
        resolved.entries[0].wargearSelections[2].selectedChoices.map((item) => item.choice.id),
        ["shuriken-pistol", "power-blade"]
    );
    assert.equal(resolved.entries[0].linePoints, 1180);
    assert.equal(resolved.totalPoints, 1180);
    assert.equal(resolved.invalidEntries.length, 0);
    assert.equal(resolved.armyIssues.length, 0);
    assert.equal(resolved.army.activeDetachment.id, "battle-host");
    assert.equal(resolved.army.availableEnhancements.length, 3);
    assert.equal(resolved.army.stratagems.length, 1);
    assert.equal(resolved.compatibility.needsReview, true);
    assert.equal(resolved.readiness.state, "playable");
    assert.equal(resolved.entries[0].support.supportLevel, "full");
});

test("deriveResolvedRoster adds enhancement points and exposes enhancement metadata", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-enhancement",
            factionSlug: "aeldari",
            name: "Enhancement",
            army: legalArmy("entry-1"),
            entries: [
                {
                    instanceId: "entry-1",
                    unitId: "autarch",
                    optionId: "1-model",
                    quantity: 1,
                    enhancementId: "phoenix-gem",
                    wargearSelections: {},
                },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.entries[0].activeEnhancement.name, "Phoenix Gem");
    assert.equal(resolved.entries[0].linePointsBase, 90);
    assert.equal(resolved.entries[0].linePointsEnhancement, 35);
    assert.equal(resolved.entries[0].linePoints, 125);
    assert.equal(resolved.totalPoints, 125);
    assert.equal(resolved.invalidEntries.length, 0);
});

test("deriveResolvedRoster requires a detachment when faction rules expose detachments", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-missing-detachment",
            factionSlug: "aeldari",
            name: "No Detachment",
            army: { battleSize: "strike-force", warlordInstanceId: "entry-1", detachmentId: null },
            entries: [
                { instanceId: "entry-1", unitId: "autarch", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.ok(resolved.armyIssues.some((issue) => issue.code === "missing-detachment"));
});

test("deriveResolvedRoster rejects illegal enhancement assignments", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-enhancement-illegal",
            factionSlug: "aeldari",
            name: "Illegal Enhancements",
            army: legalArmy("entry-1"),
            entries: [
                { instanceId: "entry-1", unitId: "autarch", optionId: "1-model", quantity: 1, enhancementId: "phoenix-gem", wargearSelections: {} },
                { instanceId: "entry-2", unitId: "guardian-defenders", optionId: "10-models", quantity: 1, enhancementId: "fates-messenger", wargearSelections: {} },
                { instanceId: "entry-3", unitId: "prince-yriel", optionId: "1-model", quantity: 1, enhancementId: "reader-of-the-runes", wargearSelections: {} },
                { instanceId: "entry-4", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, enhancementId: "phoenix-gem", wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.match(resolved.entries[1].issues.join(" "), /Character units/i);
    assert.match(resolved.entries[2].issues.join(" "), /Epic Heroes cannot take enhancements/i);
    assert.match(resolved.entries[0].issues.join(" "), /only be selected once per roster/i);
    assert.match(resolved.entries[3].issues.join(" "), /only be selected once per roster/i);
    assert.ok(resolved.armyIssues.some((issue) => issue.code === "too-many-enhancements"));
});

test("deriveResolvedRoster upgrades legacy upgrade-only selections into additive points", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-legacy",
            factionSlug: "aeldari",
            name: "Legacy",
            army: legalArmy(),
            entries: [
                {
                    instanceId: "entry-1",
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
    assert.equal(resolved.armyIssues.length, 0);
});

test("deriveResolvedRoster degrades gracefully when faction, unit, or option is missing", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-4",
            factionSlug: "space-marines",
            name: "Broken",
            army: { battleSize: "strike-force", warlordInstanceId: "missing-entry" },
            entries: [
                { instanceId: "entry-1", unitId: "missing-unit", optionId: "missing-option", quantity: 1, wargearSelections: { "relic-weapon": "axe" } },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.totalPoints, 0);
    assert.equal(resolved.validEntries.length, 0);
    assert.match(resolved.invalidEntries[0].issues[0], /Saved faction is not available/);
    assert.match(resolved.invalidEntries[0].issues.join(" "), /Unit not found/);
    assert.equal(resolved.invalidEntries[0].support.supportLevel, "incompatible");
    assert.equal(resolved.invalidEntries[0].canRepair, true);
    assert.equal(resolved.compatibility.incompatibleEntries.length, 1);
});

test("migrateSavedRosterDocument defaults army state for legacy rosters", () => {
    const migrated = Store.migrateSavedRosterDocument({
        id: "legacy-roster",
        factionSlug: "aeldari",
        name: "Legacy",
        entries: [{ unitId: "avatar-of-khaine", quantity: 1 }],
    });

    assert.equal(migrated.army.battleSize, "strike-force");
    assert.equal(migrated.army.warlordInstanceId, null);
    assert.equal(migrated.army.detachmentId, null);
    assert.equal(migrated.entries[0].attachedToInstanceId, null);
    assert.equal(migrated.entries[0].embarkedInInstanceId, null);
    assert.equal(migrated.entries[0].enhancementId, null);
    assert.equal(migrated.builderSchemaVersion, null);
    assert.equal(migrated.builderGeneratedAt, null);
});

test("dedupeSavedRosters keeps the newest save per roster name and faction", () => {
    const storage = createMemoryStorage();
    Store.saveRosterToStorage(storage, Store.serializeRuntimeRoster({
        id: "roster-a",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Swordwind",
        builderSchemaVersion: 5,
        builderGeneratedAt: "2026-03-20T10:00:00+00:00",
        savedAt: "2026-03-20T10:00:00+00:00",
        army: legalArmy(),
        entries: [],
    }));
    Store.saveRosterToStorage(storage, Store.serializeRuntimeRoster({
        id: "roster-b",
        appVersion: "builder-catalog-v2",
        factionSlug: "aeldari",
        name: "Swordwind",
        builderSchemaVersion: 6,
        builderGeneratedAt: "2026-03-30T17:08:35+00:00",
        savedAt: "2026-03-30T17:08:35+00:00",
        army: legalArmy(),
        entries: [],
    }));

    const result = Store.dedupeSavedRosters(storage);
    assert.equal(result.ok, true);
    assert.equal(result.removedCount, 1);
    assert.deepEqual(Store.listSavedRosters(storage).map((item) => item.id), ["roster-b"]);
});

test("deriveResolvedRoster validates multi-pick limits and shared pools", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-wargear-issues",
            factionSlug: "aeldari",
            name: "Wargear",
            army: legalArmy(),
            entries: [
                {
                    instanceId: "entry-1",
                    unitId: "avatar-of-khaine",
                    optionId: "1-model",
                    quantity: 1,
                    wargearSelections: {
                        armory: { mode: "multi", choiceIds: ["shuriken-pistol", "shuriken-pistol", "power-blade"] },
                        "marksman-rifle": "marksman-rifle-choice",
                        "vox-caster": "vox-caster-choice",
                    },
                },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.match(resolved.entries[0].issues.join(" "), /must use different choices/i);
    assert.match(resolved.entries[0].issues.join(" "), /2-pick limit/i);
    assert.match(resolved.entries[0].issues.join(" "), /eligible models/i);
    const armorySelection = resolved.entries[0].wargearSelections.find((item) => item.group.id === "armory");
    assert.equal(armorySelection.totalSelected, 3);
    const poolSelection = resolved.entries[0].wargearSelections.find((item) => item.group.id === "marksman-rifle");
    assert.equal(poolSelection.poolUsage.used, 2);
    assert.equal(poolSelection.poolUsage.max, 1);
});

test("deriveResolvedRoster preserves inactive wargear selections across model-count changes", () => {
    const baseRoster = {
        id: "roster-conditional-wargear",
        factionSlug: "aeldari",
        name: "Conditional Wargear",
        army: legalArmy(),
        entries: [
            {
                instanceId: "entry-1",
                unitId: "troupe",
                optionId: "5-models",
                quantity: 1,
                wargearSelections: {
                    "pistol-upgrade-large": { mode: "allocation", counts: { "fusion-pistol": 2 } },
                },
            },
        ],
    };

    const inactive = Store.deriveResolvedRoster({
        roster: baseRoster,
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(
        inactive.entries[0].wargearSelections.some((item) => item.group.id === "pistol-upgrade-large"),
        false
    );
    assert.equal(inactive.entries[0].inactiveWargearSelections.length, 1);
    assert.match(inactive.entries[0].issues.join(" "), /inactive at 5 models/i);
    assert.match(inactive.entries[0].issues.join(" "), /10\+ models/i);

    const reactivated = Store.deriveResolvedRoster({
        roster: {
            ...baseRoster,
            entries: [
                {
                    ...baseRoster.entries[0],
                    optionId: "11-models",
                },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    const selection = reactivated.entries[0].wargearSelections.find((item) => item.group.id === "pistol-upgrade-large");
    assert.equal(reactivated.entries[0].inactiveWargearSelections.length, 0);
    assert.equal(selection.selectedChoices[0].choice.id, "fusion-pistol");
    assert.equal(selection.selectedChoices[0].count, 2);
    assert.doesNotMatch(reactivated.entries[0].issues.join(" "), /inactive at/i);
});

test("deriveResolvedRoster resolves valid attachments and embarked units", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-relationships-valid",
            factionSlug: "aeldari",
            name: "Relationships",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-bodyguard", unitId: "guardian-defenders", optionId: "10-models", quantity: 1, wargearSelections: {}, embarkedInInstanceId: "entry-transport" },
                { instanceId: "entry-hero", unitId: "autarch", optionId: "1-model", quantity: 1, wargearSelections: {}, attachedToInstanceId: "entry-bodyguard" },
                { instanceId: "entry-transport", unitId: "wave-serpent", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    const hero = resolved.entries.find((entry) => entry.instanceId === "entry-hero");
    const bodyguard = resolved.entries.find((entry) => entry.instanceId === "entry-bodyguard");
    const transport = resolved.entries.find((entry) => entry.instanceId === "entry-transport");

    assert.equal(hero.relationship.attachedToLabel, "Guardian Defenders");
    assert.equal(hero.relationship.inheritedEmbarkedInLabel, "Wave Serpent");
    assert.deepEqual(bodyguard.relationship.attachedLeaderNames, ["Autarch"]);
    assert.equal(bodyguard.relationship.embarkedInLabel, "Wave Serpent");
    assert.equal(transport.relationship.transportCapacity.used, 11);
    assert.deepEqual(transport.relationship.embarkedUnitNames, ["Guardian Defenders"]);
    assert.equal(resolved.invalidEntries.length, 0);
});

test("deriveResolvedRoster flags invalid attachment and transport assignments", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-relationships-invalid",
            factionSlug: "aeldari",
            name: "Bad Relationships",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-bodyguard-1", unitId: "guardian-defenders", optionId: "10-models", quantity: 1, wargearSelections: {}, embarkedInInstanceId: "entry-transport" },
                { instanceId: "entry-bodyguard-2", unitId: "guardian-defenders", optionId: "10-models", quantity: 1, wargearSelections: {}, embarkedInInstanceId: "entry-transport" },
                { instanceId: "entry-hero", unitId: "autarch", optionId: "1-model", quantity: 1, wargearSelections: {}, attachedToInstanceId: "entry-fire-prism" },
                { instanceId: "entry-fire-prism", unitId: "fire-prism", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-transport", unitId: "wave-serpent", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    const hero = resolved.entries.find((entry) => entry.instanceId === "entry-hero");
    const transport = resolved.entries.find((entry) => entry.instanceId === "entry-transport");

    assert.match(hero.issues.join(" "), /cannot attach to Fire Prism/i);
    assert.match(transport.issues.join(" "), /uses 20\/12 transport capacity/i);
});

test("deriveResolvedRoster flags empty Dedicated Transports", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-empty-transport",
            factionSlug: "aeldari",
            name: "Empty Transport",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-hero", unitId: "autarch", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-transport", unitId: "wave-serpent", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    const transport = resolved.entries.find((entry) => entry.instanceId === "entry-transport");
    assert.match(transport.issues.join(" "), /Dedicated Transport has no embarked units assigned/i);
});

test("deriveResolvedRoster flags points caps by battle size", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-points",
            factionSlug: "aeldari",
            name: "Points",
            army: legalArmy("entry-1", "incursion"),
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "2-models", quantity: 2, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.pointsLimit, 1000);
    assert.match(resolved.armyIssues[0].message, /exceeding the 1000-point incursion limit/i);
});

test("deriveResolvedRoster enforces default duplicate cap of three", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-rule-three",
            factionSlug: "aeldari",
            name: "Rule of Three",
            army: legalArmy(),
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 4, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.invalidEntries.length, 1);
    assert.match(resolved.invalidEntries[0].issues.join(" "), /limit of 3/);
});

test("deriveResolvedRoster allows six Battleline units and flags the seventh", () => {
    const allowed = Store.deriveResolvedRoster({
        roster: {
            id: "roster-battleline-ok",
            factionSlug: "aeldari",
            name: "Battleline OK",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-hero", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-1", unitId: "guardian-defenders", optionId: "10-models", quantity: 6, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });
    const flagged = Store.deriveResolvedRoster({
        roster: {
            id: "roster-battleline-bad",
            factionSlug: "aeldari",
            name: "Battleline Bad",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-hero", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-1", unitId: "guardian-defenders", optionId: "10-models", quantity: 7, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(allowed.invalidEntries.length, 0);
    assert.match(flagged.invalidEntries[0].issues.join(" "), /limit of 6/);
});

test("deriveResolvedRoster allows six Dedicated Transports and flags the seventh", () => {
    const allowed = Store.deriveResolvedRoster({
        roster: {
            id: "roster-transport-ok",
            factionSlug: "aeldari",
            name: "Transport OK",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-hero", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-1", unitId: "wave-serpent", optionId: "1-model", quantity: 6, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });
    const flagged = Store.deriveResolvedRoster({
        roster: {
            id: "roster-transport-bad",
            factionSlug: "aeldari",
            name: "Transport Bad",
            army: legalArmy("entry-hero"),
            entries: [
                { instanceId: "entry-hero", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-1", unitId: "wave-serpent", optionId: "1-model", quantity: 7, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.doesNotMatch(allowed.invalidEntries[0].issues.join(" "), /limit of 6/);
    assert.match(flagged.invalidEntries[0].issues.join(" "), /limit of 6/);
});

test("deriveResolvedRoster enforces unique Epic Heroes", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-epic",
            factionSlug: "aeldari",
            name: "Epic Hero",
            army: legalArmy("entry-1"),
            entries: [
                { instanceId: "entry-1", unitId: "prince-yriel", optionId: "1-model", quantity: 2, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.equal(resolved.invalidEntries.length, 1);
    assert.match(resolved.invalidEntries[0].issues.join(" "), /limit of 1/);
});

test("deriveResolvedRoster requires a Character unit", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-no-character",
            factionSlug: "aeldari",
            name: "No Character",
            army: { battleSize: "strike-force", warlordInstanceId: null },
            entries: [
                { instanceId: "entry-1", unitId: "fire-prism", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.ok(resolved.armyIssues.some((issue) => issue.code === "missing-character"));
    assert.ok(resolved.armyIssues.some((issue) => issue.code === "missing-warlord"));
});

test("deriveResolvedRoster requires a Warlord when Characters are present", () => {
    const resolved = Store.deriveResolvedRoster({
        roster: {
            id: "roster-no-warlord",
            factionSlug: "aeldari",
            name: "No Warlord",
            army: { battleSize: "strike-force", warlordInstanceId: null },
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.ok(resolved.armyIssues.some((issue) => issue.code === "missing-warlord"));
});

test("deriveResolvedRoster rejects non-character or missing Warlords and accepts one valid Warlord", () => {
    const nonCharacter = Store.deriveResolvedRoster({
        roster: {
            id: "roster-bad-warlord",
            factionSlug: "aeldari",
            name: "Bad Warlord",
            army: { battleSize: "strike-force", warlordInstanceId: "entry-2" },
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-2", unitId: "fire-prism", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });
    const missing = Store.deriveResolvedRoster({
        roster: {
            id: "roster-missing-warlord",
            factionSlug: "aeldari",
            name: "Missing Warlord",
            army: { battleSize: "strike-force", warlordInstanceId: "missing-entry" },
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });
    const valid = Store.deriveResolvedRoster({
        roster: {
            id: "roster-valid-warlord",
            factionSlug: "aeldari",
            name: "Valid Warlord",
            army: legalArmy("entry-1"),
            entries: [
                { instanceId: "entry-1", unitId: "avatar-of-khaine", optionId: "1-model", quantity: 1, wargearSelections: {} },
                { instanceId: "entry-2", unitId: "fire-prism", optionId: "1-model", quantity: 1, wargearSelections: {} },
            ],
        },
        catalog: sampleCatalog(),
        availableFactionSlugs: ["aeldari"],
    });

    assert.ok(nonCharacter.armyIssues.some((issue) => issue.code === "invalid-warlord"));
    assert.ok(missing.armyIssues.some((issue) => issue.code === "invalid-warlord"));
    assert.equal(valid.armyIssues.length, 0);
});
