(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
        return;
    }
    root.WahBuilderApp = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

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

    function sourceCardLookupKey(unitOrSource) {
        const source = unitOrSource && unitOrSource.source ? unitOrSource.source : unitOrSource;
        const outputSlug = String(source && source.outputSlug ? source.outputSlug : "").trim();
        const datasheetSlug = String(source && source.datasheetSlug ? source.datasheetSlug : "").trim();
        if (!outputSlug || !datasheetSlug) {
            return "";
        }
        return `${outputSlug}::${datasheetSlug}`;
    }

    function sourceCardUrl(unit) {
        const source = unit && unit.source ? unit.source : null;
        if (!source || !source.outputSlug || !source.datasheetSlug) {
            return null;
        }
        return `./data/source-cards/${encodeURIComponent(source.outputSlug)}/${encodeURIComponent(source.datasheetSlug)}.png`;
    }

    function buildMissingSourceCardLookup(report) {
        const lookup = new Set();
        if (!report || !Array.isArray(report.factions)) {
            return lookup;
        }

        report.factions.forEach((faction) => {
            const missingCards = Array.isArray(faction && faction.missingSourceCards)
                ? faction.missingSourceCards
                : [];
            missingCards.forEach((entry) => {
                const reason = String(entry && entry.reason ? entry.reason : "");
                const path = reason.startsWith("missing-file:") ? reason.slice("missing-file:".length) : "";
                const match = path.match(/\/([^/]+)\/([^/]+)\.png$/i);
                if (!match) {
                    return;
                }
                lookup.add(`${match[1]}::${match[2]}`);
            });
        });

        return lookup;
    }

    function buildRendererOptions(entry, previewRenderMode) {
        const unit = entry && entry.unit ? entry.unit : null;
        return {
            selectedOption: entry ? entry.selectedOption : null,
            selectedUpgrades: entry ? entry.selectedUpgrades : [],
            selectedPoints: entry ? entry.linePoints : null,
            quantity: entry ? entry.quantity : 1,
            renderMode: previewRenderMode || "default",
            selectedWargear: entry ? entry.wargearSelections : [],
            relationshipNotes: entry && entry.relationship && Array.isArray(entry.relationship.relationshipNotes)
                ? entry.relationship.relationshipNotes
                : [],
            manualWargearGroups: unit && unit.wargear
                ? unit.wargear.options.filter((group) => group.selectionMode === "manual")
                : [],
        };
    }

    function renderConfiguredPreviewCard(entry, options) {
        const renderer = options && options.renderer;
        const unit = entry && entry.unit ? entry.unit : null;
        if (!renderer || !unit || typeof renderer.renderCard !== "function") {
            return "";
        }
        return renderer.renderCard(unit, buildRendererOptions(entry, options.previewRenderMode));
    }

    function renderSourcePreviewCard(entry, options) {
        const unit = entry && entry.unit ? entry.unit : null;
        const safeName = escapeHtml(entry && entry.displayName ? entry.displayName : (unit && unit.name ? unit.name : "Unknown unit"));
        const url = sourceCardUrl(unit);
        const missingLookup = options && options.missingSourceCardLookup instanceof Set
            ? options.missingSourceCardLookup
            : null;
        const isKnownMissing = !url || Boolean(missingLookup && missingLookup.has(sourceCardLookupKey(unit)));
        const fallbackCard = renderConfiguredPreviewCard(entry, options);
        const fallbackMarkup = fallbackCard
            ? `
                <div class="source-card-fallback" data-source-card-fallback>
                    ${fallbackCard}
                </div>
            `
            : `<div class="source-card-missing inline-note inline-note-warning">Configured HTML card is not available for this unit.</div>`;

        if (isKnownMissing) {
            return `
                <section class="source-card source-card-fallback-card" data-source-card-mode="fallback">
                    <div class="source-card-header">
                        <h3 class="source-card-title">${safeName}</h3>
                        <div class="source-card-meta source-card-meta-warning">Wahapedia image unavailable; using configured card</div>
                    </div>
                    ${fallbackMarkup}
                </section>
            `;
        }

        return `
            <section class="source-card" data-source-card-mode="image">
                <div class="source-card-header">
                    <h3 class="source-card-title">${safeName}</h3>
                    <div class="source-card-meta" data-source-card-meta-default>Original Wahapedia source card</div>
                    <div class="source-card-meta source-card-meta-warning" data-source-card-meta-fallback hidden>Wahapedia image unavailable; using configured card</div>
                </div>
                <div class="source-card-image-wrap" data-source-card-image-wrap>
                    <img
                        class="source-card-image"
                        src="${url}"
                        alt="Original Wahapedia card for ${safeName}"
                        loading="lazy"
                        onerror="var card=this.closest('.source-card'); if(card){ var imageWrap=card.querySelector('[data-source-card-image-wrap]'); var fallback=card.querySelector('[data-source-card-fallback]'); var defaultMeta=card.querySelector('[data-source-card-meta-default]'); var fallbackMeta=card.querySelector('[data-source-card-meta-fallback]'); var actions=card.querySelector('[data-source-card-actions]'); card.dataset.sourceCardMode='fallback'; if(imageWrap){ imageWrap.hidden=true; } if(fallback){ fallback.hidden=false; } if(defaultMeta){ defaultMeta.hidden=true; } if(fallbackMeta){ fallbackMeta.hidden=false; } if(actions){ actions.hidden=true; } }"
                    >
                </div>
                <div class="source-card-actions" data-source-card-actions>
                    <a class="btn" href="${url}" target="_blank" rel="noopener noreferrer">Open source image</a>
                </div>
                <div class="source-card-fallback" data-source-card-fallback hidden>
                    ${fallbackCard}
                </div>
            </section>
        `;
    }

    function renderPreviewEntries(entries, options) {
        const previewSourceMode = options && options.previewSourceMode ? options.previewSourceMode : "configured";
        const renderableEntries = Array.isArray(entries) ? entries : [];
        if (previewSourceMode === "source-image") {
            return renderableEntries.map((entry) => renderSourcePreviewCard(entry, options)).join("");
        }
        return renderableEntries.map((entry) => renderConfiguredPreviewCard(entry, options)).join("");
    }

    function printPreviewCards(options) {
        const renderableEntries = Array.isArray(options && options.renderableEntries)
            ? options.renderableEntries
            : [];
        const previewSourceMode = options && options.previewSourceMode ? options.previewSourceMode : "configured";
        if (!renderableEntries.length) {
            if (typeof options.alertFn === "function") {
                options.alertFn("Add at least one resolved unit before printing.");
            }
            return { printed: false, previewSourceMode };
        }
        if (typeof options.printFn === "function") {
            options.printFn();
        }
        return { printed: true, previewSourceMode };
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

        function ensureArmyState() {
            state.army = Store.normalizeArmyState(state.army);
            return state.army;
        }

        function isCharacterUnit(unit) {
            return Boolean(unit && Array.isArray(unit.keywords) && unit.keywords.includes("CHARACTER"));
        }

        function ensureWarlordSelection(preferredInstanceId) {
            const army = ensureArmyState();
            const characterEntryIds = state.roster
                .filter((item) => isCharacterUnit(catalogUnitById(item.unitId)))
                .map((item) => item.instanceId);

            if (!characterEntryIds.length) {
                army.warlordInstanceId = null;
                return null;
            }

            if (preferredInstanceId && characterEntryIds.includes(preferredInstanceId) && !army.warlordInstanceId) {
                army.warlordInstanceId = preferredInstanceId;
                return army.warlordInstanceId;
            }

            if (army.warlordInstanceId && characterEntryIds.includes(army.warlordInstanceId)) {
                return army.warlordInstanceId;
            }

            army.warlordInstanceId = characterEntryIds[0];
            return army.warlordInstanceId;
        }

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

        function resolveSelectionLimit(unit, entry, group, limitSpec) {
            if (!group) {
                return null;
            }
            const selectedOption = resolveBaseOption(unit, entry);
            const modelCount = selectedOption && typeof selectedOption.modelCount === "number"
                ? selectedOption.modelCount
                : null;
            if (typeof limitSpec === "undefined") {
                return modelCount;
            }
            if (limitSpec === null) {
                return null;
            }
            if (limitSpec === "modelCount") {
                return modelCount;
            }
            if (typeof limitSpec === "object") {
                if (limitSpec.kind === "modelCount") {
                    return modelCount;
                }
                if (limitSpec.kind === "static") {
                    return typeof limitSpec.max === "number" ? limitSpec.max : null;
                }
                if (limitSpec.kind === "ratio" && modelCount !== null) {
                    const perModels = Number(limitSpec.perModels) || 0;
                    const maxPerStep = Number(limitSpec.maxPerStep) || 0;
                    if (perModels > 0 && maxPerStep > 0) {
                        return Math.floor(modelCount / perModels) * maxPerStep;
                    }
                    return 0;
                }
            }
            return null;
        }

        function allocationLimit(unit, entry, group) {
            if (!group || group.selectionMode !== "allocation") {
                return null;
            }
            return resolveSelectionLimit(unit, entry, group, group.allocationLimit);
        }

        function addToRoster(unitId) {
            const unit = catalogUnitById(unitId);
            if (!unit) {
                return false;
            }
            const defaultOption = renderer.defaultPointsOption(unit);
            const entry = {
                instanceId: Store.createRosterId(),
                unitId,
                optionId: defaultOption ? defaultOption.id : null,
                optionIndex: defaultOption ? unit.pointsOptions.indexOf(defaultOption) : null,
                upgradeOptionIds: [],
                quantity: 1,
                wargearSelections: {},
                attachedToInstanceId: null,
                embarkedInInstanceId: null,
            };
            state.roster.push(entry);
            ensureWarlordSelection(isCharacterUnit(unit) ? entry.instanceId : null);
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

        function updateRosterWargearMulti(instanceId, groupId, choiceId, checked, inputElement) {
            const entry = state.roster.find((item) => item.instanceId === instanceId);
            if (!entry) {
                return false;
            }
            const unit = catalogUnitById(entry.unitId);
            const group = unit && unit.wargear && Array.isArray(unit.wargear.options)
                ? unit.wargear.options.find((option) => option.id === groupId)
                : null;
            if (!group || group.selectionMode !== "multi") {
                return false;
            }
            const currentValue = entry.wargearSelections && entry.wargearSelections[groupId];
            const savedChoiceIds = Array.isArray(currentValue)
                ? currentValue
                : (currentValue && typeof currentValue === "object" && Array.isArray(currentValue.choiceIds)
                    ? currentValue.choiceIds
                    : []);
            const selectedIds = [];
            savedChoiceIds.forEach((savedId) => {
                const normalizedId = String(savedId || "").trim();
                if (normalizedId && !selectedIds.includes(normalizedId)) {
                    selectedIds.push(normalizedId);
                }
            });

            const targetChoice = (group.choices || []).find((choice) => choice.id === choiceId) || null;
            if (!targetChoice) {
                return false;
            }
            const currentCost = selectedIds.reduce((sum, savedId) => {
                const savedChoice = (group.choices || []).find((choice) => choice.id === savedId) || null;
                return sum + Math.max(1, Number.parseInt(savedChoice && savedChoice.pickCost, 10) || 1);
            }, 0);
            const targetCost = Math.max(1, Number.parseInt(targetChoice.pickCost, 10) || 1);
            const maxPicks = typeof group.pickCount === "number" ? group.pickCount : null;

            if (checked) {
                if (!selectedIds.includes(choiceId)) {
                    const nextCost = currentCost + targetCost;
                    if (maxPicks !== null && nextCost > maxPicks) {
                        if (inputElement && typeof inputElement.checked === "boolean") {
                            inputElement.checked = false;
                        }
                        return true;
                    }
                    selectedIds.push(choiceId);
                }
            } else {
                const index = selectedIds.indexOf(choiceId);
                if (index >= 0) {
                    selectedIds.splice(index, 1);
                }
            }

            if (!entry.wargearSelections || typeof entry.wargearSelections !== "object") {
                entry.wargearSelections = {};
            }
            if (selectedIds.length) {
                entry.wargearSelections[groupId] = { mode: "multi", choiceIds: selectedIds };
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
            clearRelationshipsForRemovedEntry(instanceId);
            ensureWarlordSelection();
            rerenderAndPersist();
            return true;
        }

        function clearRoster() {
            state.roster = [];
            ensureArmyState().warlordInstanceId = null;
            rerenderAndPersist();
            if (setRosterStatus) {
                setRosterStatus("Cleared the active roster.", false);
            }
            return true;
        }

        function updateArmyBattleSize(battleSize) {
            ensureArmyState().battleSize = Store.normalizeArmyState({ battleSize }).battleSize;
            rerenderAndPersist();
            return true;
        }

        function updateArmyWarlord(instanceId) {
            const army = ensureArmyState();
            const entry = state.roster.find((item) => item.instanceId === instanceId) || null;
            const unit = entry ? catalogUnitById(entry.unitId) : null;
            if (!entry || !isCharacterUnit(unit)) {
                return false;
            }
            army.warlordInstanceId = entry.instanceId;
            rerenderAndPersist();
            return true;
        }

        function updateRosterAttachment(instanceId, targetInstanceId) {
            const entry = state.roster.find((item) => item.instanceId === instanceId) || null;
            if (!entry) {
                return false;
            }
            entry.attachedToInstanceId = targetInstanceId ? String(targetInstanceId).trim() || null : null;
            if (entry.attachedToInstanceId) {
                entry.embarkedInInstanceId = null;
            }
            rerenderAndPersist();
            return true;
        }

        function updateRosterEmbark(instanceId, transportInstanceId) {
            const entry = state.roster.find((item) => item.instanceId === instanceId) || null;
            if (!entry) {
                return false;
            }
            if (entry.attachedToInstanceId) {
                return false;
            }
            entry.embarkedInInstanceId = transportInstanceId ? String(transportInstanceId).trim() || null : null;
            rerenderAndPersist();
            return true;
        }

        function clearRelationshipsForRemovedEntry(instanceId) {
            state.roster.forEach((item) => {
                if (item.attachedToInstanceId === instanceId) {
                    item.attachedToInstanceId = null;
                }
                if (item.embarkedInInstanceId === instanceId) {
                    item.embarkedInInstanceId = null;
                }
            });
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
            const wargearMulti = target && typeof target.closest === "function"
                ? target.closest('[data-action="wargear-multi-toggle"]')
                : null;
            const warlord = target && typeof target.closest === "function"
                ? target.closest('[data-action="warlord-select"]')
                : null;
            const attachment = target && typeof target.closest === "function"
                ? target.closest('[data-action="attachment-select"]')
                : null;
            const embark = target && typeof target.closest === "function"
                ? target.closest('[data-action="embark-select"]')
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
            if (wargearMulti) {
                return updateRosterWargearMulti(
                    wargearMulti.dataset.instanceId,
                    wargearMulti.dataset.groupId,
                    wargearMulti.dataset.choiceId,
                    wargearMulti.checked,
                    wargearMulti
                );
            }
            if (warlord) {
                return updateArmyWarlord(warlord.dataset.instanceId);
            }
            if (attachment) {
                return updateRosterAttachment(attachment.dataset.instanceId, attachment.value);
            }
            if (embark) {
                return updateRosterEmbark(embark.dataset.instanceId, embark.value);
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
            updateRosterWargearMulti,
            updateArmyBattleSize,
            updateArmyWarlord,
            updateRosterAttachment,
            updateRosterEmbark,
            removeFromRoster,
            clearRoster,
            handleUnitListClick,
            handleRosterBodyChange,
            handleRosterBodyClick,
        };
    }

    return {
        buildMissingSourceCardLookup,
        createInteractionController,
        eventElementTarget,
        printPreviewCards,
        renderPreviewEntries,
        sourceCardLookupKey,
        sourceCardUrl,
    };
});
