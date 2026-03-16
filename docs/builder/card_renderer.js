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
        const manualWargearGroups = Array.isArray(options.manualWargearGroups) ? options.manualWargearGroups : [];
        const selectedReferences = [];
        const replacedReferences = [];
        const currentLoadout = [];

        selectedWargear.forEach((entry) => {
            if (!entry || !entry.selectedChoice || !entry.group) {
                return;
            }
            const selectedLabel = entry.selectedChoice.label;
            const targetLabel = entry.group.target || entry.group.label;
            currentLoadout.push({
                type: "wargear",
                label: selectedLabel,
                detail: targetLabel ? `Replaces ${targetLabel}` : "Selected wargear",
            });
            selectedReferences.push(normalizeLoadoutLabel(selectedLabel));
            if (targetLabel) {
                replacedReferences.push(extractTargetFragment(targetLabel));
            }
        });

        selectedUpgrades.forEach((upgrade) => {
            currentLoadout.push({
                type: "upgrade",
                label: upgrade.label,
                detail: `+${upgrade.points} pts upgrade`,
            });
        });

        manualWargearGroups.forEach((group) => {
            currentLoadout.push({
                type: "manual",
                label: group.label,
                detail: "Manual selection still required",
            });
        });

        return {
            currentLoadout,
            selectedReferences,
            replacedReferences,
            hasManualSelections: manualWargearGroups.length > 0,
        };
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

    function renderAbilities(unit) {
        const groups = [];
        if (unit.abilities && unit.abilities.core && unit.abilities.core.length) {
            groups.push(`
                <div class="ability-group">
                    <span class="ability-heading">Core:</span>
                    <span>${escapeHtml(unit.abilities.core.join(", "))}</span>
                </div>
            `);
        }
        if (unit.abilities && unit.abilities.faction && unit.abilities.faction.length) {
            groups.push(`
                <div class="ability-group">
                    <span class="ability-heading">Faction:</span>
                    <span>${escapeHtml(unit.abilities.faction.join(", "))}</span>
                </div>
            `);
        }
        (unit.abilities && unit.abilities.datasheet ? unit.abilities.datasheet : []).forEach((rule) => {
            groups.push(`
                <div class="ability-group">
                    <span class="ability-heading">${escapeHtml(rule.name)}:</span>
                    <span>${escapeHtml(rule.text)}</span>
                </div>
            `);
        });
        (unit.abilities && unit.abilities.other ? unit.abilities.other : []).forEach((entry) => {
            groups.push(renderEntry(entry));
        });
        return groups.join("");
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

    function renderRenderBlock(block) {
        if (!block) {
            return "";
        }
        const body = (block.entries || []).map(renderEntry).join("");
        if (block.displayStyle === "damaged") {
            return `
                <div class="damaged-block">
                    <div class="damaged-title">${escapeHtml(block.title)}</div>
                    <div class="damaged-text">${body}</div>
                </div>
            `;
        }
        return `
            <section>
                <div class="datasheet-section-title">${escapeHtml(block.title)}</div>
                <div class="datasheet-section-content">${body}</div>
            </section>
        `;
    }

    function renderComposition(unit, options) {
        const lines = (unit.composition && unit.composition.rawLines ? unit.composition.rawLines : [])
            .map((line) => `<li>${escapeHtml(line)}</li>`)
            .join("");
        const selectedOption = options.selectedOption || defaultPointsOption(unit);
        const selectedUpgrades = Array.isArray(options.selectedUpgrades) ? options.selectedUpgrades : [];
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
        if (unit.selectionMode === "manual") {
            chips.push(`<span class="selection-chip">Manual labels</span>`);
        }
        const unitMissingStats = missingStats(unit);
        if (unitMissingStats.length) {
            chips.push(`<span class="selection-chip selection-chip-warning">Missing stats: ${escapeHtml(unitMissingStats.join(", "))}</span>`);
        }

        return `
            <section>
                <div class="datasheet-section-title">Unit Composition</div>
                <div class="datasheet-section-content composition-box">
                    ${lines ? `<ul class="datasheet-lines">${lines}</ul>` : `<div>No composition data.</div>`}
                    ${chips.length ? `<div class="selection-summary">${chips.join("")}</div>` : ""}
                    ${selectedPoints != null ? `<div class="points-badge">${escapeHtml(selectedPoints)} pts</div>` : ""}
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

        if (selectedOption && selectedOption.label) {
            chips.push(`<span class="config-chip">Config: ${escapeHtml(selectedOption.label)}</span>`);
        }
        selectedUpgrades.forEach((upgrade) => {
            chips.push(`<span class="config-chip config-chip-upgrade">+ ${escapeHtml(upgrade.label)}</span>`);
        });
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
        const quantity = opts.quantity || 1;
        const meta = [];
        if (selectedOption && selectedOption.label) {
            meta.push(`Config: ${selectedOption.label}`);
        }
        if (selectedUpgrades.length) {
            meta.push(`Upgrades: ${selectedUpgrades.map((upgrade) => upgrade.label).join(", ")}`);
        }
        if (quantity > 1) {
            meta.push(`Qty ${quantity}`);
        }
        const unitMissingStats = missingStats(unit);

        return `
            <article class="datasheet-card">
                <header class="datasheet-header">
                    <h1 class="datasheet-title">${escapeHtml(unit.name)}</h1>
                    ${meta.length ? `<div class="datasheet-meta">${escapeHtml(meta.join(" | "))}</div>` : ""}
                </header>
                ${renderConfigurationStrip(unit, opts, loadoutState)}
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
                        <section>
                            <div class="datasheet-section-title">Abilities</div>
                            <div class="datasheet-section-content">${renderAbilities(unit)}</div>
                        </section>
                        ${renderCurrentLoadout(loadoutState)}
                        ${(unit.renderBlocks || []).map(renderRenderBlock).join("")}
                        ${renderComposition(unit, opts)}
                    </div>
                </div>
                <footer class="datasheet-footer">
                    <div><span class="datasheet-footer-label">Keywords:</span>${escapeHtml(formatKeywords(unit.keywords))}</div>
                    <div><span class="datasheet-footer-label">Faction:</span>${escapeHtml(formatKeywords(unit.factionKeywords))}</div>
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
