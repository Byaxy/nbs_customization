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

	commission_pct(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	wht_pct(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	pricing_mode(frm) {
		if (!frm.is_new()) frm.enable_save();
	},

	standard_selling_source_tier(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	quote_currency(frm) {
		if (frm.doc.pricing_mode !== "Manual") return;
		if (!frm.doc.quote_currency || !frm.doc.company_currency) return;
		if (frm.doc.quote_currency === frm.doc.company_currency) {
			frm.set_value("exchange_rate", 1);
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.get_fx_rate",
			args: {
				from_currency: frm.doc.quote_currency,
				to_currency: frm.doc.company_currency,
				date: frm.doc.exchange_rate_date || frappe.datetime.get_today(),
			},
			callback(r) {
				if (r.message) frm.set_value("exchange_rate", r.message);
			},
		});
	},

	exchange_rate_date(frm) {
		if (frm.doc.pricing_mode !== "Manual") return;
		frm.trigger("quote_currency");
	},
});

function _add_action_buttons(frm) {
	const needsRefresh =
		!frm.doc.last_updated || new Date(frm.doc.modified) > new Date(frm.doc.last_updated);

	const isManual = frm.doc.pricing_mode === "Manual";
	const refreshLabel = isManual ? __("Recalculate Estimate") : __("Refresh Valuation");
	const refreshMsg = isManual ? __("Recalculating tiers...") : __("Reading latest valuation rate...");

	const $refresh = frm.add_custom_button(refreshLabel, () => {
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.refresh_valuation",
			args: { doc_name: frm.doc.name },
			freeze: true,
			freeze_message: refreshMsg,
			callback(r) {
				if (!r.exc) frm.reload_doc();
			},
		});
	});

	if (needsRefresh) $refresh.removeClass("btn-default").addClass("btn-primary");

	// Preview tiers dialog
	if (flt(frm.doc.basic_rate) || flt(frm.doc.rate_30) || flt(frm.doc.suggested_selling_price)) {
		frm.add_custom_button(__("Preview Tiers"), () => _show_preview(frm));
	}

	// Apply tiers
	const hasAnyTier = flt(frm.doc.basic_rate) || flt(frm.doc.rate_30) || flt(frm.doc.suggested_selling_price);
	if (hasAnyTier) {
		const current = flt(frm.doc.current_selling_price);
		const suggested = flt(frm.doc.suggested_selling_price);
		const changed = current !== suggested;

		const $btn = frm.add_custom_button(__("Apply Tiers"), () => _show_apply_dialog(frm));
		if (changed) $btn.removeClass("btn-default").addClass("btn-primary");
	}
}

function _show_preview(frm) {
	const d = frm.doc;
	const rows = [
		["Basic (0%)", d.basic_rate, d.price_list_basic],
		["15%", d.rate_15, d.price_list_15],
		["30% → Standard Selling", d.rate_30, d.price_list_30 || "Standard Selling"],
		["45%", d.rate_45, d.price_list_45],
		["Commission", d.rate_commission, d.price_list_commission],
		["Commission + Tax", d.rate_commission_tax, d.price_list_commission_tax],
	];
	const current = flt(d.current_selling_price);
	let html = `<div style="max-height:320px;overflow:auto;"><table class="table table-bordered small">
		<thead><tr><th>Tier</th><th>Price List</th><th class="text-right">Rate</th><th>vs Current</th></tr></thead><tbody>`;
	for (const [label, rate, pl] of rows) {
		const r = flt(rate);
		let delta = "";
		if (r && current) {
			const diff = r - current;
			const pct = current ? ((diff / current) * 100).toFixed(1) : "0";
			if (diff > 0) delta = `<span style="color:var(--orange-500)">▲ ${pct}%</span>`;
			else if (diff < 0) delta = `<span style="color:var(--green-500)">▼ ${pct}%</span>`;
			else delta = `<span style="color:var(--gray-600)">✓ same</span>`;
		}
		const bold = label.includes("Standard Selling") ? "font-weight:600;" : "";
		html += `<tr style="${bold}"><td>${label}</td><td class="text-muted small">${pl || ""}</td><td class="text-right">${r ? format_currency(r) : "-"}</td><td class="text-center">${delta}</td></tr>`;
	}
	html += `</tbody></table>`;
	html += `<div class="text-muted small">Standard Selling source: <b>${d.standard_selling_source_tier || "30%"}</b> → Suggested ${format_currency(d.suggested_selling_price)} | Current ${format_currency(current)} | Mode ${d.pricing_mode}</div></div>`;

	frappe.msgprint({ title: __("Tier Preview — ") + d.item_code, message: html, wide: true });
}

