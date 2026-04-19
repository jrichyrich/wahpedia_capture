const test = require("node:test");
const assert = require("node:assert/strict");

const App = require("../docs/builder/app.js");
const Store = require("../docs/builder/roster_store.js");

function sampleUnit() {
    return {
        unitId: "caladius-grav-tank",
        name: "Caladius Grav-tank",
        keywords: ["VEHICLE"],
        pointsOptions: [
            { id: "1-model", label: "1 model", points: 215, selectionKind: "models", modelCount: 1 },
            { id: "3-models", label: "3 models", points: 300, selectionKind: "models", modelCount: 3 },
        ],
        wargear: {
            options: [
                {
                    id: "iliastus-swap",
                    label: "This model’s twin iliastus accelerator cannon can be replaced with 1 twin arachnus heavy blaze cannon.",
                    target: "This model’s twin iliastus accelerator cannon",
                    selectionMode: "single",
                    choices: [{ id: "1-twin-arachnus-heavy-blaze-cannon", label: "1 twin arachnus heavy blaze cannon" }],
                },
                {
                    id: "catapult-allocation",
                    label: "Any number of models can each have their twin shuriken catapult replaced with one of the following:",
                    target: "twin shuriken catapult",
                    action: "replace",
                    selectionMode: "allocation",
                    allocationLimit: "modelCount",
                    choices: [
                        { id: "dark-lance", label: "1 dark lance" },
                        { id: "scatter-laser", label: "1 scatter laser" },
                    ],
                },
                {
                    id: "sergeant-armory",
                    label: "The sergeant’s sidearm can be replaced with 1 twin blades, or two different weapons from the following list:",
                    target: "sidearm",
                    action: "replace",
                    selectionMode: "multi",
                    pickCount: 2,
                    requireDistinct: true,
                    choices: [
                        { id: "twin-blades", label: "1 twin blades", pickCost: 2 },
                        { id: "bolt-pistol", label: "1 bolt pistol" },
                        { id: "power-weapon", label: "1 power weapon" },
                    ],
                },
            ],
        },
    };
}

function createDeps() {
    const unit = sampleUnit();
    const state = {
        roster: [{
            instanceId: "entry-1",
            unitId: unit.unitId,
            optionId: "1-model",
            optionIndex: 0,
            upgradeOptionIds: [],
            quantity: 1,
            wargearSelections: {},
            attachedToInstanceId: null,
            embarkedInInstanceId: null,
        }],
        army: Store.normalizeArmyState({}),
    };
    const calls = { renderRoster: 0, renderPreview: 0, scheduleAutoSave: 0, setRosterStatus: [] };
    return {
        unit,
        state,
        calls,
        controller: App.createInteractionController({
            state,
            Store,
            renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
            catalogUnitById: (unitId) => (unitId === unit.unitId ? unit : null),
            pointsGroups: (value) => ({
                base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
                upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
            }),
            renderRoster: () => { calls.renderRoster += 1; },
            renderPreview: () => { calls.renderPreview += 1; },
            scheduleAutoSave: () => { calls.scheduleAutoSave += 1; },
            setRosterStatus: (message, isError, undoAction, options) => { calls.setRosterStatus.push({ message, isError, undoAction, options }); },
        }),
    };
}

function samplePreviewEntry(overrides = {}) {
    const unit = {
        ...sampleUnit(),
        source: {
            outputSlug: "aeldari",
            datasheetSlug: "Avatar-of-Khaine",
        },
    };
    return {
        instanceId: "preview-entry-1",
        displayName: unit.name,
        unit,
        selectedOption: unit.pointsOptions[0],
        selectedUpgrades: [],
        linePoints: unit.pointsOptions[0].points,
        quantity: 1,
        wargearSelections: [],
        relationship: { relationshipNotes: [] },
        ...overrides,
    };
}

function makeEvent(selector, dataset, extras = {}) {
    const element = {
        dataset: dataset || {},
        value: extras.value,
        checked: extras.checked,
        closest(query) {
            return query === selector ? this : null;
        },
    };
    return { target: element };
}

