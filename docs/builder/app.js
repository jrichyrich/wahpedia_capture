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

        function resolveBaseOption(unit, entry) {
            if (!unit) {
                return null;
            }
            const baseOptions = pointsGroups(unit).base;
            const allOptions = Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [];
            if (entry.optionId) {
                const byId = allOptions.find((option) => option.id === entry.optionId) || null;
                if (byId && byId.selectionKind !== "upgrade") {
                    return byId;
                }
            }
            if (Number.isInteger(entry.optionIndex) && baseOptions[entry.optionIndex]) {
                return baseOptions[entry.optionIndex];
            }
            return renderer.defaultPointsOption(unit);
        }

        function allocationLimit(unit, entry, group) {
            if (!group || group.selectionMode !== "allocation") {
                return null;
            }
            const selectedOption = resolveBaseOption(unit, entry);
            const modelCount = selectedOption && typeof selectedOption.modelCount === "number"
                ? selectedOption.modelCount
                : null;
            if (!group.allocationLimit || group.allocationLimit === "modelCount") {
                return modelCount;
            }
            if (typeof group.allocationLimit === "object") {
                if (group.allocationLimit.kind === "modelCount") {
                    return modelCount;
                }
                if (group.allocationLimit.kind === "static") {
                    return typeof group.allocationLimit.max === "number" ? group.allocationLimit.max : null;
                }
                if (group.allocationLimit.kind === "ratio" && modelCount !== null) {
                    const perModels = Number(group.allocationLimit.perModels) || 0;
                    const maxPerStep = Number(group.allocationLimit.maxPerStep) || 0;
                    if (perModels > 0 && maxPerStep > 0) {
                        return Math.floor(modelCount / perModels) * maxPerStep;
                    }
                    return 0;
                }
            }
            return null;
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

        function updateRosterWargearAllocation(instanceId, groupId, choiceId, countValue) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            const unit = catalogUnitById(entry.unitId);
            const group = unit && unit.wargear && Array.isArray(unit.wargear.options)
                ? unit.wargear.options.find((option) => option.id === groupId)
                : null;
            if (!group || group.selectionMode !== "allocation") {
                return false;
            }
            const requestedCount = Math.max(0, Number.parseInt(countValue, 10) || 0);
            const currentValue = entry.wargearSelections && typeof entry.wargearSelections[groupId] === "object"
                ? entry.wargearSelections[groupId]
                : {};
            const counts = {
                ...((currentValue.mode === "allocation" && currentValue.counts && typeof currentValue.counts === "object")
                    ? currentValue.counts
                    : currentValue),
            };

            const limit = allocationLimit(unit, entry, group);
            const otherTotal = Object.entries(counts).reduce((sum, [savedChoiceId, savedCount]) => {
                if (savedChoiceId === choiceId) {
                    return sum;
                }
                return sum + Math.max(0, Number.parseInt(savedCount, 10) || 0);
            }, 0);
            const normalizedCount = limit === null
                ? requestedCount
                : Math.max(0, Math.min(requestedCount, Math.max(0, limit - otherTotal)));

            if (!entry.wargearSelections || typeof entry.wargearSelections !== "object") {
                entry.wargearSelections = {};
            }
            if (normalizedCount > 0) {
                counts[choiceId] = normalizedCount;
            } else {
                delete counts[choiceId];
            }
            if (Object.keys(counts).length) {
                entry.wargearSelections[groupId] = { mode: "allocation", counts };
            } else {
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
            const wargearCount = target && typeof target.closest === "function"
                ? target.closest('[data-action="wargear-count"]')
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
            if (wargearCount) {
                return updateRosterWargearAllocation(
                    wargearCount.dataset.instanceId,
                    wargearCount.dataset.groupId,
                    wargearCount.dataset.choiceId,
                    wargearCount.value
                );
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
            updateRosterWargearAllocation,
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