function _show_apply_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Apply Tier Prices — ") + frm.doc.item_code,
		fields: [
			{ fieldname: "info", fieldtype: "HTML", options: `<div class="text-muted small">Standard Selling will be set from <b>${frm.doc.standard_selling_source_tier || "30%"}</b> (${format_currency(frm.doc.suggested_selling_price)}). Choose tiers to create/update Item Price rows. History kept via <code>valid_from</code>.</div>` },
			{ fieldname: "tier_basic", fieldtype: "Check", label: __("Basic (") + format_currency(frm.doc.basic_rate) + " → " + (frm.doc.price_list_basic || "Selling - Basic") + ")" },
			{ fieldname: "tier_15", fieldtype: "Check", label: __("15% (") + format_currency(frm.doc.rate_15) + " → " + (frm.doc.price_list_15 || "Selling - 15%") + ")" },
			{ fieldname: "tier_30", fieldtype: "Check", label: __("30% → Standard Selling (") + format_currency(frm.doc.rate_30) + " → " + (frm.doc.price_list_30 || "Standard Selling") + ")" , default: 1 },
			{ fieldname: "tier_45", fieldtype: "Check", label: __("45% (") + format_currency(frm.doc.rate_45) + " → " + (frm.doc.price_list_45 || "Selling - 45%") + ")" },
			{ fieldname: "tier_commission", fieldtype: "Check", label: __("Commission (") + format_currency(frm.doc.rate_commission) + " → " + (frm.doc.price_list_commission || "Selling - Commission") + ")" },
			{ fieldname: "tier_commission_tax", fieldtype: "Check", label: __("Commission + Tax (") + format_currency(frm.doc.rate_commission_tax) + " → " + (frm.doc.price_list_commission_tax || "Selling - Commission (Tax)") + ")" },
		],
		primary_action_label: __("Apply Selected"),
		primary_action(values) {
			const map = { tier_basic: "basic", tier_15: "15", tier_30: "30", tier_45: "45", tier_commission: "commission", tier_commission_tax: "commission_tax" };
			const selected = [];
			for (const [fld, key] of Object.entries(map)) if (values[fld]) selected.push(key);
			if (!selected.length) {
				frappe.msgprint(__("Select at least one tier."));
				return;
			}
			frappe.confirm(__("Apply {0} tier(s)? This creates/updates Item Price with valid_from=today (history kept).", [selected.length]), () => {
				frappe.call({
					method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.apply_tiers",
					args: { doc_name: frm.doc.name, selected_tiers: selected },
					freeze: true,
					freeze_message: __("Updating Item Prices..."),
					callback(r) {
						if (!r.exc) {
							d.hide();
							frm.reload_doc();
						}
					},
				});
			});
		},
	});
	// default select 30% + maybe all if user wants "Apply All" quickly — keep 30% checked, others unchecked
	// Add Apply All helper
	d.set_secondary_action(() => {
		const all = ["basic", "15", "30", "45", "commission", "commission_tax"];
		frappe.confirm(__("Apply ALL 6 tiers?"), () => {
			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.apply_tiers",
				args: { doc_name: frm.doc.name, selected_tiers: all },
				freeze: true,
				freeze_message: __("Updating Item Prices..."),
				callback(r) {
					if (!r.exc) {
						d.hide();
						frm.reload_doc();
					}
				},
			});
		});
	});
	d.get_secondary_btn().text(__("Apply All 6"));
	d.show();
}

function _render_price_comparison(frm) {
	frm.get_field("suggested_selling_price").$wrapper.find(".price-comparison-hint").remove();
	const current = flt(frm.doc.current_selling_price);
	const suggested = flt(frm.doc.suggested_selling_price);
	if (!suggested) return;
	let hint_html = "";
	if (!current) {
		hint_html = `<span class="price-comparison-hint text-muted small">No selling price yet for Standard Selling.</span>`;
	} else if (suggested > current) {
		const diff = flt(suggested - current, 2);
		const pct = flt(((suggested - current) / current) * 100, 1);
		hint_html = `<span class="price-comparison-hint" style="color: var(--orange-500); font-size: 12px;">▲ ${pct}% above Standard Selling (current: ${format_currency(current)}, diff: ${format_currency(diff)}) — source: ${frm.doc.standard_selling_source_tier || "30%"}</span>`;
	} else if (suggested < current) {
		const diff = flt(current - suggested, 2);
		const pct = flt(((current - suggested) / current) * 100, 1);
		hint_html = `<span class="price-comparison-hint" style="color: var(--green-500); font-size: 12px;">▼ ${pct}% below Standard Selling (current: ${format_currency(current)}, diff: ${format_currency(diff)}) — source: ${frm.doc.standard_selling_source_tier || "30%"}</span>`;
	} else {
		hint_html = `<span class="price-comparison-hint" style="color: var(--gray-500); font-size: 12px;">✓ Matches Standard Selling</span>`;
	}
	frm.get_field("suggested_selling_price").$wrapper.find(".control-value").after(hint_html);

	// tier quick lane (minimal)
	const tier = frm.get_field("final_rate_per_unit");
	if (tier) {
		tier.$wrapper.find(".tier-lane").remove();
		if (flt(frm.doc.final_rate_per_unit)) {
			tier.$wrapper.append(`<div class="tier-lane text-muted small" style="margin-top:4px;">Basic ${format_currency(frm.doc.basic_rate)} · 15% ${format_currency(frm.doc.rate_15)} · 30% ${format_currency(frm.doc.rate_30)} · 45% ${format_currency(frm.doc.rate_45)} · Comm ${format_currency(frm.doc.rate_commission)} · Comm+Tax ${format_currency(frm.doc.rate_commission_tax)}</div>`);
		}
	}
}
