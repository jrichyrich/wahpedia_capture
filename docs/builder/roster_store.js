(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
        return;
    }
    root.WahBuilderRosterStore = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const ROSTER_SCHEMA_VERSION = 7;
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
        const detachmentId = payload.detachmentId || payload.detachment_id;
        const normalizedDetachmentId = detachmentId ? String(detachmentId).trim() : null;
        return {
            battleSize,
            warlordInstanceId: normalizedWarlordId || null,
            detachmentId: normalizedDetachmentId || null,
        };
    }

    function normalizeBuilderMetadata(payload) {
        const source = payload && typeof payload === "object" ? payload : {};
        const builderSchemaVersion = Number.isInteger(source.builderSchemaVersion)
            ? source.builderSchemaVersion
            : (Number.isInteger(source.builder_schema_version) ? source.builder_schema_version : null);
        const builderGeneratedAt = source.builderGeneratedAt || source.builder_generated_at;
        return {
            builderSchemaVersion,
            builderGeneratedAt: builderGeneratedAt ? String(builderGeneratedAt) : null,
        };
    }

    function normalizeInstanceReference(value) {
        const normalized = value ? String(value).trim() : "";
        return normalized || null;
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
            enhancementId: entry.enhancementId ? String(entry.enhancementId).trim() : null,
            attachedToInstanceId: normalizeInstanceReference(entry.attachedToInstanceId || entry.attached_to_instance_id),
            embarkedInInstanceId: normalizeInstanceReference(entry.embarkedInInstanceId || entry.embarked_in_instance_id),
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
        const builderMetadata = normalizeBuilderMetadata(payload);
        return {
            schemaVersion: ROSTER_SCHEMA_VERSION,
            id: payload.id ? String(payload.id).trim() : createRosterId(),
            savedAt: payload.savedAt ? String(payload.savedAt) : nowIso(),
            appVersion: payload.appVersion ? String(payload.appVersion) : "builder-catalog-unknown",
            factionSlug,
            name: normalizeName(payload.name, factionSlug),
            builderSchemaVersion: builderMetadata.builderSchemaVersion,
            builderGeneratedAt: builderMetadata.builderGeneratedAt,
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
            builderSchemaVersion: options && Number.isInteger(options.builderSchemaVersion) ? options.builderSchemaVersion : null,
            builderGeneratedAt: options && options.builderGeneratedAt ? String(options.builderGeneratedAt) : null,
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
            enhancementId: entry.enhancementId ? String(entry.enhancementId) : null,
            attachedToInstanceId: normalizeInstanceReference(entry.attachedToInstanceId),
            embarkedInInstanceId: normalizeInstanceReference(entry.embarkedInInstanceId),
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
            enhancementId: entry.enhancementId || null,
            attachedToInstanceId: entry.attachedToInstanceId || null,
            embarkedInInstanceId: entry.embarkedInInstanceId || null,
        });
    }

    function serializeRuntimeRoster(options) {
        return migrateSavedRosterDocument({
            id: options.id,
            savedAt: options.savedAt || nowIso(),
            appVersion: options.appVersion,
            factionSlug: options.factionSlug,
            name: options.name,
            builderSchemaVersion: Number.isInteger(options.builderSchemaVersion) ? options.builderSchemaVersion : null,
            builderGeneratedAt: options.builderGeneratedAt ? String(options.builderGeneratedAt) : null,
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

    function normalizeRuleReference(value) {
        return String(value || "")
            .toUpperCase()
            .replace(/[’']/g, "")
            .replace(/\([^)]*\)/g, " ")
            .replace(/\*/g, " ")
            .replace(/[^A-Z0-9]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function referenceVariants(value) {
        const raw = String(value || "").trim();
        const variants = new Set();
        const normalized = normalizeRuleReference(raw);
        if (normalized) {
            variants.add(normalized);
        }
        const withoutParens = normalizeRuleReference(raw.replace(/\([^)]*\)/g, " "));
        if (withoutParens) {
            variants.add(withoutParens);
        }
        const parentheticalMatches = raw.match(/\(([^)]+)\)/g) || [];
        parentheticalMatches.forEach((match) => {
            const normalizedInner = normalizeRuleReference(match.replace(/[()]/g, ""));
            if (normalizedInner) {
                variants.add(normalizedInner);
            }
        });
        return Array.from(variants);
    }

    function unitRuleText(unit) {
        const values = [];
        if (!unit) {
            return values;
        }
        (Array.isArray(unit.renderBlocks) ? unit.renderBlocks : []).forEach((block) => {
            (Array.isArray(block.entries) ? block.entries : []).forEach((entry) => {
                if (!entry || typeof entry !== "object") {
                    return;
                }
                if (typeof entry.text === "string" && entry.text.trim()) {
                    values.push(entry.text.trim());
                }
                if (typeof entry.label === "string" && entry.label.trim()) {
                    values.push(entry.label.trim());
                }
                if (Array.isArray(entry.items)) {
                    entry.items.forEach((item) => {
                        if (item && String(item).trim()) {
                            values.push(String(item).trim());
                        }
                    });
                }
            });
        });
        const composition = unit.composition && Array.isArray(unit.composition.statements)
            ? unit.composition.statements
            : [];
        composition.forEach((statement) => {
            if (statement && statement.text && String(statement.text).trim()) {
                values.push(String(statement.text).trim());
            }
        });
        const datasheetRules = unit.abilities && Array.isArray(unit.abilities.datasheet)
            ? unit.abilities.datasheet
            : [];
        datasheetRules.forEach((rule) => {
            if (rule && rule.text && String(rule.text).trim()) {
                values.push(String(rule.text).trim());
            }
            if (rule && rule.name && String(rule.name).trim()) {
                values.push(String(rule.name).trim());
            }
        });
        const otherRules = unit.abilities && Array.isArray(unit.abilities.other)
            ? unit.abilities.other
            : [];
        otherRules.forEach((entry) => {
            if (entry && entry.text && String(entry.text).trim()) {
                values.push(String(entry.text).trim());
            }
            if (entry && Array.isArray(entry.items)) {
                entry.items.forEach((item) => {
                    if (item && String(item).trim()) {
                        values.push(String(item).trim());
                    }
                });
            }
        });
        return values;
    }

    function parseNumberWord(value) {
        const normalized = String(value || "").trim().toLowerCase();
        if (!normalized) {
            return null;
        }
        if (/^\d+$/.test(normalized)) {
            return Number.parseInt(normalized, 10);
        }
        return {
            one: 1,
            two: 2,
            three: 3,
            four: 4,
            five: 5,
            six: 6,
        }[normalized] || null;
    }

    function uniqueNormalizedRefs(values) {
        const seen = new Set();
        const refs = [];
        (Array.isArray(values) ? values : []).forEach((value) => {
            const normalized = normalizeRuleReference(value);
            if (!normalized || seen.has(normalized)) {
                return;
            }
            seen.add(normalized);
            refs.push(normalized);
        });
        return refs;
    }

    function parseReferenceParts(value) {
        return uniqueNormalizedRefs(
            String(value || "")
                .split(/\s*,\s*|\s+or\s+/i)
                .flatMap((part) => referenceVariants(part))
                .filter(Boolean)
        );
    }

    function isCharacterOrLeaderUnit(unit) {
        return unitHasKeyword(unit, "CHARACTER") || Boolean(leaderMetadataForUnit(unit).targetRefs.length);
    }

    function leaderMetadataForUnit(unit) {
        const targetRefs = [];
        const texts = unitRuleText(unit);
        const additionalLeaderRefs = [];
        let allowsAdditionalLeaderWithCharacter = false;
        let requiresAttachment = false;
        let subtypeCap = null;
        (Array.isArray(unit.renderBlocks) ? unit.renderBlocks : [])
            .filter((block) => block && block.title === "LEADER")
            .forEach((block) => {
                (Array.isArray(block.entries) ? block.entries : []).forEach((entry) => {
                    if (Array.isArray(entry.items)) {
                        entry.items.forEach((item) => {
                            referenceVariants(item).forEach((normalized) => {
                                if (normalized && !targetRefs.includes(normalized)) {
                                    targetRefs.push(normalized);
                                }
                            });
                        });
                    }
                    if (typeof entry.text === "string") {
                        const match = entry.text.match(/join one\s+(.+?)\s+unit/i);
                        if (match) {
                            referenceVariants(match[1]).forEach((normalized) => {
                                if (normalized && !targetRefs.includes(normalized)) {
                                    targetRefs.push(normalized);
                                }
                            });
                        }
                    }
                });
            });
        texts.forEach((text) => {
            const match = text.match(/must join one\s+(.+?)\s+unit/i);
            if (match) {
                referenceVariants(match[1]).forEach((normalized) => {
                    if (normalized && !targetRefs.includes(normalized)) {
                        targetRefs.push(normalized);
                    }
                });
            }
            if (/must attach this model|must join one/i.test(text)) {
                requiresAttachment = true;
            }
            [
                /even if one(?: or more)?\s+(.+?)\s+(?:model|models|unit|units)\s+have already been attached/i,
                /even if one(?: or more)?\s+(.+?)\s+(?:model|models|unit|units)\s+has already been attached/i,
                /even if\s+(.+?)\s+has already been attached/i,
                /even if\s+(.+?)\s+has been attached/i,
            ].forEach((pattern) => {
                const additionalMatch = text.match(pattern);
                if (!additionalMatch) {
                    return;
                }
                const refs = parseReferenceParts(additionalMatch[1]);
                if (refs.includes("CHARACTER")) {
                    allowsAdditionalLeaderWithCharacter = true;
                }
                refs.forEach((ref) => {
                    if (ref !== "CHARACTER" && !additionalLeaderRefs.includes(ref)) {
                        additionalLeaderRefs.push(ref);
                    }
                });
            });
            const subtypeCapMatch = text.match(/never include more than one\s+(.+?)\s+model/i);
            if (subtypeCapMatch) {
                subtypeCap = {
                    refs: parseReferenceParts(subtypeCapMatch[1]),
                    max: 1,
                    label: String(subtypeCapMatch[1] || "").replace(/\s+/g, " ").trim(),
                };
            }
        });
        return {
            targetRefs,
            additionalLeaderRefs,
            allowsAdditionalLeaderWithCharacter,
            requiresAttachment,
            subtypeCap,
        };
    }

    function targetMetadataForUnit(unit) {
        const texts = unitRuleText(unit);
        const aliasRefs = [];
        let maxLeaders = 1;
        let requiredLeaderKeywordRefs = [];
        const leaderSubtypeCaps = [];

        texts.forEach((text) => {
            const aliasMatch = text.match(/can be attached to\s+(?:an?|the)\s+(.+?)\s*,\s*it can also be attached to this unit/i);
            if (aliasMatch) {
                referenceVariants(aliasMatch[1]).forEach((normalized) => {
                    if (normalized && !aliasRefs.includes(normalized)) {
                        aliasRefs.push(normalized);
                    }
                });
            }
            const maxLeadersMatch = text.match(/can have up to\s+(\w+)\s+Leader units attached/i);
            if (maxLeadersMatch) {
                const parsed = parseNumberWord(maxLeadersMatch[1]);
                if (parsed) {
                    maxLeaders = parsed;
                }
            }
            if (/no more than one of those units is a COMMAND SQUAD unit/i.test(text)) {
                leaderSubtypeCaps.push({
                    refs: ["COMMAND SQUAD"],
                    max: 1,
                    label: "Command Squad",
                });
            }
            const requiredMatch = text.match(/must attach one\s+(.+?)\s+model to this unit/i);
            if (requiredMatch) {
                requiredLeaderKeywordRefs = parseReferenceParts(requiredMatch[1]);
            }
        });

        return {
            nameRef: normalizeRuleReference(unit && unit.name),
            aliasRefs,
            maxLeaders,
            leaderSubtypeCaps,
            requiredLeaderKeywordRefs,
            requiresLeader: requiredLeaderKeywordRefs.length > 0,
        };
    }

    function allUnitKeywords(unit) {
        return [
            ...(Array.isArray(unit && unit.keywords) ? unit.keywords : []),
            ...(Array.isArray(unit && unit.factionKeywords) ? unit.factionKeywords : []),
            unit && unit.name ? unit.name : "",
        ]
            .map((value) => normalizeRuleReference(value))
            .filter(Boolean);
    }

    function normalizedHintWords(value) {
        return normalizeRuleReference(value)
            .split(" ")
            .filter((word) => word && !["MODEL", "MODELS", "ONLY", "OR", "AND"].includes(word));
    }

    function unitMatchesRuleHint(unit, hint) {
        const normalizedHint = normalizeRuleReference(hint);
        if (!unit || !normalizedHint) {
            return false;
        }
        const haystack = allUnitKeywords(unit);
        if (haystack.some((value) => value === normalizedHint || value.includes(normalizedHint))) {
            return true;
        }
        const words = normalizedHintWords(hint);
        if (!words.length) {
            return false;
        }
        return words.every((word) => haystack.some((value) => value === word || value.includes(word)));
    }

    function entryModelCount(entry) {
        if (entry && entry.selectedOption && typeof entry.selectedOption.modelCount === "number") {
            return entry.selectedOption.modelCount;
        }
        const options = entry && entry.unit && entry.unit.composition && Array.isArray(entry.unit.composition.modelCountOptions)
            ? entry.unit.composition.modelCountOptions
            : [];
        if (!options.length) {
            return 1;
        }
        return options.reduce((sum, option) => {
            const count = typeof option.maxModels === "number"
                ? option.maxModels
                : (typeof option.minModels === "number" ? option.minModels : 0);
            return sum + Math.max(0, count);
        }, 0) || 1;
    }

    function unitMatchesReference(unit, reference) {
        const normalizedReference = normalizeRuleReference(reference);
        if (!unit || !normalizedReference) {
            return false;
        }
        return unitMatchesRuleHint(unit, normalizedReference);
    }

    function formatEligibilityRequirement(value) {
        return String(value || "").replace(/\bmodel only\.?$/i, "").replace(/\s+/g, " ").trim() || "the required keywords";
    }

    function enhancementEligibilityMismatch(enhancement, unit) {
        const keywordHints = Array.isArray(enhancement && enhancement.keywordHints)
            ? enhancement.keywordHints.filter(Boolean)
            : [];
        if (!keywordHints.length) {
            return null;
        }
        if (keywordHints.some((hint) => unitMatchesRuleHint(unit, hint))) {
            return null;
        }
        const requirement = enhancement.eligibilityText
            ? formatEligibilityRequirement(enhancement.eligibilityText)
            : keywordHints.join(" or ");
        return `${enhancement.name} requires ${requirement}.`;
    }

    function transportMetadataForUnit(unit) {
        const block = (Array.isArray(unit && unit.renderBlocks) ? unit.renderBlocks : []).find((entry) => entry && entry.title === "TRANSPORT") || null;
        const text = block && Array.isArray(block.entries)
            ? ((block.entries.find((entry) => entry && typeof entry.text === "string" && /transport capacity of/i.test(entry.text)) || {}).text || null)
            : null;
        if (!text) {
            return null;
        }
        const capacityMatch = text.match(/transport capacity of\s+(\d+)\s+(.+?)(?:\.|$)/i);
        if (!capacityMatch) {
            return {
                rawText: text,
                supported: false,
            };
        }
        const capacity = Number.parseInt(capacityMatch[1], 10);
        const allowedClause = String(capacityMatch[2] || "").trim();
        if (!capacity) {
            return {
                rawText: text,
                supported: false,
                capacity,
            };
        }
        const alternativePoolRegex = /^(.+?)\s+model\s+or\s+(\d+)\s+(.+?)\s+models?$/i;
        const alternativePoolMatch = allowedClause.match(alternativePoolRegex);
        if (alternativePoolMatch) {
            return {
                rawText: text,
                supported: true,
                mode: "alternativePools",
                capacity: null,
                allowedClause,
                pools: [
                    {
                        capacity,
                        refs: parseReferenceParts(alternativePoolMatch[1]),
                        label: String(alternativePoolMatch[1] || "").replace(/\s+/g, " ").trim(),
                    },
                    {
                        capacity: Number.parseInt(alternativePoolMatch[2], 10) || 0,
                        refs: parseReferenceParts(alternativePoolMatch[3]),
                        label: String(alternativePoolMatch[3] || "").replace(/\s+/g, " ").trim(),
                    },
                ],
                disallowedKeywords: [],
                slotModifiers: [],
            };
        }
        const allowlistMatch = allowedClause.match(/^models from the following units:\s+(.+)$/i);
        const disallowedKeywords = [];
        const disallowedMatch = text.match(/It cannot transport\s+(.+?)\s+models?\./i);
        if (disallowedMatch) {
            disallowedMatch[1]
                .split(/\s*,\s*|\s+or\s+/i)
                .map((value) => normalizeRuleReference(value))
                .filter(Boolean)
                .forEach((value) => {
                    if (!disallowedKeywords.includes(value)) {
                        disallowedKeywords.push(value);
                    }
                });
        }
        const slotModifiers = [];
        const modifierRegex = /Each\s+(.+?)\s+model takes up the space of\s+(\d+)\s+models?/gi;
        let modifierMatch;
        while ((modifierMatch = modifierRegex.exec(text))) {
            const refs = String(modifierMatch[1] || "")
                .split(/\s*,\s*|\s+or\s+/i)
                .map((value) => normalizeRuleReference(value))
                .filter(Boolean);
            const seats = Number.parseInt(modifierMatch[2], 10) || 1;
            if (refs.length && seats > 1) {
                slotModifiers.push({ refs, seats });
            }
        }
        return {
            rawText: text,
            supported: true,
            mode: allowlistMatch ? "namedUnitAllowlist" : "standard",
            capacity,
            allowedClause,
            allowedUnitRefs: allowlistMatch ? parseReferenceParts(allowlistMatch[1]) : [],
            disallowedKeywords,
            slotModifiers,
        };
    }

    function transportSupportsUnit(transportMeta, unit) {
        if (!transportMeta || !transportMeta.supported || !unit) {
            return null;
        }
        const unitKeywords = allUnitKeywords(unit);
        if (transportMeta.disallowedKeywords.some((ref) => unitKeywords.some((keyword) => keyword === ref || keyword.includes(ref) || ref.includes(keyword)))) {
            return {
                allowed: false,
                mode: transportMeta.mode || "standard",
                reason: "Passenger type is barred by this transport's datasheet rule.",
            };
        }
        if (transportMeta.mode === "namedUnitAllowlist") {
            const allowed = transportMeta.allowedUnitRefs.some((ref) => unitKeywords.some((keyword) => keyword === ref || keyword.includes(ref) || ref.includes(keyword)));
            return {
                allowed,
                mode: "namedUnitAllowlist",
                reason: allowed ? null : "Passenger is not on this transport's named-unit allowlist.",
            };
        }
        if (transportMeta.mode === "alternativePools") {
            const poolIndex = transportMeta.pools.findIndex((pool) => pool.refs.some((ref) => unitKeywords.some((keyword) => keyword === ref || keyword.includes(ref) || ref.includes(keyword))));
            return {
                allowed: poolIndex !== -1,
                mode: "alternativePools",
                poolIndex,
                pool: poolIndex === -1 ? null : transportMeta.pools[poolIndex],
                reason: poolIndex === -1 ? "Passenger does not match any allowed transport pool." : null,
            };
        }
        const normalizedAllowed = normalizeRuleReference(transportMeta.allowedClause);
        if (!normalizedAllowed) {
            return { allowed: true, mode: "standard" };
        }
        const alternatives = transportMeta.allowedClause
            .split(/\s+or\s+/i)
            .map((value) => normalizeRuleReference(value))
            .filter(Boolean);
        if (!alternatives.length) {
            return { allowed: true, mode: "standard" };
        }
        return {
            allowed: alternatives.some((alternative) => {
                const words = alternative
                    .split(" ")
                    .filter((word) => word && word !== "MODEL" && word !== "MODELS");
                return words.every((word) => unitKeywords.some((keyword) => keyword === word || keyword.includes(word) || word.includes(keyword)));
            }),
            mode: "standard",
            reason: null,
        };
    }

    function transportSeatMultiplier(transportMeta, unit) {
        if (!transportMeta || !transportMeta.supported || !unit) {
            return 1;
        }
        const unitKeywords = allUnitKeywords(unit);
        return transportMeta.slotModifiers.reduce((maxSeats, modifier) => {
            const matches = modifier.refs.some((ref) => unitKeywords.some((keyword) => keyword === ref || keyword.includes(ref) || ref.includes(keyword)));
            return matches ? Math.max(maxSeats, modifier.seats) : maxSeats;
        }, 1);
    }

    function relationshipSummaryEntry(type, label, detail) {
        return {
            type,
            label,
            detail,
        };
    }

    function buildRelationshipMetadata(entries) {
        const metadataById = new Map();
        entries.forEach((entry) => {
            const leaderMeta = leaderMetadataForUnit(entry.unit);
            const targetMeta = targetMetadataForUnit(entry.unit);
            const transportMeta = transportMetadataForUnit(entry.unit);
            metadataById.set(entry.instanceId, {
                leaderMeta,
                targetMeta,
                transportMeta,
                nameRef: normalizeRuleReference(entry.displayName),
            });
        });
        return metadataById;
    }

    function entryMatchesAnyRef(entry, refs) {
        return (Array.isArray(refs) ? refs : []).some((ref) => unitMatchesReference(entry && entry.unit, ref));
    }

    function leaderProvidesAdditionalSlot(leaderEntry, otherLeaderEntries, relationshipMetadata) {
        const leaderMeta = relationshipMetadata.get(leaderEntry.instanceId).leaderMeta;
        if (!leaderMeta) {
            return false;
        }
        if (leaderMeta.allowsAdditionalLeaderWithCharacter && otherLeaderEntries.some((entry) => unitHasKeyword(entry.unit, "CHARACTER"))) {
            return true;
        }
        return leaderMeta.additionalLeaderRefs.length > 0 && otherLeaderEntries.some((entry) => entryMatchesAnyRef(entry, leaderMeta.additionalLeaderRefs));
    }

    function validateLeaderSubtypeCaps(targetEntry, leaderEntries, relationshipMetadata) {
        const targetMeta = relationshipMetadata.get(targetEntry.instanceId).targetMeta;
        const caps = [...(Array.isArray(targetMeta.leaderSubtypeCaps) ? targetMeta.leaderSubtypeCaps : [])];
        leaderEntries.forEach((leaderEntry) => {
            const leaderMeta = relationshipMetadata.get(leaderEntry.instanceId).leaderMeta;
            if (leaderMeta && leaderMeta.subtypeCap && Array.isArray(leaderMeta.subtypeCap.refs) && leaderMeta.subtypeCap.refs.length) {
                caps.push(leaderMeta.subtypeCap);
            }
        });
        return caps
            .map((cap) => {
                const matches = leaderEntries.filter((leaderEntry) => entryMatchesAnyRef(leaderEntry, cap.refs));
                if (matches.length <= cap.max) {
                    return null;
                }
                return `${targetEntry.displayName} cannot have more than ${cap.max} attached ${cap.label} unit${cap.max === 1 ? "" : "s"}.`;
            })
            .filter(Boolean);
    }

    function formatReferenceList(refs) {
        const values = (Array.isArray(refs) ? refs : []).filter(Boolean);
        if (!values.length) {
            return "required slot";
        }
        if (values.length === 1) {
            return values[0];
        }
        return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
    }

    function evaluateLeaderAttachment(leaderEntry, targetEntry, relationshipMetadata, attachedLeaderEntries) {
        const leaderMeta = relationshipMetadata.get(leaderEntry.instanceId).leaderMeta;
        const targetMeta = relationshipMetadata.get(targetEntry.instanceId).targetMeta;
        if (!leaderMeta.targetRefs.length) {
            return {
                allowed: false,
                reason: `${leaderEntry.displayName} has no eligible bodyguard targets in the current roster.`,
            };
        }
        const refs = [targetMeta.nameRef, ...targetMeta.aliasRefs].filter(Boolean);
        const matchesTarget = refs.some((ref) => leaderMeta.targetRefs.some((targetRef) => targetRef === ref || targetRef.includes(ref) || ref.includes(targetRef)));
        if (!matchesTarget) {
            return {
                allowed: false,
                reason: `${leaderEntry.displayName} cannot join ${targetEntry.displayName}.`,
            };
        }
        if (targetMeta.requiredLeaderKeywordRefs.length) {
            const keywords = allUnitKeywords(leaderEntry.unit);
            if (!targetMeta.requiredLeaderKeywordRefs.some((ref) => keywords.some((keyword) => keyword === ref || keyword.includes(ref) || ref.includes(keyword)))) {
                return {
                    allowed: false,
                    reason: `${leaderEntry.displayName} does not satisfy ${targetEntry.displayName}'s required ${formatReferenceList(targetMeta.requiredLeaderKeywordRefs)} Leader slot.`,
                };
            }
        }
        const otherLeaderEntries = Array.isArray(attachedLeaderEntries) ? attachedLeaderEntries.filter((entry) => entry && entry.instanceId !== leaderEntry.instanceId) : [];
        const proposedLeaderEntries = [...otherLeaderEntries, leaderEntry];
        if (proposedLeaderEntries.length > targetMeta.maxLeaders) {
            const extraSlotAllowed = proposedLeaderEntries.length === (targetMeta.maxLeaders + 1)
                && proposedLeaderEntries.some((entry) => {
                    const others = proposedLeaderEntries.filter((otherEntry) => otherEntry.instanceId !== entry.instanceId);
                    return leaderProvidesAdditionalSlot(entry, others, relationshipMetadata);
                });
            if (!extraSlotAllowed) {
                return {
                    allowed: false,
                    reason: `${targetEntry.displayName} already has its allowed Leader combination.`,
                };
            }
        }
        const subtypeCapIssue = validateLeaderSubtypeCaps(targetEntry, proposedLeaderEntries, relationshipMetadata)[0] || null;
        if (subtypeCapIssue) {
            return {
                allowed: false,
                reason: subtypeCapIssue
                    .replace(`${targetEntry.displayName} cannot have more than 1 attached `, `${targetEntry.displayName} already has its allowed `)
                    .replace(" unit.", " attachment."),
            };
        }
        return { allowed: true, reason: null };
    }

    function canLeaderAttachToTarget(leaderEntry, targetEntry, relationshipMetadata, attachedLeaderEntries) {
        return evaluateLeaderAttachment(leaderEntry, targetEntry, relationshipMetadata, attachedLeaderEntries).allowed;
    }

    function issuePriority(entry, issue) {
        const text = String(issue || "");
        if (!text) {
            return 99;
        }
        if (
            (entry && entry.activeEnhancement && text.includes(entry.activeEnhancement.name))
            || /enhancement/i.test(text)
            || /Epic Heroes cannot take enhancements/i.test(text)
        ) {
            return 0;
        }
        if (
            /cannot join/i.test(text)
            || /attached .* Leader/i.test(text)
            || /required .*Leader slot/i.test(text)
            || /must be attached to an eligible unit/i.test(text)
            || /allowed Leader combination/i.test(text)
            || /allowed .* attachment/i.test(text)
        ) {
            return 1;
        }
        if (
            /cannot embark/i.test(text)
            || /transport capacity/i.test(text)
            || /transport pool/i.test(text)
            || /transport assignment/i.test(text)
            || /allowlist/i.test(text)
            || /Passenger/i.test(text)
        ) {
            return 2;
        }
        if (
            /wargear/i.test(text)
            || /pick limit/i.test(text)
            || /eligible models/i.test(text)
            || /configuration/i.test(text)
            || /inactive at/i.test(text)
        ) {
            return 3;
        }
        if (
            /appears .* exceeding its limit/i.test(text)
            || /Warlord/i.test(text)
            || /detachment/i.test(text)
            || /Character unit/i.test(text)
        ) {
            return 4;
        }
        if (
            /current catalog/i.test(text)
            || /faction mismatch/i.test(text)
            || /Saved faction/i.test(text)
            || /no longer resolves/i.test(text)
        ) {
            return 5;
        }
        return 50;
    }

    function rankIssuesForEntry(entry) {
        const issues = Array.isArray(entry && entry.issues) ? entry.issues : [];
        return issues
            .map((issue, index) => ({
                message: issue,
                rank: issuePriority(entry, issue),
                index,
            }))
            .sort((left, right) => (left.rank - right.rank) || (left.index - right.index));
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

    function compareSavedAtDescending(left, right) {
        const leftTime = Date.parse(left && left.savedAt ? left.savedAt : "") || 0;
        const rightTime = Date.parse(right && right.savedAt ? right.savedAt : "") || 0;
        return rightTime - leftTime;
    }

    function listSavedRosters(storage) {
        const adapter = createStorageAdapter(storage);
        const raw = readJson(adapter, INDEX_KEY, []);
        if (!Array.isArray(raw)) {
            return [];
        }
        return raw
            .filter((item) => item && typeof item === "object" && item.id)
            .sort(compareSavedAtDescending);
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
            builderSchemaVersion: savedRoster.builderSchemaVersion,
            builderGeneratedAt: savedRoster.builderGeneratedAt,
        });
        index.sort(compareSavedAtDescending);
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

    function dedupeSavedRosters(storage) {
        const adapter = createStorageAdapter(storage);
        if (!adapter) {
            return { ok: false, reason: "storage-unavailable" };
        }
        const index = listSavedRosters(adapter);
        const keep = [];
        const keepIds = new Set();
        const seenKeys = new Set();
        index.forEach((item) => {
            const key = `${String(item.factionSlug || "").trim()}::${String(item.name || "").trim().toLowerCase()}`;
            if (seenKeys.has(key)) {
                adapter.removeItem(rosterKey(item.id));
                return;
            }
            seenKeys.add(key);
            keep.push(item);
            keepIds.add(item.id);
        });
        writeJson(adapter, INDEX_KEY, keep);
        const activeId = getActiveRosterId(adapter);
        if (activeId && !keepIds.has(activeId)) {
            setActiveRosterId(adapter, keep.length ? keep[0].id : null);
        }
        return { ok: true, index: keep, removedCount: index.length - keep.length };
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

    function catalogRules(catalog) {
        const rules = catalog && typeof catalog.rules === "object" ? catalog.rules : {};
        return {
            armyRules: Array.isArray(rules.armyRules) ? rules.armyRules : [],
            detachments: Array.isArray(rules.detachments) ? rules.detachments : [],
        };
    }

    function resolveActiveDetachment(catalog, army) {
        const detachments = catalogRules(catalog).detachments;
        if (!detachments.length) {
            return null;
        }
        const detachmentId = army && army.detachmentId ? String(army.detachmentId).trim() : "";
        if (!detachmentId) {
            return null;
        }
        return detachments.find((detachment) => detachment && detachment.id === detachmentId) || null;
    }

    function findEnhancement(activeDetachment, enhancementId) {
        if (!activeDetachment || !enhancementId) {
            return null;
        }
        const enhancements = Array.isArray(activeDetachment.enhancements) ? activeDetachment.enhancements : [];
        return enhancements.find((enhancement) => enhancement && enhancement.id === enhancementId) || null;
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

    function availabilityMatchesModelCount(availability, modelCount) {
        if (!availability || availability.kind !== "modelCountRange" || modelCount === null) {
            return true;
        }
        const minModels = typeof availability.minModels === "number" ? availability.minModels : null;
        const maxModels = typeof availability.maxModels === "number" ? availability.maxModels : null;
        if (minModels !== null && modelCount < minModels) {
            return false;
        }
        if (maxModels !== null && modelCount > maxModels) {
            return false;
        }
        return true;
    }

    function describeModelCount(modelCount) {
        return typeof modelCount === "number"
            ? `${modelCount} model${modelCount === 1 ? "" : "s"}`
            : "the current unit size";
    }

    function describeAvailability(availability) {
        if (!availability || availability.kind !== "modelCountRange") {
            return "a different unit size";
        }
        const minModels = typeof availability.minModels === "number" ? availability.minModels : null;
        const maxModels = typeof availability.maxModels === "number" ? availability.maxModels : null;
        if (minModels !== null && maxModels !== null && minModels === maxModels) {
            return `${minModels} model${minModels === 1 ? "" : "s"}`;
        }
        if (minModels !== null && maxModels !== null) {
            return `${minModels}-${maxModels} models`;
        }
        if (minModels !== null) {
            return `${minModels}+ models`;
        }
        if (maxModels !== null) {
            return `${maxModels} or fewer models`;
        }
        return "a different unit size";
    }

    function hasSavedWargearSelection(group, savedValue) {
        if (!group) {
            return false;
        }
        if (group.selectionMode === "allocation") {
            if (typeof savedValue === "string") {
                return Boolean(String(savedValue || "").trim());
            }
            const rawCounts = savedValue && typeof savedValue === "object"
                ? (savedValue.mode === "allocation" && savedValue.counts && typeof savedValue.counts === "object"
                    ? savedValue.counts
                    : savedValue)
                : null;
            if (!rawCounts || typeof rawCounts !== "object") {
                return false;
            }
            return Object.values(rawCounts).some((count) => Math.max(0, Number.parseInt(count, 10) || 0) > 0);
        }
        if (group.selectionMode === "multi") {
            const rawChoiceIds = Array.isArray(savedValue)
                ? savedValue
                : (savedValue && typeof savedValue === "object" && Array.isArray(savedValue.choiceIds)
                    ? savedValue.choiceIds
                    : []);
            return rawChoiceIds.some((choiceId) => Boolean(String(choiceId || "").trim()));
        }
        return typeof savedValue === "string" && Boolean(savedValue.trim());
    }

    function resolveWargearSelections(unit, entry, selectedOption) {
        const groups = unit && unit.wargear && Array.isArray(unit.wargear.options) ? unit.wargear.options : [];
        const selections = [];
        const issues = [];
        const inactiveSelections = [];
        const modelCount = selectedOption && typeof selectedOption.modelCount === "number"
            ? selectedOption.modelCount
            : null;
        const poolUsageByKey = new Map();

        groups.forEach((group) => {
            const savedValue = entry.wargearSelections ? entry.wargearSelections[group.id] : null;
            if (!availabilityMatchesModelCount(group.availability, modelCount)) {
                if (hasSavedWargearSelection(group, savedValue)) {
                    const message = `Saved wargear selection for ${groupLabel(group)} is inactive at ${describeModelCount(modelCount)}. It is available only at ${describeAvailability(group.availability)}.`;
                    inactiveSelections.push({
                        group,
                        availability: group.availability || null,
                        issue: message,
                    });
                    issues.push(message);
                }
                return;
            }
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

        return { selections, issues, inactiveSelections };
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

    function normalizeSupportMetadata(unit) {
        const support = unit && unit.support && typeof unit.support === "object" ? unit.support : {};
        const supportReasons = Array.isArray(support.supportReasons)
            ? support.supportReasons.map((value) => String(value || "").trim()).filter(Boolean)
            : [];
        const supportLevel = support.supportLevel ? String(support.supportLevel) : (supportReasons.length ? "partial" : "full");
        return {
            supportLevel,
            supportReasons,
            previewSupport: support.previewSupport ? String(support.previewSupport) : "configured-only",
        };
    }

    function rosterCompatibility(roster, catalog, availableFactionSlugs, entries) {
        const compatibleFaction = !availableFactionSlugs.length || availableFactionSlugs.includes(roster.factionSlug);
        const schemaMatches = Boolean(
            catalog
            && Number.isInteger(roster.builderSchemaVersion)
            && Number.isInteger(catalog.schemaVersion)
            && roster.builderSchemaVersion === catalog.schemaVersion
        );
        const generatedAtMatches = Boolean(
            catalog
            && roster.builderGeneratedAt
            && catalog.generatedAt
            && String(roster.builderGeneratedAt) === String(catalog.generatedAt)
        );
        const missingMetadata = roster.builderSchemaVersion === null || roster.builderGeneratedAt === null;
        const incompatibleEntries = (Array.isArray(entries) ? entries : []).filter((entry) => entry && entry.support.supportLevel === "incompatible");
        return {
            compatibleFaction,
            schemaMatches,
            generatedAtMatches,
            missingMetadata,
            needsReview: missingMetadata || !schemaMatches || !generatedAtMatches || incompatibleEntries.length > 0 || !compatibleFaction,
            incompatibleEntries,
        };
    }

    function rosterReadiness(armyIssues, invalidEntries, entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return { state: "draft", label: "Draft" };
        }
        if ((Array.isArray(armyIssues) && armyIssues.length) || (Array.isArray(invalidEntries) && invalidEntries.length)) {
            return { state: "draft", label: "Draft" };
        }
        const hasPartialSupport = entries.some((entry) => entry && entry.support && entry.support.supportLevel !== "full");
        if (hasPartialSupport) {
            return { state: "partial", label: "Partial" };
        }
        return { state: "playable", label: "Playable" };
    }

    function deriveResolvedRoster(options) {
        const roster = migrateSavedRosterDocument(options.roster);
        const catalog = options.catalog || null;
        const availableFactionSlugs = Array.isArray(options.availableFactionSlugs) ? options.availableFactionSlugs : [];
        const entries = [];
        const army = normalizeArmyState(roster.army);
        const rules = catalogRules(catalog);
        const activeDetachment = resolveActiveDetachment(catalog, army);
        const availableEnhancements = activeDetachment && Array.isArray(activeDetachment.enhancements)
            ? activeDetachment.enhancements
            : [];
        const stratagems = activeDetachment && Array.isArray(activeDetachment.stratagems)
            ? activeDetachment.stratagems
            : [];
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

            const activeEnhancement = findEnhancement(activeDetachment, entry.enhancementId);
            const unitPointsBase = selectedOption && typeof selectedOption.points === "number"
                ? selectedOption.points + pointsResolution.selectedUpgrades.reduce((sum, option) => {
                    return typeof option.points === "number" ? sum + option.points : sum;
                }, 0)
                : 0;
            const unitPointsEnhancement = activeEnhancement && typeof activeEnhancement.points === "number"
                ? activeEnhancement.points
                : 0;
            const linePointsBase = unitPointsBase * entry.quantity;
            const linePointsEnhancement = unitPointsEnhancement * entry.quantity;
            const unitPoints = unitPointsBase + unitPointsEnhancement;
            const linePoints = linePointsBase + linePointsEnhancement;
            totalPoints += linePoints;
            const support = unit
                ? normalizeSupportMetadata(unit)
                : {
                    supportLevel: "incompatible",
                    supportReasons: ["missing_unit"],
                    previewSupport: "configured-only",
                };

            entries.push({
                instanceId: entry.instanceId || `resolved-${index}`,
                unitId: entry.unitId,
                displayName: unit ? unit.name : humanizeUnitId(entry.unitId),
                quantity: entry.quantity,
                unit,
                selectedOption,
                selectedUpgrades: pointsResolution.selectedUpgrades,
                activeEnhancement,
                options: pointsResolution.options,
                upgradeOptions: pointsResolution.upgradeOptions,
                wargearSelections: wargearResolution.selections,
                inactiveWargearSelections: wargearResolution.inactiveSelections,
                issues,
                isValid: issues.length === 0,
                canRepair: !unit || issues.some((issue) => /not found in current catalog|faction mismatch/i.test(issue)),
                support,
                unitPoints,
                linePointsBase,
                linePointsEnhancement,
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
        const transportEntries = resolvedEntries.filter((entry) => unitHasKeyword(entry.unit, "TRANSPORT"));
        const enhancementEntries = [];
        const assignedEnhancementEntries = [];
        const duplicateCounts = new Map();
        const duplicateCaps = new Map();
        const entriesById = new Map(entries.map((entry) => [entry.instanceId, entry]));
        const relationshipMetadata = buildRelationshipMetadata(resolvedEntries);
        const attachedLeaderIdsByTarget = new Map();
        const requestedAttachedLeaderIdsByTarget = new Map();
        const embarkedUnitIdsByTransport = new Map();
        const transportSeatUsageByTransport = new Map();
        const transportPoolUsageByTransport = new Map();
        const unsupportedTransportEntries = [];

        if (rules.detachments.length && !army.detachmentId) {
            armyIssues.push({
                code: "missing-detachment",
                level: "error",
                message: "Roster must select a detachment to unlock faction rules, enhancements, and stratagems.",
            });
        } else if (army.detachmentId && !activeDetachment) {
            armyIssues.push({
                code: "invalid-detachment",
                level: "error",
                message: "Selected detachment is not available in the current catalog.",
            });
        }

        resolvedEntries.forEach((entry) => {
            if (entry.entry.attachedToInstanceId) {
                if (!requestedAttachedLeaderIdsByTarget.has(entry.entry.attachedToInstanceId)) {
                    requestedAttachedLeaderIdsByTarget.set(entry.entry.attachedToInstanceId, []);
                }
                requestedAttachedLeaderIdsByTarget.get(entry.entry.attachedToInstanceId).push(entry.instanceId);
            }
        });

        resolvedEntries.forEach((entry) => {
            const datasheetName = entry.unit && entry.unit.name ? entry.unit.name : entry.displayName;
            duplicateCounts.set(datasheetName, (duplicateCounts.get(datasheetName) || 0) + entry.quantity);
            if (!duplicateCaps.has(datasheetName)) {
                duplicateCaps.set(datasheetName, duplicateCapForUnit(entry.unit));
            }
            entry.relationship = {
                attachedToInstanceId: entry.entry.attachedToInstanceId || null,
                attachedToLabel: null,
                attachOptions: [],
                attachedLeaderIds: [],
                attachedLeaderNames: [],
                embarkedInInstanceId: entry.entry.embarkedInInstanceId || null,
                embarkedInLabel: null,
                inheritedEmbarkedInInstanceId: null,
                inheritedEmbarkedInLabel: null,
                transportOptions: [],
                embarkedUnitIds: [],
                embarkedUnitNames: [],
                transportCapacity: null,
                relationshipNotes: [],
            };

            if (!entry.entry.enhancementId) {
                return;
            }
            assignedEnhancementEntries.push(entry);
            if (!army.detachmentId || !activeDetachment) {
                entry.issues.push("Enhancements require an active detachment.");
                return;
            }
            if (!entry.activeEnhancement) {
                entry.issues.push(`Saved enhancement is not available in ${activeDetachment.name}.`);
                return;
            }
            if (!unitHasKeyword(entry.unit, "CHARACTER")) {
                entry.issues.push("Enhancements can only be assigned to Character units.");
                return;
            }
            if (unitHasKeyword(entry.unit, "EPIC HERO")) {
                entry.issues.push("Epic Heroes cannot take enhancements.");
                return;
            }
            const enhancementEligibilityIssue = enhancementEligibilityMismatch(entry.activeEnhancement, entry.unit);
            if (enhancementEligibilityIssue) {
                entry.issues.push(enhancementEligibilityIssue);
                return;
            }
            enhancementEntries.push(entry);
        });

        const enhancementCounts = new Map();
        enhancementEntries.forEach((entry) => {
            const enhancementId = entry.activeEnhancement && entry.activeEnhancement.id;
            if (!enhancementId) {
                return;
            }
            enhancementCounts.set(enhancementId, (enhancementCounts.get(enhancementId) || 0) + 1);
        });
        enhancementEntries.forEach((entry) => {
            const enhancementId = entry.activeEnhancement && entry.activeEnhancement.id;
            if (enhancementId && (enhancementCounts.get(enhancementId) || 0) > 1) {
                entry.issues.push(`${entry.activeEnhancement.name} can only be selected once per roster.`);
            }
        });
        if (assignedEnhancementEntries.length > 3) {
            armyIssues.push({
                code: "too-many-enhancements",
                level: "error",
                message: `Roster assigns ${assignedEnhancementEntries.length} enhancements; the maximum is 3.`,
            });
        }

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

        resolvedEntries.forEach((entry) => {
            const leaderMeta = relationshipMetadata.get(entry.instanceId).leaderMeta;
            if (!leaderMeta.targetRefs.length) {
                return;
            }
            entry.relationship.attachOptions = resolvedEntries
                .filter((targetEntry) => {
                    if (targetEntry.instanceId === entry.instanceId) {
                        return false;
                    }
                    const attachedLeaderEntries = (requestedAttachedLeaderIdsByTarget.get(targetEntry.instanceId) || [])
                        .filter((instanceId) => instanceId !== entry.instanceId)
                        .map((instanceId) => entriesById.get(instanceId))
                        .filter(Boolean);
                    return canLeaderAttachToTarget(entry, targetEntry, relationshipMetadata, attachedLeaderEntries);
                })
                .map((targetEntry) => ({
                    instanceId: targetEntry.instanceId,
                    label: targetEntry.displayName,
                }));
        });

        resolvedEntries.forEach((entry) => {
            if (!entry.relationship.attachedToInstanceId) {
                return;
            }
            const targetEntry = entriesById.get(entry.relationship.attachedToInstanceId) || null;
            if (!targetEntry || !targetEntry.unit) {
                entry.issues.push("Attached unit is not available in the current roster.");
                return;
            }
            if (targetEntry.instanceId === entry.instanceId) {
                entry.issues.push("A unit cannot be attached to itself.");
                return;
            }
            const attachedLeaderEntries = (attachedLeaderIdsByTarget.get(targetEntry.instanceId) || [])
                .map((instanceId) => entriesById.get(instanceId))
                .filter(Boolean);
            const attachmentStatus = evaluateLeaderAttachment(entry, targetEntry, relationshipMetadata, attachedLeaderEntries);
            if (!attachmentStatus.allowed) {
                entry.issues.push(attachmentStatus.reason || `${entry.displayName} cannot join ${targetEntry.displayName}.`);
                return;
            }
            if (!attachedLeaderIdsByTarget.has(targetEntry.instanceId)) {
                attachedLeaderIdsByTarget.set(targetEntry.instanceId, []);
            }
            attachedLeaderIdsByTarget.get(targetEntry.instanceId).push(entry.instanceId);
            entry.relationship.attachedToLabel = targetEntry.displayName;
            entry.relationship.relationshipNotes.push(
                relationshipSummaryEntry("attachment", `Attached to ${targetEntry.displayName}`, "Leader assignment")
            );
            if (entry.relationship.embarkedInInstanceId) {
                entry.issues.push("Attached Leaders inherit transport assignment from their unit and cannot embark separately.");
            }
        });

        resolvedEntries.forEach((entry) => {
            const leaderMeta = relationshipMetadata.get(entry.instanceId).leaderMeta;
            if (leaderMeta.requiresAttachment && !entry.relationship.attachedToInstanceId) {
                entry.issues.push(`${entry.displayName} must be attached to an eligible unit.`);
            }
        });

        resolvedEntries.forEach((entry) => {
            const targetMeta = relationshipMetadata.get(entry.instanceId).targetMeta;
            const attachedLeaderIds = attachedLeaderIdsByTarget.get(entry.instanceId) || [];
            const attachedLeaderEntries = attachedLeaderIds
                .map((instanceId) => entriesById.get(instanceId))
                .filter(Boolean);
            entry.relationship.attachedLeaderIds = [...attachedLeaderIds];
            entry.relationship.attachedLeaderNames = attachedLeaderEntries.map((leaderEntry) => leaderEntry.displayName);
            if (attachedLeaderIds.length) {
                entry.relationship.relationshipNotes.push(
                    relationshipSummaryEntry(
                        "attachment",
                        attachedLeaderIds.length === 1
                            ? `Attached Leader: ${entry.relationship.attachedLeaderNames[0]}`
                            : `Attached Leaders: ${entry.relationship.attachedLeaderNames.join(", ")}`,
                        "Leader assignment"
                    )
                );
            }
            if (attachedLeaderEntries.length > targetMeta.maxLeaders) {
                const extraSlotAllowed = attachedLeaderEntries.length === (targetMeta.maxLeaders + 1)
                    && attachedLeaderEntries.some((leaderEntry) => {
                        const otherLeaderEntries = attachedLeaderEntries.filter((otherEntry) => otherEntry.instanceId !== leaderEntry.instanceId);
                        return leaderProvidesAdditionalSlot(leaderEntry, otherLeaderEntries, relationshipMetadata);
                    });
                if (!extraSlotAllowed) {
                    entry.issues.push(`${entry.displayName} has ${attachedLeaderEntries.length} attached Leaders, exceeding its limit of ${targetMeta.maxLeaders}.`);
                }
            }
            validateLeaderSubtypeCaps(entry, attachedLeaderEntries, relationshipMetadata).forEach((issue) => {
                entry.issues.push(issue);
            });
            if (targetMeta.requiresLeader && !attachedLeaderIds.length) {
                entry.issues.push(`${entry.displayName} requires an attached ${targetMeta.requiredLeaderKeywordRefs.join(" or ")} Leader.`);
            }
        });

        resolvedEntries.forEach((entry) => {
            const transportMeta = relationshipMetadata.get(entry.instanceId).transportMeta;
            if (transportMeta) {
                entry.relationship.transportCapacity = {
                    supported: Boolean(transportMeta.supported),
                    rawText: transportMeta.rawText,
                    max: typeof transportMeta.capacity === "number" ? transportMeta.capacity : null,
                    used: 0,
                };
                if (!transportMeta.supported) {
                    unsupportedTransportEntries.push(entry);
                }
            }
        });

        resolvedEntries.forEach((entry) => {
            if (entry.relationship.attachedToInstanceId) {
                return;
            }
            if (!entry.relationship.embarkedInInstanceId) {
                return;
            }
            const transportEntry = entriesById.get(entry.relationship.embarkedInInstanceId) || null;
            if (!transportEntry || !transportEntry.unit) {
                entry.issues.push("Selected transport is not available in the current roster.");
                return;
            }
            if (!unitHasKeyword(transportEntry.unit, "TRANSPORT")) {
                entry.issues.push(`${transportEntry.displayName} is not a Transport unit.`);
                return;
            }

            const transportMeta = relationshipMetadata.get(transportEntry.instanceId).transportMeta;
            const compatibility = transportSupportsUnit(transportMeta, entry.unit);
            if (compatibility && compatibility.allowed === false) {
                const transportReason = compatibility.reason
                    ? `${transportEntry.displayName}: ${compatibility.reason}`
                    : `${entry.displayName} cannot embark in ${transportEntry.displayName}.`;
                entry.issues.push(transportReason);
            }
            entry.relationship.embarkedInLabel = transportEntry.displayName;
            entry.relationship.relationshipNotes.push(
                relationshipSummaryEntry("transport", `Embarked in ${transportEntry.displayName}`, "Transport assignment")
            );
            if (!embarkedUnitIdsByTransport.has(transportEntry.instanceId)) {
                embarkedUnitIdsByTransport.set(transportEntry.instanceId, []);
            }
            embarkedUnitIdsByTransport.get(transportEntry.instanceId).push(entry.instanceId);

            const ownSeats = compatibility && compatibility.mode === "alternativePools"
                ? Math.max(1, entry.quantity || 1)
                : entryModelCount(entry) * transportSeatMultiplier(transportMeta, entry.unit);
            const attachedLeaderIds = attachedLeaderIdsByTarget.get(entry.instanceId) || [];
            const attachedSeats = attachedLeaderIds.reduce((sum, leaderId) => {
                const leaderEntry = entriesById.get(leaderId);
                if (!leaderEntry || !leaderEntry.unit) {
                    return sum;
                }
                leaderEntry.relationship.inheritedEmbarkedInInstanceId = transportEntry.instanceId;
                leaderEntry.relationship.inheritedEmbarkedInLabel = transportEntry.displayName;
                leaderEntry.relationship.relationshipNotes.push(
                    relationshipSummaryEntry("transport", `Embarked with ${entry.displayName} in ${transportEntry.displayName}`, "Transport assignment")
                );
                return sum + (
                    compatibility && compatibility.mode === "alternativePools"
                        ? Math.max(1, leaderEntry.quantity || 1)
                        : (entryModelCount(leaderEntry) * transportSeatMultiplier(transportMeta, leaderEntry.unit))
                );
            }, 0);
            if (compatibility && compatibility.mode === "alternativePools" && compatibility.poolIndex !== -1) {
                if (!transportPoolUsageByTransport.has(transportEntry.instanceId)) {
                    transportPoolUsageByTransport.set(transportEntry.instanceId, new Map());
                }
                const poolUsage = transportPoolUsageByTransport.get(transportEntry.instanceId);
                poolUsage.set(compatibility.poolIndex, (poolUsage.get(compatibility.poolIndex) || 0) + ownSeats + attachedSeats);
            } else {
                transportSeatUsageByTransport.set(
                    transportEntry.instanceId,
                    (transportSeatUsageByTransport.get(transportEntry.instanceId) || 0) + ownSeats + attachedSeats
                );
            }
        });

        transportEntries.forEach((transportEntry) => {
            const embarkedUnitIds = embarkedUnitIdsByTransport.get(transportEntry.instanceId) || [];
            transportEntry.relationship.embarkedUnitIds = [...embarkedUnitIds];
            transportEntry.relationship.embarkedUnitNames = embarkedUnitIds
                .map((instanceId) => entriesById.get(instanceId))
                .filter(Boolean)
                .map((entry) => entry.displayName);
            if (transportEntry.relationship.transportCapacity) {
                const transportMeta = relationshipMetadata.get(transportEntry.instanceId).transportMeta;
                if (transportMeta && transportMeta.mode === "alternativePools") {
                    const poolUsage = transportPoolUsageByTransport.get(transportEntry.instanceId) || new Map();
                    const activePools = [...poolUsage.entries()].filter(([, used]) => used > 0);
                    if (activePools.length === 1) {
                        const [poolIndex, used] = activePools[0];
                        const pool = transportMeta.pools[poolIndex];
                        transportEntry.relationship.transportCapacity.max = pool.capacity;
                        transportEntry.relationship.transportCapacity.used = used;
                    } else {
                        transportEntry.relationship.transportCapacity.used = activePools.reduce((sum, [, used]) => sum + used, 0);
                    }
                } else {
                    transportEntry.relationship.transportCapacity.used = transportSeatUsageByTransport.get(transportEntry.instanceId) || 0;
                }
            }
            if (transportEntry.relationship.embarkedUnitNames.length) {
                transportEntry.relationship.relationshipNotes.push(
                    relationshipSummaryEntry(
                        "transport",
                        transportEntry.relationship.embarkedUnitNames.length === 1
                            ? `Embarked Unit: ${transportEntry.relationship.embarkedUnitNames[0]}`
                            : `Embarked Units: ${transportEntry.relationship.embarkedUnitNames.join(", ")}`,
                        "Transport occupancy"
                    )
                );
            }
            if (unitHasKeyword(transportEntry.unit, "DEDICATED TRANSPORT") && !embarkedUnitIds.length) {
                transportEntry.issues.push("Dedicated Transport has no embarked units assigned.");
            }
            const transportMeta = relationshipMetadata.get(transportEntry.instanceId).transportMeta;
            if (transportMeta && transportMeta.mode === "alternativePools") {
                const poolUsage = transportPoolUsageByTransport.get(transportEntry.instanceId) || new Map();
                const activePools = [...poolUsage.entries()].filter(([, used]) => used > 0);
                if (activePools.length > 1) {
                    transportEntry.issues.push(`${transportEntry.displayName} mixes incompatible transport pool assignments.`);
                } else if (activePools.length === 1) {
                    const [poolIndex, used] = activePools[0];
                    const pool = transportMeta.pools[poolIndex];
                    if (used > pool.capacity) {
                        transportEntry.issues.push(
                            `${transportEntry.displayName} uses ${used}/${pool.capacity} ${pool.label} transport capacity.`
                        );
                    }
                }
            } else if (
                transportEntry.relationship.transportCapacity
                && transportEntry.relationship.transportCapacity.supported
                && typeof transportEntry.relationship.transportCapacity.max === "number"
                && transportEntry.relationship.transportCapacity.used > transportEntry.relationship.transportCapacity.max
            ) {
                transportEntry.issues.push(
                    `${transportEntry.displayName} uses ${transportEntry.relationship.transportCapacity.used}/${transportEntry.relationship.transportCapacity.max} transport capacity.`
                );
            }
        });

        resolvedEntries.forEach((entry) => {
            if (entry.relationship.attachedToInstanceId) {
                return;
            }
            entry.relationship.transportOptions = transportEntries
                .filter((transportEntry) => transportEntry.instanceId !== entry.instanceId)
                .map((transportEntry) => {
                    const transportCapacity = transportEntry.relationship.transportCapacity;
                    const occupancy = transportCapacity && typeof transportCapacity.max === "number"
                        ? ` (${transportCapacity.used}/${transportCapacity.max})`
                        : "";
                    return {
                        instanceId: transportEntry.instanceId,
                        label: `${transportEntry.displayName}${occupancy}`,
                    };
                });
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
                level: "info",
                message: "Strategic Reserves are not modeled yet, so the 25% reserves cap is not checked.",
            });
        }

        if (unsupportedTransportEntries.length) {
            armyWarnings.push({
                code: "transport-rules-partial",
                level: "info",
                message: "Some transport rules are too complex to validate fully, so transport capacity and compatibility checks are advisory for those units.",
            });
        }

        entries.forEach((entry) => {
            const rankedIssues = rankIssuesForEntry(entry);
            entry.issues = rankedIssues.map((issue) => issue.message);
            entry.primaryIssue = rankedIssues.length ? rankedIssues[0].message : null;
            entry.primaryIssueRank = rankedIssues.length ? rankedIssues[0].rank : null;
            entry.isValid = entry.issues.length === 0;
        });

        army.activeDetachment = activeDetachment;
        army.availableEnhancements = availableEnhancements;
        army.stratagems = stratagems;
        army.armyRules = rules.armyRules;
        army.detachments = rules.detachments;
        const compatibility = rosterCompatibility(roster, catalog, availableFactionSlugs, entries);
        const readiness = rosterReadiness(armyIssues, entries.filter((entry) => !entry.isValid), entries);

        return {
            roster,
            army,
            entries,
            totalPoints,
            pointsLimit,
            armyIssues,
            armyWarnings,
            compatibility,
            readiness,
            validEntries: entries.filter((entry) => entry.isValid),
            invalidEntries: entries
                .filter((entry) => !entry.isValid)
                .sort((left, right) => {
                    const leftRank = typeof left.primaryIssueRank === "number" ? left.primaryIssueRank : 99;
                    const rightRank = typeof right.primaryIssueRank === "number" ? right.primaryIssueRank : 99;
                    return (leftRank - rightRank) || entries.indexOf(left) - entries.indexOf(right);
                }),
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
        dedupeSavedRosters,
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
