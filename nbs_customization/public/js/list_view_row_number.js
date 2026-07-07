/**
 * NBS Customization: Add row number ("No.") column to all List Views.
 * Patches at the HTML-output level with stable regex anchors.
 */
(function () {
	const patch_list_view = () => {
		if (!window.frappe || !frappe.views || !frappe.views.ListView) {
			return false;
		}
		if (frappe.views.ListView.prototype._row_number_patched) return true;

		frappe.views.ListView.prototype._row_number_patched = true;

		// 1. Inject "No." into the header Subject column, after the checkbox<span>
		const _get_header_html = frappe.views.ListView.prototype.get_header_html;
		frappe.views.ListView.prototype.get_header_html = function () {
			const html = _get_header_html.apply(this, arguments);
			if (!html) return html;
			// Anchors on the unique header-checkbox class
			return html.replace(
				/(<input\s+class="list-header-checkbox\s+list-check-all"[^>]*>\s*<\/span>)/,
				"$1" + `<span class="nbs-row-no nbs-row-no-header">${__("No.")}</span>`,
			);
		};

		// 2. Inject row number into each body-row Subject column, after the checkbox<span>
		const _get_column_html = frappe.views.ListView.prototype.get_column_html;
		frappe.views.ListView.prototype.get_column_html = function (col, doc, show_in_mobile) {
			const html = _get_column_html.apply(this, arguments);
			if (col.type === "Subject" && html) {
				const row_no = (doc._idx !== undefined ? doc._idx : 0) + 1;
				// Anchors on type=checkbox (each Subject column has exactly one)
				return html.replace(
					/(<input[^>]*type="checkbox"[^>]*>\s*<\/span>)/,
					"$1" + `<span class="nbs-row-no">${row_no}</span>`,
				);
			}
			return html;
		};

		return true;
	};

	if (!patch_list_view()) {
		const interval = setInterval(() => {
			if (patch_list_view()) clearInterval(interval);
		}, 500);
		setTimeout(() => clearInterval(interval), 30000);
	}
})();