test("handleRosterBodyClick removes an entry and rerenders", () => {
    const { controller, state, calls } = createDeps();
    const handled = controller.handleRosterBodyClick(
        makeEvent('[data-action="remove-entry"]', { instanceId: "entry-1" })
    );

    assert.equal(handled, true);
    assert.equal(state.roster.length, 0);
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
});

test("handleRosterBodyChange updates structured wargear selection and rerenders", () => {
    const { controller, state, calls } = createDeps();
    const handled = controller.handleRosterBodyChange(
        makeEvent(
            '[data-action="wargear-select"]',
            { instanceId: "entry-1", groupId: "iliastus-swap" },
            { value: "1-twin-arachnus-heavy-blaze-cannon" }
        )
    );

    assert.equal(handled, true);
    assert.equal(state.roster[0].wargearSelections["iliastus-swap"], "1-twin-arachnus-heavy-blaze-cannon");
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
});

test("updateRosterWargearInline updates the roster and exposes an undo action", () => {
    const { controller, state, calls } = createDeps();

    const handled = controller.updateRosterWargearInline(
        "entry-1",
        "iliastus-swap",
        "1-twin-arachnus-heavy-blaze-cannon"
    );

    assert.equal(handled, true);
    assert.equal(state.roster[0].wargearSelections["iliastus-swap"], "1-twin-arachnus-heavy-blaze-cannon");
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
    assert.equal(calls.setRosterStatus.length, 1);
    assert.match(calls.setRosterStatus[0].message, /updated to 1 twin arachnus heavy blaze cannon/i);
    assert.equal(typeof calls.setRosterStatus[0].undoAction.onClick, "function");
    assert.equal(calls.setRosterStatus[0].undoAction.previewInstanceId, "entry-1");
    assert.deepEqual(calls.setRosterStatus[0].options, { previewInstanceId: "entry-1" });

    calls.setRosterStatus[0].undoAction.onClick();

    assert.equal(Object.hasOwn(state.roster[0].wargearSelections, "iliastus-swap"), false);
    assert.equal(calls.setRosterStatus.length, 2);
    assert.match(calls.setRosterStatus[1].message, /reverted/i);
    assert.deepEqual(calls.setRosterStatus[1].options, { previewInstanceId: "entry-1" });
});

test("handleRosterBodyChange updates counted allocation wargear and clamps to model count", () => {
    const { controller, state, calls } = createDeps();
    state.roster[0].optionId = "3-models";
    state.roster[0].optionIndex = 1;
    state.roster[0].wargearSelections = {
        "catapult-allocation": { mode: "allocation", counts: { "dark-lance": 1 } },
    };

    const handled = controller.handleRosterBodyChange(
        makeEvent(
            '[data-action="wargear-count"]',
            { instanceId: "entry-1", groupId: "catapult-allocation", choiceId: "scatter-laser" },
            { value: "3" }
        )
    );

    assert.equal(handled, true);
    assert.equal(state.roster[0].wargearSelections["catapult-allocation"].counts["dark-lance"], 1);
    assert.equal(state.roster[0].wargearSelections["catapult-allocation"].counts["scatter-laser"], 2);
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
});

test("handleRosterBodyChange enforces static allocation caps", () => {
    const { controller, state } = createDeps();
    state.roster[0].wargearSelections = {
        "catapult-allocation": { mode: "allocation", counts: { "dark-lance": 1 } },
    };
    state.roster[0].unitId = "caladius-grav-tank";
    state.roster[0].optionId = "1-model";
    state.roster[0].optionIndex = 0;
    const unit = sampleUnit();
    unit.wargear.options[1].allocationLimit = { kind: "static", max: 2 };

    const customController = App.createInteractionController({
        state,
        Store,
        renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
        catalogUnitById: () => unit,
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        renderRoster: () => {},
        renderPreview: () => {},
        scheduleAutoSave: () => {},
        setRosterStatus: () => {},
    });

    customController.handleRosterBodyChange(
        makeEvent(
            '[data-action="wargear-count"]',
            { instanceId: "entry-1", groupId: "catapult-allocation", choiceId: "scatter-laser" },
            { value: "4" }
        )
    );

    assert.equal(state.roster[0].wargearSelections["catapult-allocation"].counts["scatter-laser"], 1);
});

