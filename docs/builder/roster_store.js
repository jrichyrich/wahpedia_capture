(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
        return;
    }
    root.WahBuilderRosterStore = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const ROSTER_SCHEMA_VERSION = 4;
    const STORAGE_NAMESPACE = "wahpediaCapture.builder.v1";
    const INDEX_KEY = `${STORAGE_NAMESPACE}.savedRosters`;
    const ACTIVE_KEY = `${STORAGE_NAMESPACE}.activeRosterId`;
    const DEFAULT_BATTLE_SIZE = "strike-force";
    const BATTLE_SIZE_POINTS = Object.freeze({
        incursion: 1000,
        "strike-force": 2000,
        onslaught: 3000,
    });

    function nowIso() {
        return new Date().toISOString();
    }

    function createRosterId() {
        return `roster-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    }

    function slugToTitle(slug) {
        return String(slug || "")
            .split("-")
            .filter(Boolean)
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join(" ");
    }

    function normalizeName(name, factionSlug) {
        const trimmed = String(name || "").trim();
        if (trimmed) {
            return trimmed.slice(0, 80);
        }
        return factionSlug ? `${slugToTitle(factionSlug)} Roster` : "New Roster";
    }

    function normalizeQuantity(quantity) {
        return Math.max(1, Number(quantity) || 1);
    }

    function normalizeBattleSize(value) {
        const normalized = String(value || "").trim();
        return Object.prototype.hasOwnProperty.call(BATTLE_SIZE_POINTS, normalized)
            ? normalized
            : DEFAULT_BATTLE_SIZE;
    }

    function battleSizePoints(battleSize) {
        return BATTLE_SIZE_POINTS[normalizeBattleSize(battleSize)];
    }

    function normalizeArmyState(army) {
        const payload = army && typeof army === "object" ? army : {};
        const battleSize = normalizeBattleSize(payload.battleSize || payload.battle_size);
        const warlordInstanceId = payload.warlordInstanceId || payload.warlord_instance_id;
        const normalizedWarlordId = warlordInstanceId ? String(warlordInstanceId).trim() : null;
        return {
            battleSize,
            warlordInstanceId: normalizedWarlordId || null,
        };
    }

    function createStorageAdapter(storage) {
        if (!storage) {
            return null;
        }
        try {
            const probe = `${STORAGE_NAMESPACE}.probe`;
            storage.setItem(probe, "1");
            storage.removeItem(probe);
            return storage;
        } catch (error) {
            return null;
        }
    }

    function readJson(storage, key, fallback) {
        if (!storage) {
            return fallback;
        }
        try {
            const raw = storage.getItem(key);
            if (!raw) {
                return fallback;
            }
            return JSON.parse(raw);
        } catch (error) {
            return fallback;
        }
    }

    function writeJson(storage, key, value) {
        if (!storage) {
            return false;
        }
        storage.setItem(key, JSON.stringify(value));
        return true;
    }

    function rosterKey(rosterId) {
        return `${STORAGE_NAMESPACE}.roster.${rosterId}`;
    }

    function normalizeSavedEntry(entry) {
        if (!entry || typeof entry !== "object") {
            throw new Error("Roster entry must be an object.");
        }
        const unitId = String(entry.unitId || "").trim();
        if (!unitId) {
            throw new Error("Roster entry is missing unitId.");
        }
        const wargearSelections = {};
        if (entry.wargearSelections && typeof entry.wargearSelections === "object") {
            Object.entries(entry.wargearSelections).forEach(([groupId, value]) => {
                const normalizedGroupId = String(groupId || "").trim();
                if (!normalizedGroupId) {
                    return;
                }
                if (value && typeof value === "object" && !Array.isArray(value)) {
                    if (value.mode === "multi" && Array.isArray(value.choiceIds)) {
                        const choiceIds = value.choiceIds
                            .map((choiceId) => String(choiceId || "").trim())
                            .filter(Boolean);
                        if (choiceIds.length) {
                            wargearSelections[normalizedGroupId] = { mode: "multi", choiceIds };
                        }
                        return;
                    }
                    const rawCounts = value.mode === "allocation" && value.counts && typeof value.counts === "object"
                        ? value.counts
                        : value;
                    const counts = {};
                    Object.entries(rawCounts).forEach(([choiceId, count]) => {
                        const normalizedChoiceId = String(choiceId || "").trim();
                        const normalizedCount = Math.max(0, Number.parseInt(count, 10) || 0);
                        if (normalizedChoiceId && normalizedCount > 0) {
                            counts[normalizedChoiceId] = normalizedCount;
                        }
                    });
                    if (Object.keys(counts).length) {
                        wargearSelections[normalizedGroupId] = { mode: "allocation", counts };
                    }
                    return;
                }
                wargearSelections[normalizedGroupId] = value ? String(value).trim() : null;
            });
        }
        const normalized = {
            instanceId: entry.instanceId ? String(entry.instanceId).trim() : null,
            unitId,
            optionId: entry.optionId ? String(entry.optionId).trim() : null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
            upgradeOptionIds: Array.isArray(entry.upgradeOptionIds)
                ? entry.upgradeOptionIds
                    .map((value) => String(value || "").trim())
                    .filter(Boolean)
                : [],
            quantity: normalizeQuantity(entry.quantity),
            wargearSelections,
        };
        return normalized;
    }

    function migrateSavedRosterDocument(payload) {
        if (!payload || typeof payload !== "object") {
            throw new Error("Saved roster must be a JSON object.");
        }
        const factionSlug = String(payload.factionSlug || "").trim();
        if (!factionSlug) {
            throw new Error("Saved roster is missing factionSlug.");
        }
        const entries = Array.isArray(payload.entries) ? payload.entries.map(normalizeSavedEntry) : [];
        return {
            schemaVersion: ROSTER_SCHEMA_VERSION,
            id: payload.id ? String(payload.id).trim() : createRosterId(),
            savedAt: payload.savedAt ? String(payload.savedAt) : nowIso(),
            appVersion: payload.appVersion ? String(payload.appVersion) : "builder-catalog-unknown",
            factionSlug,
            name: normalizeName(payload.name, factionSlug),
            army: normalizeArmyState(payload.army),
            entries,
        };
    }

    function createEmptyRoster(options) {
        const factionSlug = String(options && options.factionSlug ? options.factionSlug : "").trim();
        return migrateSavedRosterDocument({
            id: options && options.id ? options.id : createRosterId(),
            schemaVersion: ROSTER_SCHEMA_VERSION,
            savedAt: nowIso(),
            appVersion: options && options.appVersion ? options.appVersion : "builder-catalog-unknown",
            factionSlug,
            name: options && options.name ? options.name : normalizeName("", factionSlug),
            army: normalizeArmyState(options && options.army),
            entries: [],
        });
    }

    function createRuntimeEntry(entry) {
        return {
            instanceId: entry.instanceId ? String(entry.instanceId) : createRosterId(),
            unitId: entry.unitId,
            optionId: entry.optionId || null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
            upgradeOptionIds: Array.isArray(entry.upgradeOptionIds) ? [...entry.upgradeOptionIds] : [],
            quantity: normalizeQuantity(entry.quantity),
            wargearSelections: { ...(entry.wargearSelections || {}) },
        };
    }

    function createRuntimeEntries(entries) {
        return (Array.isArray(entries) ? entries : []).map(createRuntimeEntry);
    }

    function serializeRuntimeEntry(entry) {
        return normalizeSavedEntry({
            instanceId: entry.instanceId || createRosterId(),
            unitId: entry.unitId,
            optionId: entry.optionId || null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
            upgradeOptionIds: Array.isArray(entry.upgradeOptionIds) ? entry.upgradeOptionIds : [],
            quantity: entry.quantity,
            wargearSelections: entry.wargearSelections || {},
        });
    }

    function serializeRuntimeRoster(options) {
        return migrateSavedRosterDocument({
            id: options.id,
            savedAt: options.savedAt || nowIso(),
            appVersion: options.appVersion,
            factionSlug: options.factionSlug,
            name: options.name,
            army: normalizeArmyState(options.army),
            entries: (options.entries || []).map(serializeRuntimeEntry),
        });
    }

    function unitHasKeyword(unit, keyword) {
        if (!unit || !Array.isArray(unit.keywords)) {
            return false;
        }
        const target = String(keyword || "").trim().toUpperCase();
        return unit.keywords.some((value) => String(value || "").trim().toUpperCase() === target);
    }

    function duplicateCapForUnit(unit) {
        if (unitHasKeyword(unit, "EPIC HERO")) {
            return 1;
        }
        if (unitHasKeyword(unit, "BATTLELINE") || unitHasKeyword(unit, "DEDICATED TRANSPORT")) {
            return 6;
        }
        return 3;
    }

    function listSavedRosters(storage) {
        const adapter = createStorageAdapter(storage);
        const raw = readJson(adapter, INDEX_KEY, []);
        if (!Array.isArray(raw)) {
            return [];
        }
        return raw.filter((item) => item && typeof item === "object" && item.id);
    }

    function getActiveRosterId(storage) {
        const adapter = createStorageAdapter(storage);
        if (!adapter) {
            return null;
        }
        try {
            return adapter.getItem(ACTIVE_KEY);
        } catch (error) {
            return null;
        }
    }

    function setActiveRosterId(storage, rosterId) {
        const adapter = createStorageAdapter(storage);
        if (!adapter) {
            return false;
        }
        if (!rosterId) {
            adapter.removeItem(ACTIVE_KEY);
            return true;
        }
        adapter.setItem(ACTIVE_KEY, rosterId);
        return true;
    }

    function loadRosterFromStorage(storage, rosterId) {
        const adapter = createStorageAdapter(storage);
        if (!adapter || !rosterId) {
            return null;
        }
        const payload = readJson(adapter, rosterKey(rosterId), null);
        if (!payload) {
            return null;
        }
        return migrateSavedRosterDocument(payload);
    }

    function saveRosterToStorage(storage, roster) {
        const adapter = createStorageAdapter(storage);
        if (!adapter) {
            return { ok: false, reason: "storage-unavailable" };
        }

        const savedRoster = migrateSavedRosterDocument({
            ...roster,
            savedAt: nowIso(),
        });
        writeJson(adapter, rosterKey(savedRoster.id), savedRoster);

        const index = listSavedRosters(adapter).filter((item) => item.id !== savedRoster.id);
        index.unshift({
            id: savedRoster.id,
            name: savedRoster.name,
            factionSlug: savedRoster.factionSlug,
            savedAt: savedRoster.savedAt,
        });
        writeJson(adapter, INDEX_KEY, index);
        setActiveRosterId(adapter, savedRoster.id);
        return { ok: true, roster: savedRoster, index };
    }

    function deleteRosterFromStorage(storage, rosterId) {
        const adapter = createStorageAdapter(storage);
        if (!adapter || !rosterId) {
            return { ok: false, reason: "storage-unavailable" };
        }
        adapter.removeItem(rosterKey(rosterId));
        const index = listSavedRosters(adapter).filter((item) => item.id !== rosterId);
        writeJson(adapter, INDEX_KEY, index);
        if (getActiveRosterId(adapter) === rosterId) {
            setActiveRosterId(adapter, index.length ? index[0].id : null);
        }
        return { ok: true, index };
    }

    function exportRosterJson(roster) {
        return `${JSON.stringify(migrateSavedRosterDocument(roster), null, 2)}\n`;
    }

    function importRosterJson(text) {
        let payload;
        try {
            payload = JSON.parse(String(text || ""));
        } catch (error) {
            throw new Error("Imported roster is not valid JSON.");
        }
        return migrateSavedRosterDocument({
            ...payload,
            id: createRosterId(),
            savedAt: nowIso(),
        });
    }

    function resolveCatalogUnit(catalog, unitId) {
        return (catalog && Array.isArray(catalog.units) ? catalog.units : []).find((unit) => unit.unitId === unitId) || null;
    }

    function splitPointsOptions(unit) {
        const all = unit && Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [];
        const upgrades = all.filter((option) => option.selectionKind === "upgrade");
        const base = all.filter((option) => option.selectionKind !== "upgrade");
        return { all, base, upgrades };
    }

    function defaultPointsOption(unit) {
        const { all, base } = splitPointsOptions(unit);
        return base[0] || all[0] || null;
    }

    function resolvePointsSelection(unit, entry) {
        const { all, base, upgrades } = splitPointsOptions(unit);
        const issues = [];
        if (!all.length) {
            return {
                selectedOption: null,
                selectedUpgrades: [],
                issues,
                options: all,
                upgradeOptions: upgrades,
            };
        }

        let selectedOption = null;
        let explicitBaseRequested = false;
        let legacySelection = null;
        const selectedUpgradeIds = new Set(
            Array.isArray(entry.upgradeOptionIds)
                ? entry.upgradeOptionIds.map((value) => String(value || "").trim()).filter(Boolean)
                : []
        );

        if (entry.optionId) {
            legacySelection = all.find((option) => option.id === entry.optionId) || null;
            if (legacySelection && legacySelection.selectionKind !== "upgrade") {
                selectedOption = legacySelection;
                explicitBaseRequested = true;
            } else if (legacySelection && legacySelection.selectionKind === "upgrade") {
                selectedUpgradeIds.add(legacySelection.id);
            }
        }

        if (!selectedOption && Number.isInteger(entry.optionIndex) && all[entry.optionIndex]) {
            legacySelection = all[entry.optionIndex];
            if (legacySelection.selectionKind !== "upgrade") {
                selectedOption = legacySelection;
                explicitBaseRequested = true;
            } else {
                selectedUpgradeIds.add(legacySelection.id);
            }
        }

        if (!selectedOption) {
            selectedOption = defaultPointsOption(unit);
        }

        if (explicitBaseRequested && !selectedOption) {
            issues.push(`Saved configuration is no longer available for ${unit.name}.`);
        }

        if (selectedOption && selectedOption.selectionKind === "upgrade") {
            selectedUpgradeIds.delete(selectedOption.id);
        }

        const selectedUpgrades = [];
        Array.from(selectedUpgradeIds).forEach((upgradeId) => {
            const upgrade = upgrades.find((option) => option.id === upgradeId) || null;
            if (!upgrade) {
                issues.push(`Saved upgrade is no longer available for ${unit.name}: ${upgradeId}.`);
                return;
            }
            selectedUpgrades.push(upgrade);
        });

        return {
            selectedOption,
            selectedUpgrades,
            issues,
            options: base.length ? base : all,
            upgradeOptions: upgrades,
        };
    }

    function resolveSelectionLimit(limitSpec, modelCount) {
        if (typeof limitSpec === "undefined") {
            return modelCount;
        }
        if (limitSpec === null) {
            return null;
        }
        if (limitSpec === "modelCount" || (typeof limitSpec === "object" && limitSpec.kind === "modelCount")) {
            return modelCount;
        }
        if (typeof limitSpec === "object") {
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

    function choicePickCost(choice) {
        return Math.max(1, Number.parseInt(choice && choice.pickCost, 10) || 1);
    }

    function resolveWargearSelections(unit, entry, selectedOption) {
        const groups = unit && unit.wargear && Array.isArray(unit.wargear.options) ? unit.wargear.options : [];
        const selections = [];
        const issues = [];
        const modelCount = selectedOption && typeof selectedOption.modelCount === "number"
            ? selectedOption.modelCount
            : null;
        const poolUsageByKey = new Map();

        groups.forEach((group) => {
            const savedValue = entry.wargearSelections ? entry.wargearSelections[group.id] : null;
            if (group.selectionMode === "allocation") {
                const rawCounts = typeof savedValue === "string"
                    ? { [savedValue]: 1 }
                    : (savedValue && typeof savedValue === "object"
                        ? (savedValue.mode === "allocation" && savedValue.counts && typeof savedValue.counts === "object"
                            ? savedValue.counts
                            : savedValue)
                        : {});
                const selectedChoices = [];
                Object.entries(rawCounts).forEach(([choiceId, count]) => {
                    const normalizedCount = Math.max(0, Number.parseInt(count, 10) || 0);
                    if (!normalizedCount) {
                        return;
                    }
                    const choice = (group.choices || []).find((entry) => entry.id === choiceId) || null;
                    if (!choice) {
                        issues.push(`Saved wargear selection is no longer available for ${group.label}: ${choiceId}.`);
                        return;
                    }
                    selectedChoices.push({
                        choice,
                        count: normalizedCount,
                    });
                });
                const selection = {
                    group,
                    selectedChoice: null,
                    selectedChoices,
                    totalSelected: selectedChoices.reduce((sum, item) => sum + item.count, 0),
                    allocationMax: resolveSelectionLimit(group.allocationLimit, modelCount),
                    issues: [],
                };
                selections.push(selection);
                if (selection.allocationMax !== null && selection.totalSelected > selection.allocationMax) {
                    selection.issues.push(`Saved wargear allocation exceeds limit for ${group.label}.`);
                    issues.push(`Saved wargear allocation exceeds limit for ${group.label}.`);
                }
                return;
            }

            if (group.selectionMode === "multi") {
                const rawChoiceIds = Array.isArray(savedValue)
                    ? savedValue
                    : (savedValue && typeof savedValue === "object" && Array.isArray(savedValue.choiceIds)
                        ? savedValue.choiceIds
                        : []);
                const selectedChoices = [];
                const selectedChoiceIds = [];
                rawChoiceIds.forEach((choiceId) => {
                    const normalizedChoiceId = String(choiceId || "").trim();
                    if (!normalizedChoiceId) {
                        return;
                    }
                    const choice = (group.choices || []).find((option) => option.id === normalizedChoiceId) || null;
                    if (!choice) {
                        issues.push(`Saved wargear selection is no longer available for ${group.label}: ${normalizedChoiceId}.`);
                        return;
                    }
                    selectedChoiceIds.push(normalizedChoiceId);
                    selectedChoices.push({
                        choice,
                        count: 1,
                    });
                });
                const totalSelected = selectedChoices.reduce((sum, item) => sum + choicePickCost(item.choice), 0);
                const selection = {
                    group,
                    selectedChoice: null,
                    selectedChoices,
                    selectedChoiceIds,
                    totalSelected,
                    pickCount: typeof group.pickCount === "number" ? group.pickCount : null,
                    issues: [],
                };
                selections.push(selection);
                if (selection.pickCount !== null && selection.totalSelected > selection.pickCount) {
                    selection.issues.push(`Saved wargear selection exceeds the ${selection.pickCount}-pick limit for ${group.label}.`);
                    issues.push(`Saved wargear selection exceeds the ${selection.pickCount}-pick limit for ${group.label}.`);
                }
                if (group.requireDistinct) {
                    const distinctCount = new Set(selectedChoiceIds).size;
                    if (distinctCount !== selectedChoiceIds.length) {
                        selection.issues.push(`Saved wargear selection must use different choices for ${group.label}.`);
                        issues.push(`Saved wargear selection must use different choices for ${group.label}.`);
                    }
                }
                return;
            }

            const savedChoiceId = typeof savedValue === "string" ? savedValue : null;
            if (!savedChoiceId) {
                selections.push({
                    group,
                    selectedChoice: null,
                    issues: [],
                });
                return;
            }

            const selectedChoice = (group.choices || []).find((choice) => choice.id === savedChoiceId) || null;
            if (!selectedChoice) {
                issues.push(`Saved wargear selection is no longer available for ${group.label}.`);
            }
            selections.push({
                group,
                selectedChoice,
                issues: [],
            });
        });

        selections.forEach((selection) => {
            const group = selection.group;
            if (!group || !group.poolKey) {
                return;
            }
            const selectedUnits = selection.selectedChoice
                ? Number(group.consumesPool) || 1
                : (Array.isArray(selection.selectedChoices)
                    ? selection.selectedChoices.reduce((sum, item) => {
                        if (!item || !item.choice) {
                            return sum;
                        }
                        const choiceCount = Math.max(1, Number(item.count) || 1);
                        return sum + (choiceCount * (Number(group.consumesPool) || 1));
                    }, 0)
                    : 0);
            const poolLimit = resolveSelectionLimit(group.poolLimit, modelCount);
            if (!poolUsageByKey.has(group.poolKey)) {
                poolUsageByKey.set(group.poolKey, {
                    key: group.poolKey,
                    label: group.eligibilityText || group.target || group.label,
                    used: 0,
                    max: poolLimit,
                });
            }
            const pool = poolUsageByKey.get(group.poolKey);
            pool.used += selectedUnits;
            if (pool.max === null && poolLimit !== null) {
                pool.max = poolLimit;
            }
            selection.poolUsage = pool;
        });

        selections.forEach((selection) => {
            const pool = selection.poolUsage;
            if (pool && typeof pool.max === "number" && pool.used > pool.max) {
                const message = `${pool.label} selections use ${pool.used}/${pool.max} eligible models in ${groupLabel(selection.group)}.`;
                selection.issues = Array.isArray(selection.issues) ? selection.issues : [];
                selection.issues.push(message);
                issues.push(message);
            }
        });

        return { selections, issues };
    }

    function groupLabel(group) {
        return group && group.label ? group.label : "this wargear group";
    }

    function humanizeUnitId(unitId) {
        return String(unitId || "")
            .split("-")
            .filter(Boolean)
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join(" ");
    }

    function deriveResolvedRoster(options) {
        const roster = migrateSavedRosterDocument(options.roster);
        const catalog = options.catalog || null;
        const availableFactionSlugs = Array.isArray(options.availableFactionSlugs) ? options.availableFactionSlugs : [];
        const entries = [];
        const army = normalizeArmyState(roster.army);
        let totalPoints = 0;

        roster.entries.forEach((entry, index) => {
            const issues = [];
            const catalogFaction = catalog && catalog.faction ? catalog.faction.slug : null;
            if (availableFactionSlugs.length && !availableFactionSlugs.includes(roster.factionSlug)) {
                issues.push(`Saved faction is not available in current builder data: ${roster.factionSlug}.`);
            }
            if (catalogFaction && catalogFaction !== roster.factionSlug) {
                issues.push(`Faction mismatch: saved roster uses ${roster.factionSlug}, current catalog is ${catalogFaction}.`);
            }

            const unit = catalogFaction === roster.factionSlug ? resolveCatalogUnit(catalog, entry.unitId) : null;
            if (!unit) {
                issues.push(`Unit not found in current catalog: ${entry.unitId}.`);
            }

            const pointsResolution = unit
                ? resolvePointsSelection(unit, entry)
                : { selectedOption: null, selectedUpgrades: [], issues: [], options: [], upgradeOptions: [] };
            const selectedOption = pointsResolution.selectedOption;
            issues.push(...pointsResolution.issues);
            const wargearResolution = unit ? resolveWargearSelections(unit, entry, selectedOption) : { selections: [], issues: [] };
            issues.push(...wargearResolution.issues);

            const unitPoints = !issues.length && selectedOption && typeof selectedOption.points === "number"
                ? selectedOption.points + pointsResolution.selectedUpgrades.reduce((sum, option) => {
                    return typeof option.points === "number" ? sum + option.points : sum;
                }, 0)
                : 0;
            const linePoints = !issues.length
                ? unitPoints * entry.quantity
                : 0;
            totalPoints += linePoints;

            entries.push({
                instanceId: entry.instanceId || `resolved-${index}`,
                unitId: entry.unitId,
                displayName: unit ? unit.name : humanizeUnitId(entry.unitId),
                quantity: entry.quantity,
                unit,
                selectedOption,
                selectedUpgrades: pointsResolution.selectedUpgrades,
                options: pointsResolution.options,
                upgradeOptions: pointsResolution.upgradeOptions,
                wargearSelections: wargearResolution.selections,
                issues,
                isValid: issues.length === 0,
                unitPoints,
                linePoints,
                entry,
            });
        });

        const pointsLimit = battleSizePoints(army.battleSize);
        const armyIssues = [];
        const armyWarnings = [];
        const resolvedEntries = entries.filter((entry) => entry.unit);
        const characterEntries = resolvedEntries.filter((entry) => unitHasKeyword(entry.unit, "CHARACTER"));
        const dedicatedTransportEntries = resolvedEntries.filter((entry) => unitHasKeyword(entry.unit, "DEDICATED TRANSPORT"));
        const duplicateCounts = new Map();
        const duplicateCaps = new Map();

        resolvedEntries.forEach((entry) => {
            const datasheetName = entry.unit && entry.unit.name ? entry.unit.name : entry.displayName;
            duplicateCounts.set(datasheetName, (duplicateCounts.get(datasheetName) || 0) + entry.quantity);
            if (!duplicateCaps.has(datasheetName)) {
                duplicateCaps.set(datasheetName, duplicateCapForUnit(entry.unit));
            }
        });

        entries.forEach((entry) => {
            if (!entry.unit) {
                return;
            }
            const datasheetName = entry.unit.name || entry.displayName;
            const duplicateCount = duplicateCounts.get(datasheetName) || 0;
            const duplicateCap = duplicateCaps.get(datasheetName) || 3;
            if (duplicateCount > duplicateCap) {
                entry.issues.push(
                    `${datasheetName} appears ${duplicateCount} times, exceeding its limit of ${duplicateCap}.`
                );
            }
        });

        if (totalPoints > pointsLimit) {
            armyIssues.push({
                code: "points-limit-exceeded",
                level: "error",
                message: `Roster totals ${totalPoints} points, exceeding the ${pointsLimit}-point ${army.battleSize} limit.`,
            });
        }

        if (!characterEntries.length) {
            armyIssues.push({
                code: "missing-character",
                level: "error",
                message: "Roster must include at least one Character unit.",
            });
        }

        if (!army.warlordInstanceId) {
            armyIssues.push({
                code: "missing-warlord",
                level: "error",
                message: "Roster must select exactly one Warlord.",
            });
        } else {
            const warlordEntry = entries.find((entry) => entry.instanceId === army.warlordInstanceId) || null;
            if (!warlordEntry || !warlordEntry.unit) {
                armyIssues.push({
                    code: "invalid-warlord",
                    level: "error",
                    message: "Selected Warlord is not available in the current roster.",
                });
            } else if (!unitHasKeyword(warlordEntry.unit, "CHARACTER")) {
                armyIssues.push({
                    code: "invalid-warlord",
                    level: "error",
                    message: "Selected Warlord must be a Character unit.",
                });
            }
        }

        if (entries.length) {
            armyWarnings.push({
                code: "strategic-reserves-not-modeled",
                level: "warning",
                message: "Strategic Reserves are not modeled yet, so the 25% reserves cap is not checked.",
            });
        }

        if (characterEntries.length) {
            armyWarnings.push({
                code: "enhancements-not-modeled",
                level: "warning",
                message: "Enhancement selection is not modeled yet, so enhancement limits and uniqueness are not checked.",
            });
        }

        if (dedicatedTransportEntries.length) {
            armyWarnings.push({
                code: "dedicated-transport-not-modeled",
                level: "warning",
                message: "Dedicated Transport embark requirements are not modeled yet, so empty transports are not validated.",
            });
        }

        entries.forEach((entry) => {
            entry.isValid = entry.issues.length === 0;
        });

        return {
            roster,
            army,
            entries,
            totalPoints,
            pointsLimit,
            armyIssues,
            armyWarnings,
            validEntries: entries.filter((entry) => entry.isValid),
            invalidEntries: entries.filter((entry) => !entry.isValid),
        };
    }

    return {
        ACTIVE_KEY,
        BATTLE_SIZE_POINTS,
        DEFAULT_BATTLE_SIZE,
        INDEX_KEY,
        ROSTER_SCHEMA_VERSION,
        STORAGE_NAMESPACE,
        battleSizePoints,
        createEmptyRoster,
        createRosterId,
        createRuntimeEntries,
        createStorageAdapter,
        deleteRosterFromStorage,
        deriveResolvedRoster,
        exportRosterJson,
        getActiveRosterId,
        importRosterJson,
        listSavedRosters,
        loadRosterFromStorage,
        migrateSavedRosterDocument,
        normalizeName,
        normalizeArmyState,
        saveRosterToStorage,
        serializeRuntimeEntry,
        serializeRuntimeRoster,
        setActiveRosterId,
        splitPointsOptions,
        defaultPointsOption,
    };
});
