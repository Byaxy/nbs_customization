/**
 * NBS Customization — nbs_workspace.js
 *
 * Card and table theming for every workspace and dashboard.
 *
 * Workspace widgets live in the page itself. Their chart and number bodies are
 * Insights islands in a shadow root, which page CSS cannot reach. The dashboard
 * page is one island for the same reason, so the card accents are written inside
 * the shadow root.
 *
 * Chart series, axes, and legends are left untouched. Every card title is navy
 * and bold. Only number cards take the left accent and the accented value.
 */

const ISLAND_STYLE_ID = "nbs-accent-style";

const BADGE_COLUMNS = [
	{ name: "delay (days)", tone: "red" },
	{ name: "days left", tone: "amber" },
	{ name: "age (days)", tone: "red" },
	{ name: "actual qty", tone: "red" },
	{ name: "on-time %", tone: "red" },
	{ name: "amount to receive", tone: "amber" },
	{ name: "overdue", tone: "amber" },
];

const NUMBER_CARD_STYLE = `
.text-3xl-semibold {
	color: var(--nbs-card-accent-ink, var(--nbs-card-accent)) !important;
}
`;

const DASHBOARD_CARD_STYLE = `
.nbs-accent-card {
	background-color: color-mix(
		in srgb,
		var(--nbs-card-accent) var(--nbs-number-tint, 10%),
		#ffffff
	) !important;
	border-left: 6px solid var(--nbs-card-accent) !important;
	border-left-color: var(--nbs-card-accent) !important;
}

[data-testid="dashboard-cell"] [data-slot="chart-card"] [data-slot="chart-header"] span {
	color: var(--nbs-primary, #001b52) !important;
	font-weight: 700;
}

.nbs-accent-card .text-3xl-semibold {
	color: var(--nbs-card-accent-ink, var(--nbs-card-accent)) !important;
}

:is([data-testid="dashboard-cell"], [role="dialog"]) table thead,
:is([data-testid="dashboard-cell"], [role="dialog"]) table thead td {
	background-color: var(--nbs-table-header-bg, #001b52) !important;
	color: var(--nbs-table-header-text, #ffffff) !important;
	border-color: rgba(255, 255, 255, 0.18) !important;
}

:is([data-testid="dashboard-cell"], [role="dialog"]) table thead td * {
	color: var(--nbs-table-header-text, #ffffff) !important;
}

:is([data-testid="dashboard-cell"], [role="dialog"]) table thead td *::before {
	color: rgba(255, 255, 255, 0.65) !important;
}

:is([data-testid="dashboard-cell"], [role="dialog"]) table tbody tr:nth-child(even):not(.sticky):not([height="99%"]) > td:not(.nbs-rule-painted) {
	background-color: var(--nbs-table-even-bg, #dbeafe) !important;
}

:is([data-testid="dashboard-cell"], [role="dialog"]) table tbody tr:hover:not(.sticky):not([height="99%"]) > td:not(.nbs-rule-painted) {
	background-color: var(--nbs-table-row-hover-bg, #dbeafe) !important;
}

[data-testid="dashboard-cell"] table tbody tr:nth-child(odd):not(.sticky):not([height="99%"]) td.nbs-badge-cell {
	background-color: var(--nbs-workspace-surface, #ffffff) !important;
}

[data-testid="dashboard-cell"] table tbody tr:nth-child(even):not(.sticky):not([height="99%"]) td.nbs-badge-cell {
	background-color: var(--nbs-table-even-bg, #dbeafe) !important;
}

[data-testid="dashboard-cell"] table tbody tr:hover:not(.sticky):not([height="99%"]) td.nbs-badge-cell {
	background-color: var(--nbs-table-row-hover-bg, #dbeafe) !important;
}

[data-testid="dashboard-cell"] table tbody td.nbs-badge-cell {
	border-color: var(--outline-gray-1, #f3f3f3) !important;
}

.nbs-badge {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	min-width: 34px;
	height: 20px;
	padding: 0 9px;
	border-radius: 999px;
	color: #ffffff;
	font-size: 12px;
	font-weight: 600;
	font-variant-numeric: tabular-nums;
	line-height: 1;
	white-space: nowrap;
}

.nbs-badge-red {
	background: var(--nbs-danger, #dc2626);
}

.nbs-badge-amber {
	background: #b45309;
}

.nbs-badge-green {
	background: #047857;
}
`;

