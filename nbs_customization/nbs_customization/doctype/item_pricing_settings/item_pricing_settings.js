// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

const FIXED_TIER_SET = [
	"Selling - Basic",
	"Selling - 15%",
	"Selling - 30%",
	"Selling - 45%",
	"Selling - Commission",
	"Selling - Commission (Tax)",
];

frappe.ui.form.on("Item Pricing Settings", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.enable_save();
			return;
		}
		frm.disable_save();
		_add_action_buttons(frm);
		_render_price_comparison(frm);
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
	},

	after_save(frm) {
		frm.disable_save();
		_add_action_buttons(frm);
		_render_price_comparison(frm);
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
	},

	validate(frm) {
		_validate_no_duplicate_price_lists(frm);
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
		_render_converted_hints(frm);
	},

	standard_selling_source_tier(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	price_list(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	price_list_target_commission(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	price_list_target_commission_tax(frm) {
		if (!frm.is_new()) {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	manual_cost_mode(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		// Hybrid: auto-clear hidden branch with confirm
		if (frm.doc.pricing_mode !== "Manual") return;
		if (frm.doc.manual_cost_mode === "Override") {
			const hasBreakdown =
				flt(frm.doc.estimated_base_rate) ||
				flt(frm.doc.manual_bank_charges) ||
				flt(frm.doc.manual_freight) ||
				flt(frm.doc.manual_clearing_fees) ||
				flt(frm.doc.manual_transport_in) ||
				flt(frm.doc.manual_transport_out) ||
				flt(frm.doc.manual_overhead) ||
				flt(frm.doc.manual_fixed_cost);
			if (hasBreakdown) {
				frappe.confirm(__("Switching to Override will clear breakdown totals and base rate. Continue?"), () => {
					frm.set_value("estimated_base_rate", 0);
					frm.set_value("manual_bank_charges", 0);
					frm.set_value("manual_freight", 0);
					frm.set_value("manual_clearing_fees", 0);
					frm.set_value("manual_transport_in", 0);
					frm.set_value("manual_transport_out", 0);
					frm.set_value("manual_overhead", 0);
					frm.set_value("manual_fixed_cost", 0);
				}, () => {
					frm.set_value("manual_cost_mode", "Breakdown");
				});
			}
		} else if (frm.doc.manual_cost_mode === "Breakdown") {
			if (flt(frm.doc.estimated_true_cost_override)) {
				frappe.confirm(__("Switching to Breakdown will clear True Cost Override. Continue?"), () => {
					frm.set_value("estimated_true_cost_override", 0);
				}, () => {
					frm.set_value("manual_cost_mode", "Override");
				});
			}
		}
	},

	estimated_base_rate(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	manual_qty(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	estimated_true_cost_override(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		// Y fallback: if user types override while in Breakdown, auto-switch to Override with confirm
		if (flt(frm.doc.estimated_true_cost_override) && frm.doc.manual_cost_mode === "Breakdown") {
			frappe.confirm(__("True Cost Override filled while in Breakdown mode. Switch to Override mode and hide breakdown?"), () => {
				frm.set_value("manual_cost_mode", "Override");
			});
		}
	},

	manual_bank_charges(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_bank_charges) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_freight(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_freight) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_clearing_fees(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_clearing_fees) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_transport_in(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_transport_in) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_transport_out(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_transport_out) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_overhead(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_overhead) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	manual_fixed_cost(frm) {
		_render_manual_totals_helper(frm);
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_fixed_cost) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
		}
	},

	cost_currency(frm) {
		if (frm.doc.pricing_mode !== "Manual") return;
		if (!frm.doc.cost_currency || !frm.doc.company_currency) {
			_render_converted_hints(frm);
			return;
		}
		if (frm.doc.cost_currency === frm.doc.company_currency) {
			frm.set_value("exchange_rate", 1);
			_render_converted_hints(frm);
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.get_fx_rate",
			args: {
				from_currency: frm.doc.cost_currency,
				to_currency: frm.doc.company_currency,
				date: frm.doc.exchange_rate_date || frappe.datetime.get_today(),
			},
			callback(r) {
				if (r.message) frm.set_value("exchange_rate", r.message);
				_render_converted_hints(frm);
			},
		});
	},

	exchange_rate(frm) {
		_render_converted_hints(frm);
		_render_manual_totals_helper(frm);
	},

	exchange_rate_date(frm) {
		if (frm.doc.pricing_mode !== "Manual") return;
		frm.trigger("cost_currency");
	},

	company_currency(frm) {
		frm.trigger("cost_currency");
	},

	// Convert checkboxes
	convert_estimated_base_rate(frm) {
		_render_converted_hints(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save();
	},
	convert_manual_bank_charges(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_freight(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_clearing_fees(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_transport_in(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_transport_out(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_overhead(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_manual_fixed_cost(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
	convert_estimated_true_cost_override(frm) { _render_converted_hints(frm); if (!frm.is_new() && frm.doc.pricing_mode === "Manual") frm.enable_save(); },
});

function _add_action_buttons(frm) {
	const needsRefresh = !frm.doc.last_updated || new Date(frm.doc.modified) > new Date(frm.doc.last_updated);

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

function _validate_no_duplicate_price_lists(frm) {
	const lists = [
		["Price List — Target Margin", frm.doc.price_list],
		["Price List — Target Commission", frm.doc.price_list_target_commission],
		["Price List — Target Commission (Tax)", frm.doc.price_list_target_commission_tax],
	];
	const seen = {};
	for (const [label, name] of lists) {
		if (!name) continue;
		if (FIXED_TIER_SET.includes(name)) {
			frappe.msgprint({
				title: __("Invalid Price List"),
				message: __("Price List {0} for {1} cannot be one of the 6 fixed tier lists.").format(name, label),
				indicator: "red",
			});
			frappe.validated = false;
			return false;
		}
		if (seen[name]) {
			frappe.msgprint({
				title: __("Duplicate Price List"),
				message: __("Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists.", [name, seen[name], label]),
				indicator: "red",
			});
			frappe.validated = false;
			return false;
		}
		seen[name] = label;
	}
	return true;
}

function _show_preview(frm) {
	const d = frm.doc;
	const hasTarget = flt(d.target_margin_pct) && d.price_list;
	const hasTC = flt(d.commission_pct) && d.price_list_target_commission;
	const hasTCT = flt(d.wht_pct) && d.price_list_target_commission_tax;
	const target_label = `Target (${flt(d.target_margin_pct) || 0}%)`;
	const target_is_source = (d.standard_selling_source_tier || "30%") === "Target";
	const tc_label = `Target Commission (${flt(d.commission_pct) || 0}%)`;
	const tct_label = `Target Commission (Tax) (${flt(d.commission_pct) || 0}%+${flt(d.wht_pct) || 0}%)`;
	const tc_is_source = (d.standard_selling_source_tier || "30%") === "Target Commission";
	const tct_is_source = (d.standard_selling_source_tier || "30%") === "Target Commission (Tax)";
	const rows = [
		["Basic (0%)", d.basic_rate, d.price_list_basic],
		["15%", d.rate_15, d.price_list_15],
		["30%", d.rate_30, d.price_list_30 || "Selling - 30%"],
		["45%", d.rate_45, d.price_list_45],
		["Commission (10%)", d.rate_commission, d.price_list_commission || "Selling - Commission"],
		["Commission + Tax (10%+3%)", d.rate_commission_tax, d.price_list_commission_tax || "Selling - Commission (Tax)"],
	];
	if (hasTarget) rows.splice(1, 0, [target_label + (target_is_source ? " → Standard Selling" : ""), d.target_rate, d.price_list]);
	if (hasTC) rows.push([tc_label + (tc_is_source ? " → Standard Selling" : ""), d.rate_target_commission, d.price_list_target_commission]);
	if (hasTCT) rows.push([tct_label + (tct_is_source ? " → Standard Selling" : ""), d.rate_target_commission_tax, d.price_list_target_commission_tax]);
	const current = flt(d.current_selling_price);
	let html = `<div style="max-height:420px;overflow:auto;"><table class="table table-bordered small" style="min-width:720px;">
		<thead><tr><th>Tier</th><th>Price List</th><th class="text-right">Rate (Company: ${d.company_currency || ""})</th><th>vs Current</th></tr></thead><tbody>`;
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
	html += `<div class="text-muted small">Standard Selling source: <b>${d.standard_selling_source_tier || "30%"}</b> → Suggested ${format_currency(d.suggested_selling_price)} | Current ${format_currency(current)} | Mode ${d.pricing_mode} · All prices in Company Currency (${d.company_currency || ""})</div></div>`;

	const preview = new frappe.ui.Dialog({
		title: __("Tier Preview — ") + d.item_code,
		size: "extra-large",
		indicator: "blue",
	});
	preview.$body.html(html);
	preview.show();
}

function _show_apply_dialog(frm) {
	const hasTarget = flt(frm.doc.target_margin_pct) && frm.doc.price_list;
	const hasTC = flt(frm.doc.commission_pct) && frm.doc.price_list_target_commission;
	const hasTCT = flt(frm.doc.wht_pct) && frm.doc.price_list_target_commission_tax;
	const target_label = `Target (${flt(frm.doc.target_margin_pct) || 0}%)`;
	const tc_label = `Target Commission (${flt(frm.doc.commission_pct) || 0}%)`;
	const tct_label = `Target Commission (Tax) (${flt(frm.doc.commission_pct) || 0}%+${flt(frm.doc.wht_pct) || 0}%)`;
	const fields = [
		{ fieldname: "info", fieldtype: "HTML", options: `<div class="text-muted small">Standard Selling will be set from <b>${frm.doc.standard_selling_source_tier || "30%"}</b> (${format_currency(frm.doc.suggested_selling_price)}) in <b>${frm.doc.company_currency || ""}</b>. Choose tiers to create/update Item Price rows. History kept via <code>valid_from</code>. 6 fixed tiers are always available; targets appear only when % + Price List are set. All prices in Company Currency.</div>` },
		{ fieldname: "tier_basic", fieldtype: "Check", label: __("Basic (") + format_currency(frm.doc.basic_rate) + " → " + (frm.doc.price_list_basic || "Selling - Basic") + ")" },
		{ fieldname: "tier_15", fieldtype: "Check", label: __("15% (") + format_currency(frm.doc.rate_15) + " → " + (frm.doc.price_list_15 || "Selling - 15%") + ")" },
		{ fieldname: "tier_30", fieldtype: "Check", label: __("30% (") + format_currency(frm.doc.rate_30) + " → " + (frm.doc.price_list_30 || "Selling - 30%") + ")" },
		{ fieldname: "tier_45", fieldtype: "Check", label: __("45% (") + format_currency(frm.doc.rate_45) + " → " + (frm.doc.price_list_45 || "Selling - 45%") + ")" },
		{ fieldname: "tier_commission", fieldtype: "Check", label: __("Commission (10%) (") + format_currency(frm.doc.rate_commission) + " → " + (frm.doc.price_list_commission || "Selling - Commission") + ")" },
		{ fieldname: "tier_commission_tax", fieldtype: "Check", label: __("Commission + Tax (10%+3%) (") + format_currency(frm.doc.rate_commission_tax) + " → " + (frm.doc.price_list_commission_tax || "Selling - Commission (Tax)") + ")" },
	];
	if (hasTarget) fields.push({ fieldname: "tier_target", fieldtype: "Check", label: __(target_label + " (") + format_currency(frm.doc.target_rate) + " → " + frm.doc.price_list + ")", default: 1 });
	if (hasTC) fields.push({ fieldname: "tier_target_commission", fieldtype: "Check", label: __(tc_label + " (") + format_currency(frm.doc.rate_target_commission) + " → " + frm.doc.price_list_target_commission + ")" });
	if (hasTCT) fields.push({ fieldname: "tier_target_commission_tax", fieldtype: "Check", label: __(tct_label + " (") + format_currency(frm.doc.rate_target_commission_tax) + " → " + frm.doc.price_list_target_commission_tax + ")" });

	const d = new frappe.ui.Dialog({
		title: __("Apply Tier Prices — ") + frm.doc.item_code,
		size: "extra-large",
		fields: fields,
		primary_action_label: __("Apply Selected"),
		primary_action(values) {
			const map = { tier_basic: "basic", tier_target: "target", tier_15: "15", tier_30: "30", tier_45: "45", tier_commission: "commission", tier_commission_tax: "commission_tax", tier_target_commission: "target_commission", tier_target_commission_tax: "target_commission_tax" };
			const selected = [];
			for (const [fld, key] of Object.entries(map)) if (values[fld]) selected.push(key);
			if (!selected.length) {
				frappe.msgprint(__("Select at least one tier."));
				return;
			}
			// duplicate check (only optionals can collide, fixed are distinct)
			const pl_map = {
				basic: frm.doc.price_list_basic || "Selling - Basic",
				"15": frm.doc.price_list_15 || "Selling - 15%",
				"30": frm.doc.price_list_30 || "Selling - 30%",
				"45": frm.doc.price_list_45 || "Selling - 45%",
				commission: frm.doc.price_list_commission || "Selling - Commission",
				commission_tax: frm.doc.price_list_commission_tax || "Selling - Commission (Tax)",
				target: frm.doc.price_list || "",
				target_commission: frm.doc.price_list_target_commission || "",
				target_commission_tax: frm.doc.price_list_target_commission_tax || "",
			};
			const seen = {};
			for (const k of selected) {
				const pl = pl_map[k];
				if (!pl) continue;
				if (FIXED_TIER_SET.includes(pl) && ["target", "target_commission", "target_commission_tax"].includes(k)) {
					frappe.msgprint({title: __("Invalid Price List"), message: __("Price List {0} for {1} cannot be one of the 6 fixed tier lists.").format(pl, k), indicator: "red"});
					return;
				}
				if (seen[pl]) {
					frappe.msgprint({title: __("Duplicate Price List"), message: __("Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists.", [pl, seen[pl], k]), indicator: "red"});
					return;
				}
				seen[pl] = k;
			}
			if (seen["Standard Selling"]) {
				frappe.msgprint({title: __("Duplicate Price List"), message: __("Price List {0} is used for both {1} and Standard Selling. Please choose distinct Price Lists.", ["Standard Selling", seen["Standard Selling"]]), indicator: "red"});
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
	const all = ["basic", "15", "30", "45", "commission", "commission_tax"];
	if (hasTarget) all.push("target");
	if (hasTC) all.push("target_commission");
	if (hasTCT) all.push("target_commission_tax");
	d.set_secondary_action(() => {
		// duplicate check for All
		const all_pl_map = {
			basic: frm.doc.price_list_basic || "Selling - Basic",
			"15": frm.doc.price_list_15 || "Selling - 15%",
			"30": frm.doc.price_list_30 || "Selling - 30%",
			"45": frm.doc.price_list_45 || "Selling - 45%",
			commission: frm.doc.price_list_commission || "Selling - Commission",
			commission_tax: frm.doc.price_list_commission_tax || "Selling - Commission (Tax)",
			target: frm.doc.price_list || "",
			target_commission: frm.doc.price_list_target_commission || "",
			target_commission_tax: frm.doc.price_list_target_commission_tax || "",
		};
		const all_seen = {};
		for (const k of all) {
			const pl = all_pl_map[k];
			if (!pl) continue;
			if (all_seen[pl]) {
				frappe.msgprint({title: __("Duplicate Price List"), message: __("Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists.", [pl, all_seen[pl], k]), indicator: "red"});
				return;
			}
			all_seen[pl] = k;
		}
		if (all_seen["Standard Selling"]) {
			frappe.msgprint({title: __("Duplicate Price List"), message: __("Price List {0} is used for both {1} and Standard Selling. Please choose distinct Price Lists.", ["Standard Selling", all_seen["Standard Selling"]]), indicator: "red"});
			return;
		}
		frappe.confirm(__("Apply ALL {0} tiers?", [all.length]), () => {
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
	d.get_secondary_btn().text(__("Apply All {0}", [all.length]));
	d.show();
}

function _render_manual_totals_helper(frm) {
	if (frm.doc.pricing_mode !== "Manual") {
		frm.get_field("manual_true_cost").$wrapper.find(".manual-totals-hint").remove();
		return;
	}
	const field = frm.get_field("manual_true_cost");
	if (!field) return;
	field.$wrapper.find(".manual-totals-hint").remove();
	const qty = flt(frm.doc.manual_qty) || 1;
	const rate = flt(frm.doc.exchange_rate) || 1;
	const isFX = frm.doc.cost_currency && frm.doc.company_currency && frm.doc.cost_currency !== frm.doc.company_currency;

	function converted(val, doConvert) {
		if (!isFX || !doConvert) return flt(val, 2);
		return flt(val * rate, 2);
	}
	// Build display totals in Company currency
	if (flt(frm.doc.estimated_true_cost_override)) {
		const raw = flt(frm.doc.estimated_true_cost_override);
		const conv = converted(raw, frm.doc.convert_estimated_true_cost_override);
		const per = conv / qty;
		const hint = `<div class="manual-totals-hint text-muted small" style="margin-top:6px;">Override total ${format_currency(raw)} ${frm.doc.cost_currency || ""} ${frm.doc.convert_estimated_true_cost_override ? `→ ${format_currency(conv)} ${frm.doc.company_currency || ""}` : ""} for ${qty} units → <b>${format_currency(per)} / unit (${frm.doc.company_currency || ""})</b></div>`;
		field.$wrapper.find(".control-value").after(hint);
		return;
	}

	const baseRaw = flt(frm.doc.estimated_base_rate) * qty;
	const baseConv = converted(flt(frm.doc.estimated_base_rate), frm.doc.convert_estimated_base_rate) * qty;
	const fixedRaw = flt(frm.doc.manual_fixed_cost) * qty;
	const fixedConv = converted(flt(frm.doc.manual_fixed_cost), frm.doc.convert_manual_fixed_cost) * qty;
	let otherRaw = flt(frm.doc.manual_bank_charges) + flt(frm.doc.manual_freight) + flt(frm.doc.manual_clearing_fees) + flt(frm.doc.manual_transport_in) + flt(frm.doc.manual_transport_out) + flt(frm.doc.manual_overhead);
	let otherConv = converted(flt(frm.doc.manual_bank_charges), frm.doc.convert_manual_bank_charges) + converted(flt(frm.doc.manual_freight), frm.doc.convert_manual_freight) + converted(flt(frm.doc.manual_clearing_fees), frm.doc.convert_manual_clearing_fees) + converted(flt(frm.doc.manual_transport_in), frm.doc.convert_manual_transport_in) + converted(flt(frm.doc.manual_transport_out), frm.doc.convert_manual_transport_out) + converted(flt(frm.doc.manual_overhead), frm.doc.convert_manual_overhead);
	const totalsConv = otherConv + fixedConv;
	const trueTotal = baseConv + totalsConv;
	const truePer = trueTotal / qty;

	if (!baseRaw && !otherRaw && !fixedRaw) return;

	const parts = [];
	if (flt(frm.doc.manual_bank_charges)) parts.push(`Bank ${format_currency(converted(flt(frm.doc.manual_bank_charges), frm.doc.convert_manual_bank_charges))}/u ${frm.doc.convert_manual_bank_charges ? '('+frm.doc.cost_currency+')' : ''}`);
	if (flt(frm.doc.manual_freight)) parts.push(`Freight ${format_currency(converted(flt(frm.doc.manual_freight), frm.doc.convert_manual_freight))}/u`);
	if (flt(frm.doc.manual_clearing_fees)) parts.push(`Clearing ${format_currency(converted(flt(frm.doc.manual_clearing_fees), frm.doc.convert_manual_clearing_fees))}/u`);
	if (flt(frm.doc.manual_transport_in)) parts.push(`Tin ${format_currency(converted(flt(frm.doc.manual_transport_in), frm.doc.convert_manual_transport_in))}/u`);
	if (flt(frm.doc.manual_transport_out)) parts.push(`Tout ${format_currency(converted(flt(frm.doc.manual_transport_out), frm.doc.convert_manual_transport_out))}/u`);
	if (flt(frm.doc.manual_overhead)) parts.push(`Overhead ${format_currency(converted(flt(frm.doc.manual_overhead), frm.doc.convert_manual_overhead))}/u`);
	if (flt(frm.doc.manual_fixed_cost)) parts.push(`Fixed ${format_currency(converted(flt(frm.doc.manual_fixed_cost), frm.doc.convert_manual_fixed_cost))}/u`);

	const detail = parts.length ? ` · ${parts.join(" · ")}` : "";
	const fxInfo = isFX ? ` (Rate ${rate} ${frm.doc.cost_currency}→${frm.doc.company_currency})` : "";
	const hint = `<div class="manual-totals-hint text-muted small" style="margin-top:6px;">Base ${format_currency(baseConv)} + shared ${format_currency(totalsConv)} = total ${format_currency(trueTotal)} for ${qty} units → <b>${format_currency(truePer)} / unit (${frm.doc.company_currency || ""})</b>${fxInfo}<span class="text-muted">${detail}</span></div>`;
	field.$wrapper.find(".control-value").after(hint);
}

function _render_converted_hints(frm) {
	if (frm.doc.pricing_mode !== "Manual") return;
	const isFX = frm.doc.cost_currency && frm.doc.company_currency && frm.doc.cost_currency !== frm.doc.company_currency;
	const rate = flt(frm.doc.exchange_rate) || 1;
	const fields = [
		["estimated_base_rate", "convert_estimated_base_rate"],
		["manual_bank_charges", "convert_manual_bank_charges"],
		["manual_freight", "convert_manual_freight"],
		["manual_clearing_fees", "convert_manual_clearing_fees"],
		["manual_transport_in", "convert_manual_transport_in"],
		["manual_transport_out", "convert_manual_transport_out"],
		["manual_overhead", "convert_manual_overhead"],
		["manual_fixed_cost", "convert_manual_fixed_cost"],
		["estimated_true_cost_override", "convert_estimated_true_cost_override"],
	];
	for (const [field, convField] of fields) {
		const fld = frm.get_field(field);
		if (!fld) continue;
		fld.$wrapper.find(".converted-hint").remove();
		const val = flt(frm.doc[field]);
		if (!val || !isFX) continue;
		const doConvert = frm.doc[convField];
		if (doConvert) {
			const conv = flt(val * rate, 2);
			const hint = `<div class="converted-hint text-muted small" style="margin-top:2px;">${format_currency(val)} ${frm.doc.cost_currency} → <b>${format_currency(conv)} ${frm.doc.company_currency}</b> @ ${rate}</div>`;
			fld.$wrapper.find(".control-value").after(hint);
		} else {
			const hint = `<div class="converted-hint text-muted small" style="margin-top:2px;">${format_currency(val)} ${frm.doc.company_currency} (no convert)</div>`;
			fld.$wrapper.find(".control-value").after(hint);
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
			const tgt = flt(frm.doc.target_rate) ? `Target ${format_currency(frm.doc.target_rate)} · ` : "";
			const tc = flt(frm.doc.rate_target_commission) ? `TComm ${format_currency(frm.doc.rate_target_commission)} · TComm+Tax ${format_currency(frm.doc.rate_target_commission_tax)} · ` : "";
			tier.$wrapper.append(`<div class="tier-lane text-muted small" style="margin-top:4px;">Basic ${format_currency(frm.doc.basic_rate)} · ${tgt}15% ${format_currency(frm.doc.rate_15)} · 30% ${format_currency(frm.doc.rate_30)} · 45% ${format_currency(frm.doc.rate_45)} · Comm10% ${format_currency(frm.doc.rate_commission)} · Comm10+3% ${format_currency(frm.doc.rate_commission_tax)} · ${tc}Final ${format_currency(frm.doc.final_rate_per_unit)} (${frm.doc.company_currency || ""})</div>`);
		}
	}
}
