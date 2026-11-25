/**
 * NBS Customization — nbs_list_stats.js
 *
 * Mounts a compact Insights dashboard above the filters of selected list views.
 * The dashboard is a normal Insights dashboard island; the list query is never
 * touched. Each dashboard uses the reader's default Company.
 */

(function () {
	if (window.NBSListStats) return;
	window.NBSListStats = true;

	const DASHBOARDS = {
		"Sales Invoice": "nbs-list-stats-sales-invoice-stats",
		"Sales Order": "nbs-list-stats-sales-order-stats",
		Quotation: "nbs-list-stats-quotation-stats",
		"Sales Commission": "nbs-list-stats-sales-commission-stats",
		"Commission Payout": "nbs-list-stats-commission-payout-stats",
		"Promissory Note": "nbs-list-stats-promissory-note-stats",
		"Purchase Order": "nbs-list-stats-purchase-order-stats",
		"Purchase Invoice": "nbs-list-stats-purchase-invoice-stats",
		"Request for Quotation": "nbs-list-stats-request-for-quotation-stats",
		Receipt: "nbs-list-stats-receipt-stats",
		"Loan Waybill": "nbs-list-stats-loan-waybill-stats",
		Expense: "nbs-list-stats-expense-stats",
	};

	const STATS_STYLE = `
[data-testid="dashboard-cell"]:has(button[title^="Company"]) {
	display: none !important;
}

.relative.isolate.w-full:has([data-testid="dashboard-cell"]) {
	transform: translateY(-44px) !important;
}

.overflow-y-auto.p-2 {
	overflow-y: hidden !important;
}
`;

	let container = null;
	let island = null;
	let mounted_for = null;
	let pending_mount = null;
	let queued = false;

	function current_doctype() {
		const route = window.frappe?.get_route?.() || [];
		return route[0] === "List" ? route[1] : null;
	}

	function visible_list_sections() {
		return [
			...document.querySelectorAll(
				".layout-main-section-wrapper.list-view .layout-main-section"
			),
		].filter(
			(section) =>
				section.getClientRects().length > 0 && section.getBoundingClientRect().height > 0
		);
	}

	function visible_list_section() {
		return visible_list_sections()[0] || null;
	}

	function remove_stale_containers(keep = null) {
		document.querySelectorAll(".nbs-list-stats").forEach((element) => {
			if (element !== keep) element.remove();
		});
	}

	function unmount() {
		island?.unmount();
		island = null;
		container?.remove();
		container = null;
		mounted_for = null;
	}

	function inject_style(shadow) {
		let style = shadow.getElementById("nbs-list-stats-style");
		if (!style) {
			style = document.createElement("style");
			style.id = "nbs-list-stats-style";
			shadow.appendChild(style);
		}
		style.textContent = `${window.NBSIslandStyle || ""}\n${STATS_STYLE}`;
	}

	function decorate_cards(shadow) {
		shadow.querySelectorAll('[data-slot="chart-card"]').forEach((card) => {
			if (!card.classList.contains("bg-surface-elevation-2")) return;
			const title = card.querySelector('[data-slot="chart-header"] span')?.textContent || "";
			const accent = window.NBSCardTones?.forTitle(title);
			if (!accent) return;

			card.style.setProperty("--nbs-card-accent", accent.color);
			card.style.setProperty("--nbs-card-accent-ink", accent.ink);
			card.classList.add("nbs-accent-card");
		});
	}

	function prepare_island() {
		const host = container?.querySelector(".frappe-island");
		const shadow = host?.shadowRoot;
		if (!shadow) return false;

		inject_style(shadow);
		decorate_cards(shadow);

		if (!shadow.__nbsListStatsObserver) {
			shadow.__nbsListStatsObserver = new MutationObserver(() => decorate_cards(shadow));
			shadow.__nbsListStatsObserver.observe(shadow, { childList: true, subtree: true });
		}
		return true;
	}

	function retry_prepare() {
		if (prepare_island()) return;
		[50, 200, 600, 1200].forEach((delay) => setTimeout(prepare_island, delay));
	}

	function mount(doctype, dashboard) {
		const section = visible_list_section();
		if (!section || current_doctype() !== doctype) return;

		unmount();
		remove_stale_containers();

		container = document.createElement("div");
		container.className = "nbs-list-stats";
		container.dataset.nbsListStats = doctype;

		const form = section.querySelector(".page-form.list-page-form");
		section.insertBefore(container, form || section.firstChild);

		island = frappe.ui.mount_island("insights.dashboard", container, { dashboard });
		island.ready?.catch(() => container?.remove());
		mounted_for = doctype;
		retry_prepare();
	}

	function cancel_pending_mount() {
		if (!pending_mount) return;

		if (pending_mount.idle !== undefined && window.cancelIdleCallback) {
			cancelIdleCallback(pending_mount.idle);
		}
		if (pending_mount.timeout !== undefined) clearTimeout(pending_mount.timeout);
		pending_mount = null;
	}

	function schedule_mount(doctype, dashboard) {
		if (pending_mount?.doctype === doctype) return;

		cancel_pending_mount();
		const pending = { doctype };
		pending_mount = pending;

		const run = () => {
			if (pending_mount !== pending) return;
			pending_mount = null;
			if (current_doctype() === doctype) mount(doctype, dashboard);
		};

		if (window.requestIdleCallback) {
			pending.idle = requestIdleCallback(run, { timeout: 500 });
		} else {
			pending.timeout = setTimeout(run, 120);
		}
	}

	function sync() {
		const doctype = current_doctype();
		const dashboard = DASHBOARDS[doctype];
		const section = visible_list_section();

		if (!dashboard || !section || !frappe.ui?.mount_island) {
			cancel_pending_mount();
			unmount();
			remove_stale_containers();
			return;
		}

		if (mounted_for === doctype && container && section.contains(container)) return;
		if (pending_mount?.doctype === doctype) return;

		unmount();
		remove_stale_containers();
		schedule_mount(doctype, dashboard);
	}

	function schedule() {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			sync();
		});
	}

	function load_styles() {
		if (document.querySelector('link[href*="nbs_list_stats.css"]')) return;

		const link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = "/assets/nbs_customization/css/nbs_list_stats.css";
		document.head.appendChild(link);
	}

	function init() {
		if (!window.frappe) return;

		load_styles();
		frappe.router?.on?.("change", schedule);
		new MutationObserver(schedule).observe(document.body, {
			childList: true,
			subtree: true,
		});

		[100, 500, 1200, 2500].forEach((delay) => setTimeout(schedule, delay));
		schedule();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
