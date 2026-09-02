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
		_render_manual_totals_helper(frm);
	},

	after_save(frm) {
		frm.disable_save();
		_add_action_buttons(frm);
		_render_price_comparison(frm);
		_render_manual_totals_helper(frm);
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
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		// Hybrid: auto-clear hidden branch with confirm
		if (frm.doc.pricing_mode !== "Manual") return;
		if (frm.doc.manual_cost_mode === "Override") {
			const hasBreakdown = flt(frm.doc.estimated_base_rate) || flt(frm.doc.manual_bank_charges) || flt(frm.doc.manual_freight) || flt(frm.doc.manual_clearing_fees) || flt(frm.doc.manual_transport_in) || flt(frm.doc.manual_transport_out) || flt(frm.doc.manual_overhead) || flt(frm.doc.manual_fixed_cost);
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
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	manual_qty(frm) {
		_render_manual_totals_helper(frm);
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
	},

	estimated_true_cost_override(frm) {
		_render_manual_totals_helper(frm);
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
		if (!frm.is_new() && frm.doc.pricing_mode === "Manual") {
			frm.enable_save();
			frm.clear_custom_buttons();
		}
		if (flt(frm.doc.manual_fixed_cost) && frm.doc.manual_cost_mode === "Override") {
			frappe.confirm(__("Breakdown total entered while in Override mode. Switch to Breakdown?"), () => frm.set_value("manual_cost_mode", "Breakdown"));
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
	const target_label = `Target (${flt(d.target_margin_pct) || 0}%)`;
	const target_is_source = (d.standard_selling_source_tier || "30%") === "Target";
	const tc_label = `Target Commission (${flt(d.commission_pct) || 0}%)`;
	const tct_label = `Target Commission (Tax) (${flt(d.commission_pct) || 0}%+${flt(d.wht_pct) || 0}%)`;
	const tc_is_source = (d.standard_selling_source_tier || "30%") === "Target Commission";
	const tct_is_source = (d.standard_selling_source_tier || "30%") === "Target Commission (Tax)";
	const rows = [
		["Basic (0%)", d.basic_rate, d.price_list_basic],
		[target_label + (target_is_source ? " → Standard Selling" : ""), d.target_rate, d.price_list || "Standard Selling"],
		["15%", d.rate_15, d.price_list_15],
		["30%", d.rate_30, d.price_list_30 || "Selling - 30%"],
		["45%", d.rate_45, d.price_list_45],
		["Commission (10%)", d.rate_commission, d.price_list_commission],
		["Commission + Tax (10%+3%)", d.rate_commission_tax, d.price_list_commission_tax],
		[tc_label + (tc_is_source ? " → Standard Selling" : ""), d.rate_target_commission, d.price_list_target_commission || "Selling - Commission (Target)"],
		[tct_label + (tct_is_source ? " → Standard Selling" : ""), d.rate_target_commission_tax, d.price_list_target_commission_tax || "Selling - Commission (Tax) (Target)"],
	];
	const current = flt(d.current_selling_price);
	let html = `<div style="max-height:420px;overflow:auto;"><table class="table table-bordered small" style="min-width:720px;">
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
	html += `<div class="text-muted small">Standard Selling source: <b>${d.standard_selling_source_tier || "30%"}</b> → Suggested ${format_currency(d.suggested_selling_price)} | Current ${format_currency(current)} | Mode ${d.pricing_mode} · Fixed 30% list is Selling - 30%, Standard Selling is separate</div></div>`;

	const preview = new frappe.ui.Dialog({
		title: __("Tier Preview — ") + d.item_code,
		size: "extra-large",
		indicator: "blue",
	});
	preview.$body.html(html);
	preview.show();
}

function _show_apply_dialog(frm) {
	const target_label = `Target (${flt(frm.doc.target_margin_pct) || 0}%)`;
	const tc_label = `Target Commission (${flt(frm.doc.commission_pct) || 0}%)`;
	const tct_label = `Target Commission (Tax) (${flt(frm.doc.commission_pct) || 0}%+${flt(frm.doc.wht_pct) || 0}%)`;
	const d = new frappe.ui.Dialog({
		title: __("Apply Tier Prices — ") + frm.doc.item_code,
		size: "extra-large",
		fields: [
			{ fieldname: "info", fieldtype: "HTML", options: `<div class="text-muted small">Standard Selling will be set from <b>${frm.doc.standard_selling_source_tier || "30%"}</b> (${format_currency(frm.doc.suggested_selling_price)}). Choose tiers to create/update Item Price rows. History kept via <code>valid_from</code>. Fixed 30% writes to Selling - 30%, Target writes to ${frm.doc.price_list || "Standard Selling"}.</div>` },
			{ fieldname: "tier_basic", fieldtype: "Check", label: __("Basic (") + format_currency(frm.doc.basic_rate) + " → " + (frm.doc.price_list_basic || "Selling - Basic") + ")" },
			{ fieldname: "tier_target", fieldtype: "Check", label: __(target_label + " (") + format_currency(frm.doc.target_rate) + " → " + (frm.doc.price_list || "Standard Selling") + ")" , default: 1 },
			{ fieldname: "tier_15", fieldtype: "Check", label: __("15% (") + format_currency(frm.doc.rate_15) + " → " + (frm.doc.price_list_15 || "Selling - 15%") + ")" },
			{ fieldname: "tier_30", fieldtype: "Check", label: __("30% (") + format_currency(frm.doc.rate_30) + " → " + (frm.doc.price_list_30 || "Selling - 30%") + ")" },
			{ fieldname: "tier_45", fieldtype: "Check", label: __("45% (") + format_currency(frm.doc.rate_45) + " → " + (frm.doc.price_list_45 || "Selling - 45%") + ")" },
			{ fieldname: "tier_commission", fieldtype: "Check", label: __("Commission (10%) (") + format_currency(frm.doc.rate_commission) + " → " + (frm.doc.price_list_commission || "Selling - Commission (10%)") + ")" },
			{ fieldname: "tier_commission_tax", fieldtype: "Check", label: __("Commission + Tax (10%+3%) (") + format_currency(frm.doc.rate_commission_tax) + " → " + (frm.doc.price_list_commission_tax || "Selling - Commission (Tax) (10%+3%)") + ")" },
			{ fieldname: "tier_target_commission", fieldtype: "Check", label: __(tc_label + " (") + format_currency(frm.doc.rate_target_commission) + " → " + (frm.doc.price_list_target_commission || "Selling - Commission (Target)") + ")" },
			{ fieldname: "tier_target_commission_tax", fieldtype: "Check", label: __(tct_label + " (") + format_currency(frm.doc.rate_target_commission_tax) + " → " + (frm.doc.price_list_target_commission_tax || "Selling - Commission (Tax) (Target)") + ")" },
		],
		primary_action_label: __("Apply Selected"),
		primary_action(values) {
			const map = { tier_basic: "basic", tier_target: "target", tier_15: "15", tier_30: "30", tier_45: "45", tier_commission: "commission", tier_commission_tax: "commission_tax", tier_target_commission: "target_commission", tier_target_commission_tax: "target_commission_tax" };
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
	// default select Target + maybe all if user wants "Apply All" quickly — keep Target checked
	// Add Apply All helper
	d.set_secondary_action(() => {
		const all = ["basic", "target", "15", "30", "45", "commission", "commission_tax", "target_commission", "target_commission_tax"];
		frappe.confirm(__("Apply ALL 9 tiers?"), () => {
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
	d.get_secondary_btn().text(__("Apply All 9"));
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
	const base_total = flt(frm.doc.estimated_base_rate) * qty;

	if (flt(frm.doc.estimated_true_cost_override)) {
		const per = flt(frm.doc.estimated_true_cost_override) / qty;
		const hint = `<div class="manual-totals-hint text-muted small" style="margin-top:6px;">Override total ${format_currency(frm.doc.estimated_true_cost_override)} for ${qty} units → <b>${format_currency(per)} / unit</b></div>`;
		field.$wrapper.find(".control-value").after(hint);
		return;
	}

	const fixed_total = flt(frm.doc.manual_fixed_cost) * qty;
	const other_totals = flt(frm.doc.manual_bank_charges) + flt(frm.doc.manual_freight) + flt(frm.doc.manual_clearing_fees) + flt(frm.doc.manual_transport_in) + flt(frm.doc.manual_transport_out) + flt(frm.doc.manual_overhead);
	const totals = other_totals + fixed_total;
	const true_total = base_total + totals;
	const true_per = true_total / qty;

	// show lane only if at least one total or base entered
	if (!base_total && !totals) return;

	const parts = [];
	if (flt(frm.doc.manual_bank_charges)) parts.push(`Bank ${format_currency(flt(frm.doc.manual_bank_charges)/qty)}/u`);
	if (flt(frm.doc.manual_freight)) parts.push(`Freight ${format_currency(flt(frm.doc.manual_freight)/qty)}/u`);
	if (flt(frm.doc.manual_clearing_fees)) parts.push(`Clearing ${format_currency(flt(frm.doc.manual_clearing_fees)/qty)}/u`);
	if (flt(frm.doc.manual_transport_in)) parts.push(`Tin ${format_currency(flt(frm.doc.manual_transport_in)/qty)}/u`);
	if (flt(frm.doc.manual_transport_out)) parts.push(`Tout ${format_currency(flt(frm.doc.manual_transport_out)/qty)}/u`);
	if (flt(frm.doc.manual_overhead)) parts.push(`Overhead ${format_currency(flt(frm.doc.manual_overhead)/qty)}/u`);
	if (flt(frm.doc.manual_fixed_cost)) parts.push(`Fixed ${format_currency(flt(frm.doc.manual_fixed_cost))}/u`);

	const detail = parts.length ? ` · ${parts.join(" · ")}` : "";
	const hint = `<div class="manual-totals-hint text-muted small" style="margin-top:6px;">Base ${format_currency(base_total)} + shared ${format_currency(totals)} = total ${format_currency(true_total)} for ${qty} units → <b>${format_currency(true_per)} / unit</b><span class="text-muted">${detail}</span></div>`;
	field.$wrapper.find(".control-value").after(hint);
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
			tier.$wrapper.append(`<div class="tier-lane text-muted small" style="margin-top:4px;">Basic ${format_currency(frm.doc.basic_rate)} · ${tgt}15% ${format_currency(frm.doc.rate_15)} · 30% ${format_currency(frm.doc.rate_30)} · 45% ${format_currency(frm.doc.rate_45)} · Comm10% ${format_currency(frm.doc.rate_commission)} · Comm10+3% ${format_currency(frm.doc.rate_commission_tax)} · ${tc}Final ${format_currency(frm.doc.final_rate_per_unit)}</div>`);
		}
	}
}
