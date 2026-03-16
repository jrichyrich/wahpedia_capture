const test = require("node:test");
const assert = require("node:assert/strict");

const App = require("../docs/builder/app.js");
const Store = require("../docs/builder/roster_store.js");

function sampleUnit() {
    return {
        unitId: "caladius-grav-tank",
        name: "Caladius Grav-tank",
        pointsOptions: [
            { id: "1-model", label: "1 model", points: 215, selectionKind: "models" },
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
        }],
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
            setRosterStatus: (message, isError) => { calls.setRosterStatus.push({ message, isError }); },
        }),
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

test("clearRoster empties the roster and records a status message", () => {
    const { controller, state, calls } = createDeps();
    controller.clearRoster();

    assert.equal(state.roster.length, 0);
    assert.equal(calls.renderRoster, 1);
    assert.equal(calls.renderPreview, 1);
    assert.equal(calls.scheduleAutoSave, 1);
    assert.equal(calls.setRosterStatus[0].message, "Cleared the active roster.");
});
