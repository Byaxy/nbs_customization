/**
 * NBS Customization — nbs_status.js
 *
 * Adds status-specific tones to framework status badges so lifecycle and
 * workflow states do not all share the same red/amber/gray shade.
 */

(() => {
	if (window.NBSStatusLoaded) return;
	window.NBSStatusLoaded = true;

	const STATUS_BADGE_SELECTOR = [
		".list-row-col[data-fieldname='status_field'] .es-badge",
		".list-row-col[data-fieldname$='_status'] .es-badge",
		".list-row-col[data-fieldname='status'] .es-badge",
		".list-row-col[data-fieldname='custom_waybill_type'] .es-badge",
		".list-row-col[data-fieldname='payment_type'] .es-badge",
		".page-indicator-pill",
		".side-panel-indicator .es-badge",
		".embedded-list .es-badge",
		".datatable .es-badge.filterable",
		".indicator-pill",
		".indicator-pill-right",
	].join(",");

	const DOCSTATUS_TONES = {
		0: "gray",
		1: "blue",
		2: "red-dark",
	};

	const LIFECYCLE_TONES = {
		draft: "gray",
		cancelled: "red-dark",
		canceled: "red-dark",
		overdue: "red",
	};

	const FIELD_TONES = {
		promissory_note_status: {
			pending: "amber",
			"partially fulfilled": "blue",
			fulfilled: "green",
		},
		payment_status: {
			pending: "amber",
			partial: "blue",
			paid: "green",
			cancelled: "red-dark",
		},
		shipment_status: {
			pending: "amber",
			"in transit": "blue",
			delivered: "green",
			cancelled: "red-dark",
		},
		conversion_status: {
			draft: "gray",
			pending: "amber",
			"partially converted": "blue",
			"fully converted": "green",
			cancelled: "red-dark",
		},
		reconciliation_status: {
			draft: "gray",
			verified: "green",
			invoiced: "blue",
			closed: "gray",
		},
		benchmark_status: {
			"below tolerance": "red",
			"within tolerance": "green",
			"at or above outright": "blue",
		},
		custom_waybill_type: {
			"regular waybill": "green",
			"loan conversion waybill": "blue",
		},
		payment_type: {
			receive: "green",
			pay: "red",
			"internal transfer": "blue",
		},
	};

	function normalize(value) {
		return (value || "").trim().toLowerCase();
	}

	function parseFilter(value) {
		if (!value) return null;
		const [fieldname, _operator, ...rest] = value.split(",");
		return { fieldname, value: rest.join(",") };
	}

	function toneForFilter(fieldname, value) {
		if (fieldname === "docstatus") {
			return DOCSTATUS_TONES[value];
		}

		const field_tones = FIELD_TONES[fieldname];
		if (field_tones) {
			return field_tones[normalize(value)];
		}

		if (fieldname === "status" || fieldname === "status_field") {
			return LIFECYCLE_TONES[normalize(value)];
		}
	}

	function labelOf(el) {
		const label = el.querySelector(".es-badge__label");
		return (label || el).textContent || "";
	}

	function toneFor(el) {
		const filter = parseFilter(el.getAttribute("data-filter"));
		const filter_tone = filter && toneForFilter(filter.fieldname, filter.value);
		return filter_tone || LIFECYCLE_TONES[normalize(labelOf(el))];
	}

	function decorate(el) {
		let tone = toneFor(el);

		if (!tone && el.classList.contains("es-badge")) {
			const theme = el.getAttribute("data-theme");
			if (theme === "amber") {
				tone = "amber";
			} else if (!theme || theme === "gray") {
				tone = "gray";
			}
		}

		if (tone) {
			el.dataset.nbsTone = tone;
		} else if (el.dataset.nbsTone) {
			delete el.dataset.nbsTone;
		}
	}

	function decorateAll(root = document) {
		root.querySelectorAll?.(STATUS_BADGE_SELECTOR).forEach(decorate);
	}

	const pending_badges = new Set();
	const schedule_frame =
		window.requestAnimationFrame?.bind(window) || ((callback) => setTimeout(callback, 16));
	let scheduled_frame = 0;

	function findBadge(node) {
		const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
		return el?.closest?.(STATUS_BADGE_SELECTOR);
	}

	function scheduleBadge(node) {
		const badge = findBadge(node);
		if (!badge) return;

		pending_badges.add(badge);
		if (scheduled_frame) return;

		scheduled_frame = schedule_frame(() => {
			scheduled_frame = 0;
			pending_badges.forEach(decorate);
			pending_badges.clear();
		});
	}

	function scheduleBadgeTree(node) {
		if (node.nodeType !== Node.ELEMENT_NODE) return;
		scheduleBadge(node);
		node.querySelectorAll?.(STATUS_BADGE_SELECTOR).forEach(scheduleBadge);
	}

	function setupObserver() {
		if (!window.MutationObserver) return;

		const observer = new MutationObserver((mutations) => {
			mutations.forEach((mutation) => {
				if (mutation.type === "attributes") {
					scheduleBadge(mutation.target);
					return;
				}

				if (mutation.type === "characterData") {
					scheduleBadge(mutation.target.parentElement);
					return;
				}

				scheduleBadge(mutation.target);
				mutation.addedNodes.forEach(scheduleBadgeTree);
			});
		});

		observer.observe(document.body, {
			childList: true,
			subtree: true,
			characterData: true,
			attributes: true,
			attributeFilter: ["data-theme", "data-filter"],
		});
	}

	window.NBSStatus = {
		refresh: () => decorateAll(document),
	};

	function init() {
		decorateAll();
		setupObserver();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