test("handleRosterBodyChange updates multi-pick wargear and respects pick caps", () => {
    const { controller, state, calls } = createDeps();

    assert.equal(controller.handleRosterBodyChange(
        makeEvent(
            '[data-action="wargear-multi-toggle"]',
            { instanceId: "entry-1", groupId: "sergeant-armory", choiceId: "bolt-pistol" },
            { checked: true }
        )
    ), true);
    assert.equal(controller.handleRosterBodyChange(
        makeEvent(
            '[data-action="wargear-multi-toggle"]',
            { instanceId: "entry-1", groupId: "sergeant-armory", choiceId: "power-weapon" },
            { checked: true }
        )
    ), true);

    assert.deepEqual(
        state.roster[0].wargearSelections["sergeant-armory"].choiceIds,
        ["bolt-pistol", "power-weapon"]
    );

    const rejectedEvent = makeEvent(
        '[data-action="wargear-multi-toggle"]',
        { instanceId: "entry-1", groupId: "sergeant-armory", choiceId: "twin-blades" },
        { checked: true }
    );
    assert.equal(controller.handleRosterBodyChange(rejectedEvent), true);
    assert.deepEqual(
        state.roster[0].wargearSelections["sergeant-armory"].choiceIds,
        ["bolt-pistol", "power-weapon"]
    );
    assert.equal(rejectedEvent.target.checked, false);

    assert.equal(calls.renderRoster, 2);
    assert.equal(calls.renderPreview, 2);
    assert.equal(calls.scheduleAutoSave, 2);
});

test("clearRoster empties the roster and records a status message", () => {
    const { controller, state, calls } = createDeps();
    controller.clearRoster();

    assert.equal(state.roster.length, 0);
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
    assert.equal(calls.setRosterStatus[0].message, "Cleared the active roster.");
});

test("updateArmyBattleSize persists the selected battle size and rerenders", () => {
    const { controller, state, calls } = createDeps();
    const handled = controller.updateArmyBattleSize("onslaught");

    assert.equal(handled, true);
    assert.equal(state.army.battleSize, "onslaught");
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
});

