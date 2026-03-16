(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
        return;
    }
    root.WahBuilderRosterStore = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const ROSTER_SCHEMA_VERSION = 2;
    const STORAGE_NAMESPACE = "wahpediaCapture.builder.v1";
    const INDEX_KEY = `${STORAGE_NAMESPACE}.savedRosters`;
    const ACTIVE_KEY = `${STORAGE_NAMESPACE}.activeRosterId`;

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
                wargearSelections[normalizedGroupId] = value ? String(value).trim() : null;
            });
        }
        const normalized = {
            unitId,
            optionId: entry.optionId ? String(entry.optionId).trim() : null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
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
            entries: [],
        });
    }

    function createRuntimeEntry(entry) {
        return {
            instanceId: createRosterId(),
            unitId: entry.unitId,
            optionId: entry.optionId || null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
            quantity: normalizeQuantity(entry.quantity),
            wargearSelections: { ...(entry.wargearSelections || {}) },
        };
    }

    function createRuntimeEntries(entries) {
        return (Array.isArray(entries) ? entries : []).map(createRuntimeEntry);
    }

    function serializeRuntimeEntry(entry) {
        return normalizeSavedEntry({
            unitId: entry.unitId,
            optionId: entry.optionId || null,
            optionIndex: Number.isInteger(entry.optionIndex) ? entry.optionIndex : null,
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
            entries: (options.entries || []).map(serializeRuntimeEntry),
        });
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

    function resolvePointsOption(unit, entry) {
        const options = unit && Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [];
        if (!options.length) {
            return null;
        }
        if (entry.optionId) {
            const byId = options.find((option) => option.id === entry.optionId);
            if (byId) {
                return byId;
            }
        }
        if (Number.isInteger(entry.optionIndex) && options[entry.optionIndex]) {
            return options[entry.optionIndex];
        }
        return null;
    }

    function resolveWargearSelections(unit, entry) {
        const groups = unit && unit.wargear && Array.isArray(unit.wargear.options) ? unit.wargear.options : [];
        const selections = [];
        const issues = [];

        groups.forEach((group) => {
            const savedChoiceId = entry.wargearSelections ? entry.wargearSelections[group.id] : null;
            if (!savedChoiceId) {
                selections.push({
                    group,
                    selectedChoice: null,
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
            });
        });

        return { selections, issues };
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

            const selectedOption = unit ? resolvePointsOption(unit, entry) : null;
            if (unit && !selectedOption) {
                issues.push(`Saved configuration is no longer available for ${unit.name}.`);
            }
            const wargearResolution = unit ? resolveWargearSelections(unit, entry) : { selections: [], issues: [] };
            issues.push(...wargearResolution.issues);

            const linePoints = !issues.length && selectedOption && typeof selectedOption.points === "number"
                ? selectedOption.points * entry.quantity
                : 0;
            totalPoints += linePoints;

            entries.push({
                instanceId: entry.instanceId || `resolved-${index}`,
                unitId: entry.unitId,
                displayName: unit ? unit.name : humanizeUnitId(entry.unitId),
                quantity: entry.quantity,
                unit,
                selectedOption,
                options: unit && Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [],
                wargearSelections: wargearResolution.selections,
                issues,
                isValid: issues.length === 0,
                linePoints,
                entry,
            });
        });

        return {
            roster,
            entries,
            totalPoints,
            validEntries: entries.filter((entry) => entry.isValid),
            invalidEntries: entries.filter((entry) => !entry.isValid),
        };
    }

    return {
        ACTIVE_KEY,
        INDEX_KEY,
        ROSTER_SCHEMA_VERSION,
        STORAGE_NAMESPACE,
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
        saveRosterToStorage,
        serializeRuntimeEntry,
        serializeRuntimeRoster,
        setActiveRosterId,
    };
});
