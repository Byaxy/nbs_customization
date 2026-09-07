// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Pricing Quotation Batch", {
	refresh(frm) {
		if (frm.is_new()) frm.enable_save();
		_add_buttons(frm);
		_render_converted_hints(frm);
	},

	company(frm) {
		if (frm.doc.company) {
			frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
				if (r.message) frm.set_value("company_currency", r.message.default_currency);
			});
		}
	},

	cost_currency(frm) {
		_fetch_fx(frm);
		_render_converted_hints(frm);
	},

	company_currency(frm) {
		_fetch_fx(frm);
		_render_converted_hints(frm);
	},

	exchange_rate(frm) {
		_render_converted_hints(frm);
	},

	exchange_rate_date(frm) {
		_fetch_fx(frm);
	},

	convert_total_bank_charges(frm) { _render_converted_hints(frm); },
	convert_total_freight(frm) { _render_converted_hints(frm); },
	convert_total_clearing_fees(frm) { _render_converted_hints(frm); },
	convert_total_fixed_cost(frm) { _render_converted_hints(frm); },
	convert_total_transport_in(frm) { _render_converted_hints(frm); },
	convert_total_transport_out(frm) { _render_converted_hints(frm); },
	convert_total_overhead(frm) { _render_converted_hints(frm); },
});

frappe.ui.form.on("Item Pricing Quotation Batch Item", {
	qty(frm) {
		frm.set_value("total_base", "");
	},

	unit_cost(frm) {
		frm.set_value("total_base", "");
		_render_row_converted_hint(frm);
	},

	convert_unit_cost(frm) {
		_render_row_converted_hint(frm);
	},

	target_margin_pct(frm) {
		frm.set_value("total_final", "");
	},
});

function _fetch_fx(frm) {
	if (!frm.doc.cost_currency || !frm.doc.company_currency) return;
	if (frm.doc.cost_currency === frm.doc.company_currency) {
		frm.set_value("exchange_rate", 1);
		return;
	}
	// don't overwrite manual edit if user just typed
	frappe.call({
		method: "nbs_customization.utils.pricing.get_exchange_rate",
		args: {
			from_currency: frm.doc.cost_currency,
			to_currency: frm.doc.company_currency,
			date: frm.doc.exchange_rate_date || frm.doc.posting_date || frappe.datetime.get_today(),
		},
		callback(r) {
			if (r.message && flt(r.message)) {
				// only auto-fill if current is 0/1 or matches fetched? keep manual override if user edited
				if (!flt(frm.doc.exchange_rate) || flt(frm.doc.exchange_rate) === 1) {
					frm.set_value("exchange_rate", r.message);
				}
			}
		},
	});
}

function _render_converted_hints(frm) {
	const isFX = frm.doc.cost_currency && frm.doc.company_currency && frm.doc.cost_currency !== frm.doc.company_currency;
	const rate = flt(frm.doc.exchange_rate) || 1;
	const fields = [
		["total_bank_charges", "convert_total_bank_charges"],
		["total_freight", "convert_total_freight"],
		["total_clearing_fees", "convert_total_clearing_fees"],
		["total_fixed_cost", "convert_total_fixed_cost"],
		["total_transport_in", "convert_total_transport_in"],
		["total_transport_out", "convert_total_transport_out"],
		["total_overhead", "convert_total_overhead"],
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
	// also for items grid unit_cost
	_render_row_converted_hint(frm);
}

function _render_row_converted_hint(frm) {
	// For grid rows, show hint in grid? Use simple approach: find unit_cost inputs
	const isFX = frm.doc.cost_currency && frm.doc.company_currency && frm.doc.cost_currency !== frm.doc.company_currency;
	if (!isFX || !frm.doc.items) return;
	// No per-field hint in grid easily, skip detailed. Totals preview will show converted totals.
}

function _add_buttons(frm) {
	if (frm.doc.docstatus !== 0) return;
	if (!frm.doc.items || !frm.doc.items.length) return;

	frm.add_custom_button(__("Recalculate Allocations"), () => {
		frm.save();
	}, __("Actions"));

	if (frm.doc.docstatus === 0 && frm.doc.items.length) {
		frm.add_custom_button(
			__("Preview Totals"),
			() => {
				let html = `<div style="max-height:420px;overflow:auto;"><table class="table table-bordered small" style="min-width:720px;"><thead><tr><th>Item</th><th>Qty</th><th>True Cost / Unit (${frm.doc.company_currency || ""})</th><th>Final / Unit (${frm.doc.company_currency || ""})</th><th>Final Total (${frm.doc.company_currency || ""})</th></tr></thead><tbody>`;
				for (const r of frm.doc.items) {
					html += `<tr><td>${r.item_code}</td><td class="text-right">${r.qty}</td><td class="text-right">${format_currency(r.true_cost_per_unit || 0)}</td><td class="text-right" style="font-weight:600">${format_currency(r.final_rate_per_unit || 0)}</td><td class="text-right">${format_currency(r.final_total || 0)}</td></tr>`;
				}
				html += `</tbody></table><div class="text-muted small">Totals — Base ${format_currency(frm.doc.total_base || 0)} · True Cost ${format_currency(frm.doc.total_true_cost || 0)} · Final ${format_currency(frm.doc.total_final || 0)} · Standard Selling source ${frm.doc.standard_selling_source_tier || "30%"} (Cost ${frm.doc.cost_currency || ""}→${frm.doc.company_currency || ""} @ ${frm.doc.exchange_rate || 1})</div></div>`;
				const preview = new frappe.ui.Dialog({
					title: __("Allocation Preview"),
					size: "extra-large",
					indicator: "blue",
				});
				preview.$body.html(html);
				preview.show();
			},
			__("Actions")
		);
	}
}
