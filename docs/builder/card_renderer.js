(function () {
    "use strict";

    const STAT_ORDER = ["M", "T", "Sv", "W", "Ld", "OC"];

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function defaultPointsOption(unit) {
        const options = Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [];
        return options.find((option) => option.selectionKind !== "upgrade") || options[0] || null;
    }

    function upgradePointsOptions(unit) {
        return (Array.isArray(unit.pointsOptions) ? unit.pointsOptions : [])
            .filter((option) => option.selectionKind === "upgrade");
    }

    function missingStats(unit) {
        if (unit && unit.quality && Array.isArray(unit.quality.missingStats)) {
            return unit.quality.missingStats;
        }
        const stats = unit && unit.stats ? unit.stats : {};
        return STAT_ORDER.filter((stat) => !stats[stat]);
    }

    function formatKeywords(values) {
        if (!Array.isArray(values) || values.length === 0) {
            return "None";
        }
        return values.join(", ");
    }

    function normalizeComparison(value) {
        return String(value || "")
            .toLowerCase()
            .replace(/[–—-]/g, " ")
            .replace(/\b\d+\b/g, " ")
            .replace(/[^a-z0-9+ ]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function normalizeLoadoutLabel(value) {
        return normalizeComparison(String(value || "").replace(/^\d+\s+/, ""));
    }

    function extractTargetFragment(value) {
        const normalized = String(value || "")
            .replace(/[’']/g, "'")
            .replace(/^\s*(?:this model|the [^']+|an [^']+|a [^']+|all [^']+|any number of models|up to \d+ [^']+)(?:'s)?\s+/i, "")
            .replace(/\.$/, "")
            .trim();
        return normalizeLoadoutLabel(normalized);
    }

    function nameMatchesReference(weaponName, reference) {
        const weaponKey = normalizeComparison(weaponName);
        const referenceKey = normalizeComparison(reference);
        if (!weaponKey || !referenceKey) {
            return false;
        }
        return weaponKey === referenceKey
            || weaponKey.includes(referenceKey)
            || referenceKey.includes(weaponKey);
    }

    function buildLoadoutState(unit, options) {
        const selectedWargear = Array.isArray(options.selectedWargear) ? options.selectedWargear : [];
        const selectedUpgrades = Array.isArray(options.selectedUpgrades) ? options.selectedUpgrades : [];
        const selectedEnhancement = options.selectedEnhancement || null;
        const manualWargearGroups = Array.isArray(options.manualWargearGroups) ? options.manualWargearGroups : [];
        const relationshipNotes = Array.isArray(options.relationshipNotes) ? options.relationshipNotes : [];
        const selectedReferences = [];
        const replacedReferences = [];
        const currentLoadout = [];

        function resolveGroupAction(group, targetLabel) {
            if (group && group.action) {
                return group.action;
            }
            return targetLabel ? "replace" : null;
        }

        function loadoutDetail(group, targetLabel) {
            const action = resolveGroupAction(group, targetLabel);
            if (action === "replace") {
                return targetLabel ? `Replaces ${targetLabel}` : "Replaces existing wargear";
            }
            if (action === "equip") {
                return targetLabel ? `Equipped on ${targetLabel}` : "Additional wargear";
            }
            return targetLabel ? `Selected for ${targetLabel}` : "Selected wargear";
        }

        function recordSelectedChoice(group, choice, count) {
            if (!choice) {
                return;
            }
            const targetLabel = group ? (group.target || group.label) : "";
            const action = resolveGroupAction(group, targetLabel);
            const singularLabel = String(choice.label || "").replace(/^\s*1\s+/, "");
            const countLabel = count && count > 1 ? `${count}x ${singularLabel}` : choice.label;
            currentLoadout.push({
                type: "wargear",
                label: countLabel,
                detail: loadoutDetail(group, targetLabel),
            });
            selectedReferences.push(normalizeLoadoutLabel(choice.label));
            if (targetLabel && action === "replace") {
                replacedReferences.push(extractTargetFragment(targetLabel));
            }
        }

        selectedWargear.forEach((entry) => {
            if (!entry || !entry.group) {
                return;
            }
            if (entry.selectedChoice) {
                recordSelectedChoice(entry.group, entry.selectedChoice, 1);
            }
            if (Array.isArray(entry.selectedChoices)) {
                entry.selectedChoices.forEach((selection) => {
                    if (!selection || !selection.choice || !selection.count) {
                        return;
                    }
                    recordSelectedChoice(entry.group, selection.choice, selection.count);
                });
            }
        });

        selectedUpgrades.forEach((upgrade) => {
            currentLoadout.push({
                type: "upgrade",
                label: upgrade.label,
                detail: `+${upgrade.points} pts upgrade`,
            });
        });

        if (selectedEnhancement) {
            currentLoadout.push({
                type: "enhancement",
                label: selectedEnhancement.name,
                detail: `${selectedEnhancement.body} (+${selectedEnhancement.points} pts)`,
            });
        }

        manualWargearGroups.forEach((group) => {
            currentLoadout.push({
                type: "manual",
                label: group.label,
                detail: "Manual selection still required",
            });
        });

        relationshipNotes.forEach((note) => {
            if (!note || !note.label) {
                return;
            }
            currentLoadout.push({
                type: note.type || "relationship",
                label: note.label,
                detail: note.detail || "Roster relationship",
            });
        });

        return {
            currentLoadout,
            selectedReferences,
            replacedReferences,
            hasManualSelections: manualWargearGroups.length > 0,
        };
    }

    function selectedChoiceForGroup(selectedWargear, groupId) {
        if (!Array.isArray(selectedWargear) || !groupId) {
            return null;
        }
        const selection = selectedWargear.find((item) => item && item.group && item.group.id === groupId) || null;
        if (!selection || !selection.selectedChoice) {
            return null;
        }
        return selection.selectedChoice;
    }

    function inlineGroupTitle(group) {
        return String(group && (group.target || group.label) ? (group.target || group.label) : "Quick swap").trim();
    }

    function inlineGroupKicker(group) {
        if (group && group.action === "equip") {
            return "Add";
        }
        return "Swap";
    }

    function inlineChoiceLabel(choice) {
        return String(choice && choice.label ? choice.label : "")
            .replace(/^\s*\d+\s+/, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function isInlineCardEligible(group) {
        if (!group || group.selectionMode !== "single" || !Array.isArray(group.choices) || !group.choices.length) {
            return false;
        }

        const title = inlineGroupTitle(group).replace(/\s+/g, " ").trim();
        if (!title || title.length > 42) {
            return false;
        }
        if (/[.:]/.test(title)) {
            return false;
        }
        if (/\b(if|when|while|after|before|for every|up to|any number|each|either|different|additional|equipped|replace its|can do one of the following)\b/i.test(title)) {
            return false;
        }
        if (/\b(this model|sergeant|exarch|felarch|squad|unit|bearer|operator|champion)\b/i.test(title)) {
            return false;
        }
        if (group.choices.length > 4) {
            return false;
        }

        return group.choices.every((choice) => {
            const label = inlineChoiceLabel(choice);
            if (!label || label.length > 40) {
                return false;
            }
            if (/[\(\)\[\]:]/.test(label)) {
                return false;
            }
            return !/\b(or|different|additional|equipped|replace|replaced|cannot|can be|and 1)\b/i.test(label);
        });
    }

    function renderInlineWargearControls(unit, options, loadoutState) {
        if (!options || !options.interactiveInlineSelection) {
            return "";
        }
        const groups = unit && unit.wargear && Array.isArray(unit.wargear.options)
            ? unit.wargear.options.filter((group) => isInlineCardEligible(group))
            : [];
        if (!groups.length) {
            return "";
        }

        const selectedWargear = Array.isArray(options.selectedWargear) ? options.selectedWargear : [];
        const instanceId = options.instanceId ? String(options.instanceId) : "";
        const simpleGroups = groups.map((group) => {
            const selectedChoice = selectedChoiceForGroup(selectedWargear, group.id);
            const groupState = selectedChoice ? "is-selected" : "is-unset";
            return `
                <div class="datasheet-inline-group ${groupState}">
                    <div class="datasheet-inline-group-head">
                        <div>
                            <div class="datasheet-inline-group-kicker">${escapeHtml(inlineGroupKicker(group))}</div>
                            <div class="datasheet-inline-group-label">${escapeHtml(inlineGroupTitle(group))}</div>
                            ${group.eligibilityText ? `<div class="datasheet-inline-group-help">${escapeHtml(group.eligibilityText)}</div>` : ""}
                        </div>
                    </div>
                    <div class="datasheet-inline-chip-row" role="group" aria-label="${escapeHtml(inlineGroupTitle(group))}" data-inline-group="${escapeHtml(group.id)}">
                        ${(group.choices || []).map((choice) => {
                            const isActive = Boolean(selectedChoice && selectedChoice.id === choice.id);
                            return `
                                <button
                                    class="datasheet-inline-chip ${isActive ? "is-active" : ""}"
                                    type="button"
                                    data-action="card-inline-select"
                                    data-instance-id="${escapeHtml(instanceId)}"
                                    data-group-id="${escapeHtml(group.id)}"
                                    data-choice-id="${escapeHtml(choice.id)}"
                                    aria-pressed="${isActive ? "true" : "false"}"
                                >
                                    ${escapeHtml(choice.label)}
                                </button>
                            `;
                        }).join("")}
                    </div>
                </div>
            `;
        }).join("");

        return `
            <section class="datasheet-inline-section" aria-label="Inline configuration">
                <div class="datasheet-inline-help">Quick swaps</div>
                <div class="datasheet-inline-grid">${simpleGroups}</div>
                <div class="datasheet-inline-footer">
                    <button
                        class="datasheet-inline-open-editor"
                        type="button"
                        data-action="open-entry-editor"
                        data-instance-id="${escapeHtml(instanceId)}"
                    >
                        Full configuration
                    </button>
                </div>
            </section>
        `;
    }

    function renderEntry(entry) {
        if (!entry || !entry.type) {
            return "";
        }

        if (entry.type === "tagged_list") {
            return `
                <div class="render-entry">
                    <span class="entry-label">${escapeHtml(entry.label)}:</span>
                    <span>${escapeHtml((entry.items || []).join(", "))}</span>
                </div>
            `;
        }

        if (entry.type === "rule") {
            return `
                <div class="render-entry">
                    <span class="entry-label">${escapeHtml(entry.name)}:</span>
                    <span>${escapeHtml(entry.text)}</span>
                </div>
            `;
        }

        if (entry.type === "statement") {
            return `
                <div class="render-entry">
                    <span class="entry-label">${escapeHtml(entry.label)}:</span>
                    <span>${escapeHtml(entry.text)}</span>
                </div>
            `;
        }

        if (entry.type === "text") {
            return `<div class="render-entry">${escapeHtml(entry.text)}</div>`;
        }

        if (entry.type === "list") {
            const items = (entry.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
            return `<ul class="entry-list render-entry">${items}</ul>`;
        }

        if (entry.type === "points") {
            const items = (entry.rows || [])
                .map((row) => `<li>${escapeHtml(row.label)}: ${escapeHtml(row.points)} pts</li>`)
                .join("");
            return `<ul class="entry-list render-entry">${items}</ul>`;
        }

        if (entry.type === "option_group") {
            const items = (entry.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
            return `
                <div class="render-entry">
                    <span class="entry-label">${escapeHtml(entry.label)}:</span>
                    ${items ? `<ul class="entry-list">${items}</ul>` : ""}
                </div>
            `;
        }

        return "";
    }

    function renderWeaponTable(title, skillLabel, weapons, loadoutState, options) {
        if (!Array.isArray(weapons) || weapons.length === 0) {
            return "";
        }
        const renderMode = options && options.renderMode ? options.renderMode : "default";
        const rows = weapons.map((weapon) => {
            const tags = (weapon.abilities || [])
                .map((tag) => `<span class="weapon-tag">${escapeHtml(tag)}</span>`)
                .join("");
            const isSelected = loadoutState.selectedReferences.some((reference) => nameMatchesReference(weapon.name, reference));
            const isReplaced = !isSelected && loadoutState.replacedReferences.some((reference) => nameMatchesReference(weapon.name, reference));
            if (renderMode === "print-clean" && isReplaced && !loadoutState.hasManualSelections) {
                return "";
            }
            const rowClass = isSelected ? " weapon-row-selected" : (isReplaced ? " weapon-row-replaced" : "");
            const choiceBadges = [
                isSelected ? `<span class="weapon-choice-badge weapon-choice-badge-selected">Selected</span>` : "",
                (isReplaced && renderMode !== "print-clean") ? `<span class="weapon-choice-badge weapon-choice-badge-replaced">Replaced</span>` : "",
            ].join("");
            return `
                <tr class="${rowClass.trim()}">
                    <td>
                        <div class="weapon-name">
                            <span>${escapeHtml(weapon.name)}</span>
                            ${choiceBadges ? `<span class="weapon-choice-badges">${choiceBadges}</span>` : ""}
                        </div>
                        ${tags ? `<div class="weapon-tags">${tags}</div>` : ""}
                    </td>
                    <td class="weapon-stat">${escapeHtml(weapon.range || "-")}</td>
                    <td class="weapon-stat">${escapeHtml(weapon.a || "-")}</td>
                    <td class="weapon-stat">${escapeHtml(weapon.skill || "-")}</td>
                    <td class="weapon-stat">${escapeHtml(weapon.s || "-")}</td>
                    <td class="weapon-stat">${escapeHtml(weapon.ap || "-")}</td>
                    <td class="weapon-stat">${escapeHtml(weapon.d || "-")}</td>
                </tr>
            `;
        }).join("");
        return `
            <section>
                <div class="datasheet-section-title">${escapeHtml(title)}</div>
                <table class="weapon-table">
                    <thead>
                        <tr>
                            <th style="text-align:left;">Weapon</th>
                            <th>RNG</th>
                            <th>A</th>
                            <th>${escapeHtml(skillLabel)}</th>
                            <th>S</th>
                            <th>AP</th>
                            <th>D</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </section>
        `;
    }

    function renderCompositionExtras(unit, options) {
        const selectedOption = options.selectedOption || defaultPointsOption(unit);
        const selectedUpgrades = Array.isArray(options.selectedUpgrades) ? options.selectedUpgrades : [];
        const selectedEnhancement = options.selectedEnhancement || null;
        const quantity = options.quantity || 1;
        const selectedPoints = typeof options.selectedPoints === "number"
            ? options.selectedPoints
            : (selectedOption ? selectedOption.points : null);
        const chips = [];

        if (selectedOption && selectedOption.label) {
            chips.push(`<span class="selection-chip">Config: ${escapeHtml(selectedOption.label)}</span>`);
        }
        if (quantity > 1) {
            chips.push(`<span class="selection-chip">Qty: ${escapeHtml(quantity)}</span>`);
        }
        if (selectedOption && selectedOption.selectionKind) {
            chips.push(`<span class="selection-chip">Type: ${escapeHtml(selectedOption.selectionKind)}</span>`);
        }
        selectedUpgrades.forEach((upgrade) => {
            chips.push(`<span class="selection-chip">Upgrade: ${escapeHtml(upgrade.label)}</span>`);
        });
        if (selectedEnhancement) {
            chips.push(`<span class="selection-chip">Enhancement: ${escapeHtml(selectedEnhancement.name)}</span>`);
        }
        if (unit.selectionMode === "manual") {
            chips.push(`<span class="selection-chip">Manual labels</span>`);
        }
        const unitMissingStats = missingStats(unit);
        if (unitMissingStats.length) {
            chips.push(`<span class="selection-chip selection-chip-warning">Missing stats: ${escapeHtml(unitMissingStats.join(", "))}</span>`);
        }

        return {
            chips,
            selectedPoints,
        };
    }

    function legacyRenderSections(unit) {
        const sections = [];
        const abilityEntries = [];

        if (unit.abilities && unit.abilities.core && unit.abilities.core.length) {
            abilityEntries.push({
                type: "tagged_list",
                label: "CORE",
                items: unit.abilities.core,
            });
        }
        if (unit.abilities && unit.abilities.faction && unit.abilities.faction.length) {
            abilityEntries.push({
                type: "tagged_list",
                label: "FACTION",
                items: unit.abilities.faction,
            });
        }
        (unit.abilities && unit.abilities.datasheet ? unit.abilities.datasheet : []).forEach((rule) => {
            abilityEntries.push(rule);
        });
        (unit.abilities && unit.abilities.other ? unit.abilities.other : []).forEach((entry) => {
            abilityEntries.push(entry);
        });
        if (abilityEntries.length) {
            sections.push({
                title: "ABILITIES",
                displayStyle: "section",
                entries: abilityEntries,
            });
        }

        (unit.renderBlocks || []).forEach((block) => sections.push(block));

        const compositionEntries = [];
        if (unit.composition && Array.isArray(unit.composition.rawLines) && unit.composition.rawLines.length) {
            compositionEntries.push({
                type: "list",
                items: unit.composition.rawLines,
            });
        }
        (unit.composition && Array.isArray(unit.composition.statements) ? unit.composition.statements : []).forEach((statement) => {
            compositionEntries.push({
                type: "statement",
                label: statement.label,
                text: statement.text,
            });
        });
        if (Array.isArray(unit.pointsOptions) && unit.pointsOptions.length) {
            compositionEntries.push({
                type: "points",
                rows: unit.pointsOptions.map((option) => ({
                    label: option.label,
                    points: option.points,
                })),
            });
        }
        if (compositionEntries.length) {
            sections.push({
                title: "UNIT COMPOSITION",
                displayStyle: "section",
                entries: compositionEntries,
            });
        }

        return sections;
    }

    function renderSection(section, unit, options) {
        if (!section) {
            return "";
        }
        const body = (section.entries || []).map(renderEntry).join("");
        if (section.displayStyle === "damaged") {
            return `
                <div class="damaged-block">
                    <div class="damaged-title">${escapeHtml(section.title)}</div>
                    <div class="damaged-text">${body}</div>
                </div>
            `;
        }

        if (String(section.title || "").toUpperCase() === "UNIT COMPOSITION") {
            const compositionExtras = renderCompositionExtras(unit, options);
            return `
                <section>
                    <div class="datasheet-section-title">${escapeHtml(section.title)}</div>
                    <div class="datasheet-section-content composition-box">
                        ${body}
                        ${compositionExtras.chips.length ? `<div class="selection-summary">${compositionExtras.chips.join("")}</div>` : ""}
                        ${compositionExtras.selectedPoints != null ? `<div class="points-badge">${escapeHtml(compositionExtras.selectedPoints)} pts</div>` : ""}
                    </div>
                </section>
            `;
        }

        return `
            <section>
                <div class="datasheet-section-title">${escapeHtml(section.title)}</div>
                <div class="datasheet-section-content">
                    ${body}
                </div>
            </section>
        `;
    }

    function renderCurrentLoadout(loadoutState) {
        const items = loadoutState.currentLoadout || [];
        if (!items.length) {
            return "";
        }

        const body = items.map((item) => `
            <div class="loadout-row loadout-row-${escapeHtml(item.type)}">
                <span class="loadout-pill loadout-pill-${escapeHtml(item.type)}">${escapeHtml(item.type)}</span>
                <div>
                    <div class="loadout-label">${escapeHtml(item.label)}</div>
                    <div class="loadout-detail">${escapeHtml(item.detail)}</div>
                </div>
            </div>
        `).join("");

        return `
            <section>
                <div class="datasheet-section-title">Current Loadout</div>
                <div class="datasheet-section-content">${body}</div>
            </section>
        `;
    }

    function renderConfigurationStrip(unit, options, loadoutState) {
        const chips = [];
        const selectedOption = options.selectedOption || defaultPointsOption(unit);
        const selectedUpgrades = Array.isArray(options.selectedUpgrades) ? options.selectedUpgrades : [];
        const selectedEnhancement = options.selectedEnhancement || null;

        if (selectedOption && selectedOption.label) {
            chips.push(`<span class="config-chip">Config: ${escapeHtml(selectedOption.label)}</span>`);
        }
        selectedUpgrades.forEach((upgrade) => {
            chips.push(`<span class="config-chip config-chip-upgrade">+ ${escapeHtml(upgrade.label)}</span>`);
        });
        if (selectedEnhancement) {
            chips.push(`<span class="config-chip config-chip-selected">Enhancement: ${escapeHtml(selectedEnhancement.name)}</span>`);
        }
        loadoutState.currentLoadout
            .filter((item) => item.type === "wargear")
            .forEach((item) => {
                chips.push(`<span class="config-chip config-chip-selected">${escapeHtml(item.label)}</span>`);
            });
        loadoutState.currentLoadout
            .filter((item) => item.type === "manual")
            .forEach(() => {
                chips.push(`<span class="config-chip config-chip-warning">Manual wargear</span>`);
            });
        loadoutState.currentLoadout
            .filter((item) => item.type === "attachment" || item.type === "transport")
            .forEach((item) => {
                chips.push(`<span class="config-chip">${escapeHtml(item.label)}</span>`);
            });

        if (!chips.length) {
            return "";
        }

        return `<div class="datasheet-config-strip">${chips.join("")}</div>`;
    }

    function renderCard(unit, options) {
        const opts = options || {};
        const renderMode = opts.renderMode || "default";
        const selectedOption = opts.selectedOption || defaultPointsOption(unit);
        const selectedUpgrades = Array.isArray(opts.selectedUpgrades) ? opts.selectedUpgrades : [];
        const loadoutState = buildLoadoutState(unit, opts);
        const inlineWargearControls = renderInlineWargearControls(unit, opts, loadoutState);
        const quantity = opts.quantity || 1;
        const meta = [];
        if (selectedOption && selectedOption.label) {
            meta.push(`Config: ${selectedOption.label}`);
        }
        if (selectedUpgrades.length) {
            meta.push(`Upgrades: ${selectedUpgrades.map((upgrade) => upgrade.label).join(", ")}`);
        }
        if (opts.selectedEnhancement) {
            meta.push(`Enhancement: ${opts.selectedEnhancement.name}`);
        }
        if (quantity > 1) {
            meta.push(`Qty ${quantity}`);
        }
        const unitMissingStats = missingStats(unit);
        const renderSections = Array.isArray(unit.renderSections) && unit.renderSections.length
            ? unit.renderSections
            : legacyRenderSections(unit);

        return `
            <article class="datasheet-card">
                <header class="datasheet-header">
                    <h1 class="datasheet-title">${escapeHtml(unit.name)}</h1>
                    ${meta.length ? `<div class="datasheet-meta">${escapeHtml(meta.join(" | "))}</div>` : ""}
                </header>
                ${renderConfigurationStrip(unit, opts, loadoutState)}
                ${inlineWargearControls}
                ${unitMissingStats.length || unit.selectionMode === "manual" ? `
                    <div class="datasheet-quality">
                        ${unitMissingStats.length ? `<div class="datasheet-quality-row"><strong>Missing stats:</strong> ${escapeHtml(unitMissingStats.join(", "))}</div>` : ""}
                        ${unit.selectionMode === "manual" ? `<div class="datasheet-quality-row"><strong>Selection labels:</strong> preserved from source because the option format is still ambiguous.</div>` : ""}
                    </div>
                ` : ""}
                <div class="datasheet-stats">
                    ${STAT_ORDER.map((stat) => `
                        <div class="datasheet-stat">
                            <div class="datasheet-stat-label">${escapeHtml(stat)}</div>
                            <div class="datasheet-stat-value">${escapeHtml(unit.stats && unit.stats[stat] ? unit.stats[stat] : "-")}</div>
                        </div>
                    `).join("")}
                </div>
                ${unit.stats && unit.stats.invulnerableSave ? `
                    <div class="datasheet-invuln">
                        <div class="datasheet-invuln-shield">${escapeHtml(unit.stats.invulnerableSave)}</div>
                        <div class="datasheet-invuln-label">Invulnerable Save</div>
                    </div>
                ` : ""}
                <div class="datasheet-grid">
                    <div class="datasheet-left">
                        ${renderWeaponTable("Ranged Weapons", "BS", unit.weapons ? unit.weapons.ranged || [] : [], loadoutState, { renderMode })}
                        ${renderWeaponTable("Melee Weapons", "WS", unit.weapons ? unit.weapons.melee || [] : [], loadoutState, { renderMode })}
                    </div>
                    <div class="datasheet-right">
                        ${renderSections.map((section) => renderSection(section, unit, opts)).join("")}
                        ${renderCurrentLoadout(loadoutState)}
                    </div>
                </div>
                <footer class="datasheet-footer">
                    <div><span class="datasheet-footer-label">Keywords:</span>${escapeHtml(formatKeywords(unit.keywords))}</div>
                    <div><span class="datasheet-footer-label">Faction Keywords:</span>${escapeHtml(formatKeywords(unit.factionKeywords))}</div>
                </footer>
            </article>
        `;
    }

    function renderCardList(units, getOptions) {
        return (units || [])
            .map((unit, index) => renderCard(unit, typeof getOptions === "function" ? getOptions(unit, index) : {}))
            .join("");
    }

    window.WahBuilderCardRenderer = {
        defaultPointsOption,
        renderCard,
        renderCardList,
        upgradePointsOptions,
    };
})();
