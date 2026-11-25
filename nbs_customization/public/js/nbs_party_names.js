/**
 * NBS Customization — nbs_party_names.js
 *
 * Shows current Customer and Supplier names where Insights renders their IDs.
 *
 * The underlying rows keep the ID: it is what dashboard filters, drill-down,
 * sorting and record links use. Only the visible text is swapped.
 */

(function () {
	const CACHE = new Map();
	let pattern = null;
	let loading = null;

	function escape(value) {
		return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	}

	function buildPattern() {
		const ids = [...CACHE.keys()].sort((a, b) => b.length - a.length);
		pattern = ids.length
			? new RegExp(
					`(?<![A-Za-z0-9_-])(?:${ids.map(escape).join("|")})(?![A-Za-z0-9_-])`,
					"g"
			  )
			: null;
	}

	function load() {
		if (loading) return loading;
		if (typeof frappe === "undefined") return Promise.resolve(false);

		loading = frappe
			.xcall("nbs_customization.api.get_party_names")
			.then((names) => {
				Object.entries(names || {}).forEach(([id, name]) => {
					if (name && name !== id) CACHE.set(id, name);
				});
				buildPattern();
				return CACHE.size > 0;
			})
			.catch(() => false);

		return loading;
	}

	function fitSvgLabel(text, value) {
		const match = /translate\(([-\d.]+)/.exec(text.getAttribute("transform") || "");
		if (!match || text.getAttribute("text-anchor") !== "end") return;

		const available = Math.max(0, Number(match[1]) - 8);
		if (!available || text.getComputedTextLength() <= available) return;

		text.setAttribute("aria-label", value);
		let low = 0;
		let high = value.length;
		let best = "…";

		while (low <= high) {
			const middle = (low + high) >> 1;
			const candidate = value.slice(0, middle).trimEnd() + "…";
			text.textContent = candidate;
			if (text.getComputedTextLength() <= available) {
				best = candidate;
				low = middle + 1;
			} else {
				high = middle - 1;
			}
		}

		text.textContent = best;
	}

	function replace(node) {
		if (!pattern || !node.nodeValue) return;

		const next = node.nodeValue.replace(pattern, (id) => CACHE.get(id) || id);
		if (next === node.nodeValue) return;

		node.nodeValue = next;
		const svgText = node.parentElement?.closest("text");
		if (svgText) fitSvgLabel(svgText, next.trim());
	}

	function apply(root) {
		if (!root || !pattern) return;

		const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
			acceptNode(node) {
				const parent = node.parentElement;
				if (!parent) return NodeFilter.FILTER_REJECT;
				if (parent.closest("style, script, noscript, textarea")) {
					return NodeFilter.FILTER_REJECT;
				}
				return NodeFilter.FILTER_ACCEPT;
			},
		});

		const nodes = [];
		while (walker.nextNode()) nodes.push(walker.currentNode);
		nodes.forEach(replace);
	}

	window.NBSPartyNames = { load, apply };
})();
