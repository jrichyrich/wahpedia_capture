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
        return options[0] || null;
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

    function renderWeaponTable(title, skillLabel, weapons) {
        if (!Array.isArray(weapons) || weapons.length === 0) {
            return "";
        }
        const rows = weapons.map((weapon) => {
            const tags = (weapon.abilities || [])
                .map((tag) => `<span class="weapon-tag">${escapeHtml(tag)}</span>`)
                .join("");
            return `
                <tr>
                    <td>
                        <div class="weapon-name">${escapeHtml(weapon.name)}</div>
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

    function renderCard(unit, options) {
        const opts = options || {};
        const selectedOption = opts.selectedOption || defaultPointsOption(unit);
        const quantity = opts.quantity || 1;
        const meta = [];
        if (selectedOption && selectedOption.label) {
            meta.push(`Config: ${selectedOption.label}`);
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
                        ${renderWeaponTable("Ranged Weapons", "BS", unit.weapons ? unit.weapons.ranged || [] : [])}
                        ${renderWeaponTable("Melee Weapons", "WS", unit.weapons ? unit.weapons.melee || [] : [])}
                    </div>
                    <div class="datasheet-right">
                        <section>
                            <div class="datasheet-section-title">Abilities</div>
                            <div class="datasheet-section-content">${renderAbilities(unit)}</div>
                        </section>
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
    };
})();