test("updateArmyWarlord selects a Character entry and ignores non-Characters", () => {
    const characterUnit = {
        unitId: "autarch",
        name: "Autarch",
        keywords: ["CHARACTER", "INFANTRY"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 90, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const vehicleUnit = sampleUnit();
    const state = {
        roster: [
            { instanceId: "entry-1", unitId: characterUnit.unitId, optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {} },
            { instanceId: "entry-2", unitId: vehicleUnit.unitId, optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {} },
        ],
        army: Store.normalizeArmyState({}),
    };
    const calls = { renderRoster: 0, renderPreview: 0, scheduleAutoSave: 0 };
    const controller = App.createInteractionController({
        state,
        Store,
        renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
        catalogUnitById: (unitId) => {
            if (unitId === characterUnit.unitId) {
                return characterUnit;
            }
            if (unitId === vehicleUnit.unitId) {
                return vehicleUnit;
            }
            return null;
        },
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        renderRoster: () => { calls.renderRoster += 1; },
        renderPreview: () => { calls.renderPreview += 1; },
        scheduleAutoSave: () => { calls.scheduleAutoSave += 1; },
        setRosterStatus: () => {},
    });

    assert.equal(controller.updateArmyWarlord("entry-2"), false);
    assert.equal(state.army.warlordInstanceId, null);

    assert.equal(controller.updateArmyWarlord("entry-1"), true);
    assert.equal(state.army.warlordInstanceId, "entry-1");
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
});

test("adding the first Character auto-selects Warlord and removing it falls back", () => {
    const characterUnit = {
        unitId: "autarch",
        name: "Autarch",
        keywords: ["CHARACTER", "INFANTRY"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 90, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const secondCharacterUnit = {
        unitId: "farseer",
        name: "Farseer",
        keywords: ["CHARACTER", "INFANTRY"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 80, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const state = { roster: [], army: Store.normalizeArmyState({}) };
    const controller = App.createInteractionController({
        state,
        Store,
        renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
        catalogUnitById: (unitId) => {
            if (unitId === characterUnit.unitId) {
                return characterUnit;
            }
            if (unitId === secondCharacterUnit.unitId) {
                return secondCharacterUnit;
            }
            return null;
        },
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        renderRoster: () => {},
        renderPreview: () => {},
        scheduleAutoSave: () => {},
        setRosterStatus: () => {},
    });

    controller.addToRoster("autarch");
    const firstId = state.roster[0].instanceId;
    assert.equal(state.army.warlordInstanceId, firstId);

    controller.addToRoster("farseer");
    const secondId = state.roster[1].instanceId;
    assert.equal(state.army.warlordInstanceId, firstId);

    controller.removeFromRoster(firstId);
    assert.equal(state.army.warlordInstanceId, secondId);

    controller.removeFromRoster(secondId);
    assert.equal(state.army.warlordInstanceId, null);
});

test("handleRosterBodyChange updates attachment and embark assignments", () => {
    const leaderUnit = {
        unitId: "autarch",
        name: "Autarch",
        keywords: ["CHARACTER", "INFANTRY"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 90, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const bodyguardUnit = {
        unitId: "guardian-defenders",
        name: "Guardian Defenders",
        keywords: ["INFANTRY"],
        pointsOptions: [{ id: "10-models", label: "10 models", points: 100, selectionKind: "models", modelCount: 10 }],
        wargear: { options: [] },
    };
    const transportUnit = {
        unitId: "wave-serpent",
        name: "Wave Serpent",
        keywords: ["VEHICLE", "TRANSPORT", "DEDICATED TRANSPORT"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 120, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const state = {
        roster: [
            { instanceId: "entry-hero", unitId: "autarch", optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: null, embarkedInInstanceId: null },
            { instanceId: "entry-bodyguard", unitId: "guardian-defenders", optionId: "10-models", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: null, embarkedInInstanceId: null },
            { instanceId: "entry-transport", unitId: "wave-serpent", optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: null, embarkedInInstanceId: null },
        ],
        army: Store.normalizeArmyState({}),
    };
    const calls = { renderRoster: 0, renderPreview: 0, scheduleAutoSave: 0 };
    const controller = App.createInteractionController({
        state,
        Store,
        renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
        catalogUnitById: (unitId) => ({
            autarch: leaderUnit,
            "guardian-defenders": bodyguardUnit,
            "wave-serpent": transportUnit,
        }[unitId] || null),
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        renderRoster: () => { calls.renderRoster += 1; },
        renderPreview: () => { calls.renderPreview += 1; },
        scheduleAutoSave: () => { calls.scheduleAutoSave += 1; },
        setRosterStatus: () => {},
    });

    assert.equal(controller.handleRosterBodyChange(
        makeEvent('[data-action="attachment-select"]', { instanceId: "entry-hero" }, { value: "entry-bodyguard" })
    ), true);
    assert.equal(state.roster[0].attachedToInstanceId, "entry-bodyguard");

    assert.equal(controller.handleRosterBodyChange(
        makeEvent('[data-action="embark-select"]', { instanceId: "entry-bodyguard" }, { value: "entry-transport" })
    ), true);
    assert.equal(state.roster[1].embarkedInInstanceId, "entry-transport");
    assert.equal(calls.renderRoster, 2);
    assert.equal(calls.renderPreview, 2);
    assert.equal(calls.scheduleAutoSave, 2);
});

test("removeFromRoster clears dependent attachment and embark references", () => {
    const leaderUnit = {
        unitId: "autarch",
        name: "Autarch",
        keywords: ["CHARACTER", "INFANTRY"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 90, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const bodyguardUnit = {
        unitId: "guardian-defenders",
        name: "Guardian Defenders",
        keywords: ["INFANTRY"],
        pointsOptions: [{ id: "10-models", label: "10 models", points: 100, selectionKind: "models", modelCount: 10 }],
        wargear: { options: [] },
    };
    const transportUnit = {
        unitId: "wave-serpent",
        name: "Wave Serpent",
        keywords: ["VEHICLE", "TRANSPORT", "DEDICATED TRANSPORT"],
        pointsOptions: [{ id: "1-model", label: "1 model", points: 120, selectionKind: "models", modelCount: 1 }],
        wargear: { options: [] },
    };
    const state = {
        roster: [
            { instanceId: "entry-hero", unitId: "autarch", optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: "entry-bodyguard", embarkedInInstanceId: null },
            { instanceId: "entry-bodyguard", unitId: "guardian-defenders", optionId: "10-models", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: null, embarkedInInstanceId: "entry-transport" },
            { instanceId: "entry-transport", unitId: "wave-serpent", optionId: "1-model", optionIndex: 0, upgradeOptionIds: [], quantity: 1, wargearSelections: {}, attachedToInstanceId: null, embarkedInInstanceId: null },
        ],
        army: Store.normalizeArmyState({ warlordInstanceId: "entry-hero" }),
    };
    const controller = App.createInteractionController({
        state,
        Store,
        renderer: { defaultPointsOption: (value) => value.pointsOptions[0] || null },
        catalogUnitById: (unitId) => ({
            autarch: leaderUnit,
            "guardian-defenders": bodyguardUnit,
            "wave-serpent": transportUnit,
        }[unitId] || null),
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        renderRoster: () => {},
        renderPreview: () => {},
        scheduleAutoSave: () => {},
        setRosterStatus: () => {},
    });

    controller.removeFromRoster("entry-bodyguard");
    assert.equal(state.roster.length, 2);
    assert.equal(state.roster[0].attachedToInstanceId, null);
    assert.equal(state.army.warlordInstanceId, "entry-hero");

    controller.removeFromRoster("entry-transport");
    assert.equal(state.roster.length, 1);
});

test("renderPreviewEntries renders configured HTML cards in configured mode", () => {
    const entry = samplePreviewEntry();
    const renderer = {
        renderCard(unit) {
            return `<article class="datasheet-card">${unit.name}</article>`;
        },
    };

    const html = App.renderPreviewEntries([entry], {
        previewSourceMode: "configured",
        previewRenderMode: "default",
        renderer,
        missingSourceCardLookup: new Set(),
    });

    assert.match(html, /datasheet-card/);
    assert.match(html, /data-preview-entry/);
    assert.match(html, /data-instance-id="preview-entry-1"/);
    assert.doesNotMatch(html, /source-card-image/);
});

test("createCatalogPreviewEntry derives a read-only preview model from a catalog unit", () => {
    const unit = sampleUnit();
    unit.support = {
        supportLevel: "partial",
        supportReasons: ["manual_wargear"],
        previewSupport: "configured-only",
    };
    const entry = App.createCatalogPreviewEntry(unit, {
        renderer: {
            defaultPointsOption(value) {
                return value.pointsOptions[1];
            },
        },
        pointsGroups: (value) => ({
            base: value.pointsOptions.filter((option) => option.selectionKind !== "upgrade"),
            upgrades: value.pointsOptions.filter((option) => option.selectionKind === "upgrade"),
        }),
        support: unit.support,
    });

    assert.equal(entry.unitId, unit.unitId);
    assert.equal(entry.displayName, unit.name);
    assert.equal(entry.selectedOption.id, "3-models");
    assert.equal(entry.optionId, "3-models");
    assert.equal(entry.optionIndex, 1);
    assert.equal(entry.linePoints, 300);
    assert.equal(entry.quantity, 1);
    assert.deepEqual(entry.selectedUpgrades, []);
    assert.deepEqual(entry.wargearSelections, []);
    assert.equal(entry.activeEnhancement, null);
    assert.equal(entry.relationship.attachedToInstanceId, null);
    assert.deepEqual(entry.support, unit.support);
    assert.equal(entry.canRepair, false);
});

test("renderPreviewEntry renders a single synthetic catalog preview card", () => {
    const entry = samplePreviewEntry({
        instanceId: "__catalog-preview__",
    });
    const renderer = {
        renderCard(unit) {
            return `<article class="datasheet-card">${unit.name}</article>`;
        },
    };

    const html = App.renderPreviewEntry(entry, {
        previewSourceMode: "configured",
        previewRenderMode: "default",
        renderer,
        missingSourceCardLookup: new Set(),
    });

    assert.match(html, /datasheet-card/);
    assert.match(html, /data-instance-id="__catalog-preview__"/);
});

test("renderPreviewEntries disables inline quick-swap controls in print-clean mode", () => {
    const entry = samplePreviewEntry({
        instanceId: "entry-inline",
    });
    const renderer = {
        renderCard(unit, options) {
            return options && options.interactiveInlineSelection
                ? `<article class="datasheet-card"><button data-action="card-inline-select">Quick swaps</button></article>`
                : `<article class="datasheet-card">${unit.name}</article>`;
        },
    };

    const html = App.renderPreviewEntries([entry], {
        previewSourceMode: "configured",
        previewRenderMode: "print-clean",
        renderer,
        missingSourceCardLookup: new Set(),
    });

    assert.match(html, /data-preview-entry/);
    assert.doesNotMatch(html, /data-action="card-inline-select"/);
    assert.doesNotMatch(html, /Quick swaps/);
});

test("chooseRestorableRoster prefers the active roster when its faction is available", () => {
    const choice = App.chooseRestorableRoster(
        [
            { id: "roster-1", factionSlug: "aeldari" },
            { id: "roster-2", factionSlug: "adeptus-custodes" },
        ],
        "roster-2",
        ["adeptus-custodes"]
    );

    assert.deepEqual(choice, { rosterId: "roster-2", reason: "active" });
});

test("chooseRestorableRoster falls back when the active roster faction is unavailable", () => {
    const choice = App.chooseRestorableRoster(
        [
            { id: "roster-1", factionSlug: "space-wolves" },
            { id: "roster-2", factionSlug: "adeptus-custodes" },
        ],
        "roster-1",
        ["adeptus-custodes"]
    );

    assert.deepEqual(choice, { rosterId: "roster-2", reason: "fallback-from-unavailable-active" });
});

test("renderPreviewEntries renders Wahapedia image cards when a source PNG is available", () => {
    const entry = samplePreviewEntry();
    const renderer = {
        renderCard(unit) {
            return `<article class="datasheet-card">${unit.name}</article>`;
        },
    };

    const html = App.renderPreviewEntries([entry], {
        previewSourceMode: "source-image",
        previewRenderMode: "default",
        renderer,
        missingSourceCardLookup: new Set(),
    });

    assert.match(html, /data-source-card-mode="image"/);
    assert.match(html, /source-card-image/);
    assert.match(html, /Open source image/);
    assert.match(html, /loading="eager"/);
    assert.match(html, /data-source-card-meta-fallback hidden/);
});

test("renderPreviewEntries falls back to configured HTML cards when the source PNG is missing", () => {
    const entry = samplePreviewEntry({
        unit: {
            ...sampleUnit(),
            name: "Captain Sicarius",
            source: {
                outputSlug: "ultramarines",
                datasheetSlug: "Captain-Sicarius",
            },
        },
        displayName: "Captain Sicarius",
    });
    const renderer = {
        renderCard(unit) {
            return `<article class="datasheet-card">${unit.name}</article>`;
        },
    };
    const missing = new Set(["ultramarines::Captain-Sicarius"]);

    const html = App.renderPreviewEntries([entry], {
        previewSourceMode: "source-image",
        previewRenderMode: "default",
        renderer,
        missingSourceCardLookup: missing,
    });

    assert.match(html, /Wahapedia image unavailable; using configured card/);
    assert.match(html, /datasheet-card/);
    assert.doesNotMatch(html, /source-card-image/);
});

test("renderPrintPackSummary renders a paper-first roster summary sheet", () => {
    const html = App.renderPrintPackSummary({
        rosterName: "Swordwind Strike",
        factionName: "Aeldari",
        battleSizeLabel: "Strike Force",
        detachmentName: "Warhost",
        totalPoints: 2000,
        pointsLimit: 2000,
        previewSourceMode: "configured",
        printableCount: 2,
        configuredFallbackCount: 1,
        excludedEntries: ["Missing Unit"],
        rows: [
            {
                quantity: 1,
                displayName: "Autarch",
                linePoints: 125,
                enhancementName: "Phoenix Gem",
                loadoutText: "1 model • Enhancement: Phoenix Gem",
                noteText: "Builder fallback card",
            },
        ],
    });

    assert.match(html, /data-print-pack-summary/);
    assert.match(html, /Swordwind Strike/);
    assert.match(html, /Configured cards/);
    assert.match(html, /Builder fallback card/);
    assert.match(html, /Excluded from print:/);
});

test("renderPrintPackSummary preserves source-image mode labeling", () => {
    const html = App.renderPrintPackSummary({
        rosterName: "Source Pack",
        factionName: "Aeldari",
        battleSizeLabel: "Strike Force",
        detachmentName: "Warhost",
        totalPoints: 1000,
        pointsLimit: 1000,
        previewSourceMode: "source-image",
        printableCount: 1,
        rows: [],
    });

    assert.match(html, /Original Wahapedia cards/);
});

test("waitForPreviewImages resolves when source preview images finish loading", async () => {
    let loadHandler = null;
    let errorHandler = null;
    let removedLoadHandler = null;
    let removedErrorHandler = null;
    const image = {
        complete: false,
        loading: "lazy",
        addEventListener(type, handler) {
            if (type === "load") {
                loadHandler = handler;
            }
            if (type === "error") {
                errorHandler = handler;
            }
        },
        removeEventListener(type, handler) {
            if (type === "load") {
                removedLoadHandler = handler;
            }
            if (type === "error") {
                removedErrorHandler = handler;
            }
        },
    };
    const previewRoot = {
        querySelectorAll(selector) {
            assert.equal(selector, ".source-card-image");
            return [image];
        },
    };

    const waiting = App.waitForPreviewImages(previewRoot, 50);

    assert.equal(image.loading, "eager");
    assert.equal(typeof loadHandler, "function");
    assert.equal(typeof errorHandler, "function");

    loadHandler();
    await waiting;

    assert.equal(removedLoadHandler, loadHandler);
    assert.equal(removedErrorHandler, errorHandler);
});

test("printPreviewCards prints the current preview mode without forcing configured mode", async () => {
    const renderableEntries = [samplePreviewEntry()];
    const calls = { print: 0, alert: 0 };
    const previewRoot = {
        querySelectorAll(selector) {
            assert.equal(selector, ".source-card-image");
            return [{ complete: true, loading: "lazy" }];
        },
    };

    const result = await App.printPreviewCards({
        renderableEntries,
        previewSourceMode: "source-image",
        previewRoot,
        alertFn: () => { calls.alert += 1; },
        printFn: () => { calls.print += 1; },
    });

    assert.equal(result.printed, true);
    assert.equal(result.previewSourceMode, "source-image");
    assert.equal(calls.print, 1);
    assert.equal(calls.alert, 0);
});

test("printPreviewCards alerts when there are no renderable entries", async () => {
    const calls = { print: 0, alert: 0 };

    const result = await App.printPreviewCards({
        renderableEntries: [],
        previewSourceMode: "configured",
        alertFn: () => { calls.alert += 1; },
        printFn: () => { calls.print += 1; },
    });

    assert.equal(result.printed, false);
    assert.equal(calls.print, 0);
    assert.equal(calls.alert, 1);
});