function normalize(value) {
	return (value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function accentFor(title) {
	return window.NBSCardTones?.forTitle(title) || { color: "#475569", ink: "#475569" };
}

class NBSWorkspaceTheme {
	constructor() {
		this.queued = false;
		this.partyNamesRequested = false;
		this.partyNamesLoading = false;
		this.observedShadows = new WeakSet();
		this.observedTables = new WeakSet();
	}

	init() {
		this.syncRoute();
		this.apply();
		this.observePage();

		if (window.frappe?.router?.on) {
			frappe.router.on("change", () => this.schedule());
		}

		// Islands mount after the route renders, so a few passes catch them.
		[150, 500, 1200, 2500].forEach((delay) => setTimeout(() => this.apply(), delay));
	}

	schedule() {
		if (this.queued) return;
		this.queued = true;
		requestAnimationFrame(() => {
			this.queued = false;
			this.syncRoute();
			this.apply();
		});
	}

	observePage() {
		if (!window.MutationObserver) return;

		this.pageObserver = new MutationObserver(() => this.schedule());
		this.pageObserver.observe(document.body, { childList: true, subtree: true });
	}

	routeMode() {
		const path = window.location.pathname.replace(/\/+$/, "");

		if (path.includes("/dashboard-view/")) {
			return "dashboard";
		}

		if (document.querySelector(".editor-js-container")) {
			return "workspace";
		}

		return "";
	}

	syncRoute() {
		const mode = this.routeMode();

		if (mode) {
			document.body.dataset.nbsDesk = mode;
		} else {
			delete document.body.dataset.nbsDesk;
		}
	}

	apply() {
		if (!document.body.dataset.nbsDesk) return;

		this.applyWidgets();
		this.applyDashboardIsland();
	}

	applyWidgets() {
		document.querySelectorAll(".widget").forEach((widget) => {
			if (!widget.closest("[data-nbs-desk]")) return;
			if (!widget.classList.contains("number-widget-box")) {
				widget.style.removeProperty("--nbs-card-accent");
				widget.style.removeProperty("--nbs-card-accent-ink");
				return;
			}

			const title = widget.querySelector(".widget-title")?.textContent || "";
			const accent = accentFor(title);
			widget.style.setProperty("--nbs-card-accent", accent.color);
			widget.style.setProperty("--nbs-card-accent-ink", accent.ink);

			const island = widget.querySelector(".frappe-island");
			if (!island) return;

			island.style.setProperty("--nbs-card-accent", accent.color);
			island.style.setProperty("--nbs-card-accent-ink", accent.ink);
			this.ensureShadowStyle(island, NUMBER_CARD_STYLE);
		});
	}

	applyDashboardIsland() {
		document.querySelectorAll(".frappe-island").forEach((island) => {
			if (island.closest(".widget")) return;

			const shadow = island.shadowRoot;
			if (!shadow) return;

			this.observeShadow(shadow);

			const cells = shadow.querySelectorAll('[data-testid="dashboard-cell"]');
			if (!cells.length) return;

			this.ensureShadowStyle(island, DASHBOARD_CARD_STYLE);

			cells.forEach((cell) => this.accentDashboardCard(cell));
			this.markRulePaintedCells(shadow);
			this.applyTableBadges(shadow);
			this.requestPartyNames();
			window.NBSPartyNames?.apply(shadow);
		});
	}

	requestPartyNames() {
		if (this.partyNamesRequested) return;

		if (!window.NBSPartyNames) {
			this.loadPartyNamesScript();
			return;
		}

		this.partyNamesRequested = true;
		window.NBSPartyNames.load().then((loaded) => {
			if (loaded) this.schedule();
		});
	}

	loadPartyNamesScript() {
		if (this.partyNamesLoading) return;

		const script = document.createElement("script");
		script.src = "/assets/nbs_customization/js/nbs_party_names.js";
		script.onload = () => {
			this.partyNamesLoading = false;
			this.requestPartyNames();
		};
		script.onerror = () => {
			this.partyNamesLoading = false;
		};
		this.partyNamesLoading = true;
		document.head.appendChild(script);
	}

	markRulePaintedCells(shadow) {
		const tables = shadow.querySelectorAll(
			':is([data-testid="dashboard-cell"], [role="dialog"]) table'
		);

		tables.forEach((table) => this.observeTable(table));
		shadow
			.querySelectorAll(
				':is([data-testid="dashboard-cell"], [role="dialog"]) table tbody td'
			)
			.forEach((cell) => {
				cell.classList.toggle("nbs-rule-painted", Boolean(cell.style.backgroundColor));
			});
	}

	observeTable(table) {
		if (!window.MutationObserver || this.observedTables.has(table)) return;

		this.observedTables.add(table);
		new MutationObserver(() => this.schedule()).observe(table, {
			attributes: true,
			attributeFilter: ["style"],
			subtree: true,
		});
	}

	applyTableBadges(shadow) {
		shadow.querySelectorAll('[data-testid="dashboard-cell"] table').forEach((table) => {
			const header = table.tHead?.rows?.[table.tHead.rows.length - 1];
			if (!header) return;

			const headers = Array.from(header.cells);
			BADGE_COLUMNS.forEach(({ name, tone }) => {
				const index = headers.findIndex(
					(cell) =>
						normalize(cell.getAttribute("data-column-name") || cell.textContent) ===
						name
				);
				if (index < 0) return;

				Array.from(table.tBodies[0]?.rows || []).forEach((row) => {
					if (row.classList.contains("sticky") || row.getAttribute("height") === "99%") {
						return;
					}

					const cell = row.cells[index];
					if (cell) this.decorateBadgeCell(cell, tone);
				});
			});
		});
	}

	decorateBadgeCell(cell, tone) {
		const badge = Array.from(cell.children).find((child) =>
			child.classList.contains("nbs-badge")
		);
		const flagged = Boolean(cell.style.backgroundColor);

		if (!flagged) {
			cell.classList.remove("nbs-badge-cell");
			if (badge) badge.replaceWith(document.createTextNode(badge.textContent));
			return;
		}

		const clone = cell.cloneNode(true);
		clone.querySelector(".nbs-badge")?.remove();
		const text = clone.textContent.trim();

		// Already decorated, and no new text from Vue sits beside the badge.
		if (badge && !text) return;

		if (!text) {
			cell.classList.remove("nbs-badge-cell");
			badge?.remove();
			return;
		}

		cell.classList.add("nbs-badge-cell");
		cell.textContent = "";

		const next = document.createElement("span");
		next.className = `nbs-badge nbs-badge-${tone}`;
		next.textContent = text;
		cell.appendChild(next);
	}

	accentDashboardCard(cell) {
		const cards = cell.querySelectorAll('[data-slot="chart-card"]');
		const card =
			Array.from(cards).find((node) => node.classList.contains("bg-surface-elevation-2")) ||
			cards[0];
		if (!card) return;

		// Number readings sit inside a wrapper that names its reading length.
		// That holds even when the reading has no value to print.
		const isNumber =
			Boolean(card.querySelector(".text-3xl-semibold")) ||
			Boolean(card.closest('[style*="--reading-length"]'));
		if (!isNumber) {
			card.classList.remove("nbs-accent-card");
			card.style.removeProperty("--nbs-card-accent");
			card.style.removeProperty("--nbs-card-accent-ink");
			return;
		}

		const title =
			card.querySelector('[data-slot="chart-header"] span')?.textContent ||
			cell.getAttribute("title") ||
			"";
		if (!normalize(title)) return;

		const accent = accentFor(title);
		card.style.setProperty("--nbs-card-accent", accent.color);
		card.style.setProperty("--nbs-card-accent-ink", accent.ink);
		card.classList.add("nbs-accent-card");
	}

	ensureShadowStyle(island, css) {
		const shadow = island.shadowRoot;
		if (!shadow || shadow.getElementById(ISLAND_STYLE_ID)) return;

		const style = document.createElement("style");
		style.id = ISLAND_STYLE_ID;
		style.textContent = css;
		shadow.appendChild(style);
	}

	observeShadow(shadow) {
		if (!window.MutationObserver || this.observedShadows.has(shadow)) return;

		this.observedShadows.add(shadow);
		new MutationObserver(() => this.schedule()).observe(shadow, {
			childList: true,
			subtree: true,
			characterData: true,
		});
	}
}

function initNBSWorkspaceTheme() {
	if (window.NBSWorkspaceTheme) return;
	window.NBSWorkspaceTheme = new NBSWorkspaceTheme();
	window.NBSWorkspaceTheme.init();
}

if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", initNBSWorkspaceTheme);
} else {
	initNBSWorkspaceTheme();
}
