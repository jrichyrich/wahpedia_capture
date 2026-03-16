(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
        return;
    }
    root.WahBuilderApp = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function eventElementTarget(event) {
        if (!event) {
            return null;
        }
        if (typeof Element !== "undefined" && event.target instanceof Element) {
            return event.target;
        }
        if (event.target && event.target.parentElement) {
            return event.target.parentElement;
        }
        return event.target || null;
    }

    function createInteractionController(deps) {
        const {
            state,
            Store,
            renderer,
            catalogUnitById,
            pointsGroups,
            renderRoster,
            renderPreview,
            scheduleAutoSave,
            setRosterStatus,
        } = deps;

        function rerenderAndPersist() {
            renderRoster();
            renderPreview();
            scheduleAutoSave();
        }

        function addToRoster(unitId) {
            const unit = catalogUnitById(unitId);
            if (!unit) {
                return false;
            }
            const defaultOption = renderer.defaultPointsOption(unit);
            state.roster.push({
                instanceId: Store.createRosterId(),
                unitId,
                optionId: defaultOption ? defaultOption.id : null,
                optionIndex: defaultOption ? unit.pointsOptions.indexOf(defaultOption) : null,
                upgradeOptionIds: [],
                quantity: 1,
                wargearSelections: {},
            });
            rerenderAndPersist();
            return true;
        }

        function updateRosterOption(instanceId, optionIndex) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            const unit = catalogUnitById(entry.unitId);
            const normalizedIndex = Number(optionIndex);
            const baseOptions = unit ? pointsGroups(unit).base : [];
            const option = unit && normalizedIndex >= 0
                ? (baseOptions[normalizedIndex] || null)
                : null;
            entry.optionIndex = Number.isInteger(normalizedIndex) ? normalizedIndex : null;
            entry.optionId = option ? option.id : null;
            rerenderAndPersist();
            return true;
        }

        function updateRosterUpgrade(instanceId, optionId, checked) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            const selected = new Set(Array.isArray(entry.upgradeOptionIds) ? entry.upgradeOptionIds : []);
            if (checked) {
                selected.add(String(optionId));
            } else {
                selected.delete(String(optionId));
            }
            entry.upgradeOptionIds = Array.from(selected);
            rerenderAndPersist();
            return true;
        }

        function updateRosterQuantity(instanceId, quantity) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            entry.quantity = Math.max(1, Number(quantity) || 1);
            rerenderAndPersist();
            return true;
        }

        function updateRosterWargear(instanceId, groupId, choiceId) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            entry.wargearSelections = entry.wargearSelections || {};
            entry.wargearSelections[groupId] = choiceId ? String(choiceId) : null;
            if (!entry.wargearSelections[groupId]) {
                delete entry.wargearSelections[groupId];
            }
            rerenderAndPersist();
            return true;
        }

        function removeFromRoster(instanceId) {
            const before = state.roster.length;
            state.roster = state.roster.filter((item) => item.instanceId !== instanceId);
            if (state.roster.length === before) {
                return false;
            }
            rerenderAndPersist();
            return true;
        }

        function clearRoster() {
            state.roster = [];
            rerenderAndPersist();
            if (setRosterStatus) {
                setRosterStatus("Cleared the active roster.", false);
            }
            return true;
        }

        function handleUnitListClick(event) {
            const target = eventElementTarget(event);
            const addButton = target && typeof target.closest === "function"
                ? target.closest('[data-action="add-unit"]')
                : null;
            if (addButton) {
                return addToRoster(addButton.dataset.unitId);
            }
            return false;
        }

        function handleRosterBodyChange(event) {
            const target = eventElementTarget(event);
            const select = target && typeof target.closest === "function"
                ? target.closest('[data-action="option-select"]')
                : null;
            const upgrade = target && typeof target.closest === "function"
                ? target.closest('[data-action="upgrade-toggle"]')
                : null;
            const wargear = target && typeof target.closest === "function"
                ? target.closest('[data-action="wargear-select"]')
                : null;
            const quantity = target && typeof target.closest === "function"
                ? target.closest('[data-action="quantity-input"]')
                : null;

            if (select) {
                return updateRosterOption(select.dataset.instanceId, select.value);
            }
            if (upgrade) {
                return updateRosterUpgrade(upgrade.dataset.instanceId, upgrade.dataset.optionId, upgrade.checked);
            }
            if (wargear) {
                return updateRosterWargear(wargear.dataset.instanceId, wargear.dataset.groupId, wargear.value);
            }
            if (quantity) {
                return updateRosterQuantity(quantity.dataset.instanceId, quantity.value);
            }
            return false;
        }

        function handleRosterBodyClick(event) {
            const target = eventElementTarget(event);
            const button = target && typeof target.closest === "function"
                ? target.closest('[data-action="remove-entry"]')
                : null;
            if (button) {
                return removeFromRoster(button.dataset.instanceId);
            }
            return false;
        }

        return {
            addToRoster,
            updateRosterOption,
            updateRosterUpgrade,
            updateRosterQuantity,
            updateRosterWargear,
            removeFromRoster,
            clearRoster,
            handleUnitListClick,
            handleRosterBodyChange,
            handleRosterBodyClick,
        };
    }

    return {
        createInteractionController,
        eventElementTarget,
    };
});
