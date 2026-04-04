// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Pricing Settings", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.enable_save();
			return;
		}

		frm.disable_save();
		_add_action_buttons(frm);
		_render_price_comparison(frm);
	},

	after_save(frm) {
		// After saving, switch to action-button mode immediately
		frm.disable_save();
		_add_action_buttons(frm);
		_render_price_comparison(frm);
	},

	target_margin_pct(frm) {
		if (!frm.is_new()) {
			frm.enable_save();

			frm.clear_custom_buttons();
		}
	},
});

function _add_action_buttons(frm) {
	const needsRefresh =
		!frm.doc.last_updated || new Date(frm.doc.modified) > new Date(frm.doc.last_updated);

	const $refresh = frm.add_custom_button(__("Refresh Valuation"), () => {
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.refresh_valuation",
			args: { doc_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Reading latest valuation rate..."),
			callback(r) {
				if (!r.exc) {
					frm.reload_doc();
				}
			},
		});
	});

	if (needsRefresh) {
		$refresh.removeClass("btn-default").addClass("btn-primary");
	}

	if (flt(frm.doc.suggested_selling_price) > 0) {
		const current = flt(frm.doc.current_selling_price);
		const suggested = flt(frm.doc.suggested_selling_price);
		const changed = current !== suggested;

		const $btn = frm.add_custom_button(__("Apply Suggested Price"), () => {
			const msg = changed
				? __(
						"This will update the selling price from <b>{0}</b> to <b>{1}</b> under <b>{2}</b>. Continue?",
						[format_currency(current), format_currency(suggested), frm.doc.price_list],
					)
				: __("The suggested price matches the current selling price. Apply anyway?");

			frappe.confirm(msg, () => {
				frappe.call({
					method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.apply_suggested_price",
					args: { doc_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Updating Item Price..."),
					callback(r) {
						if (!r.exc) {
							frm.reload_doc();
						}
					},
				});
			});
		});
		if (changed) {
			$btn.removeClass("btn-default").addClass("btn-primary");
		}
	}
}

function _render_price_comparison(frm) {
	frm.get_field("suggested_selling_price").$wrapper.find(".price-comparison-hint").remove();

	const current = flt(frm.doc.current_selling_price);
	const suggested = flt(frm.doc.suggested_selling_price);

	if (!suggested) return;

	let hint_html = "";

	if (!current) {
		hint_html = `<span class="price-comparison-hint text-muted small">
			No selling price set yet for this item.
		</span>`;
	} else if (suggested > current) {
		const diff = flt(suggested - current, 2);
		const pct = flt(((suggested - current) / current) * 100, 1);
		hint_html = `<span class="price-comparison-hint" style="color: var(--orange-500); font-size: 12px;">
			▲ ${pct}% above current price (current: ${format_currency(current)}, difference: ${format_currency(diff)})
		</span>`;
	} else if (suggested < current) {
		const diff = flt(current - suggested, 2);
		const pct = flt(((current - suggested) / current) * 100, 1);
		hint_html = `<span class="price-comparison-hint" style="color: var(--green-500); font-size: 12px;">
			▼ ${pct}% below current price (current: ${format_currency(current)}, difference: ${format_currency(diff)})
		</span>`;
	} else {
		hint_html = `<span class="price-comparison-hint" style="color: var(--gray-500); font-size: 12px;">
			✓ Matches current selling price
		</span>`;
	}

	frm.get_field("suggested_selling_price").$wrapper.find(".control-value").after(hint_html);
}
