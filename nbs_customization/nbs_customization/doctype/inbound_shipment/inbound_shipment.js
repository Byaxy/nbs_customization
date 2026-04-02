// Copyright (c) 2026, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inbound Shipment", {
	setup(frm) {
		// Cost center filtered by company
		frm.set_query("cost_center", () => ({
			filters: {
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
			},
		}));

		// POs in the purchase_orders child table — filtered by suppliers
		// currently in the suppliers child table
		frm.set_query("purchase_order", "purchase_orders", () => {
			const supplier_list = (frm.doc.suppliers || []).map((r) => r.supplier).filter(Boolean);

			const filters = {
				docstatus: 1,
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
			};
			if (supplier_list.length) {
				filters["supplier"] = ["in", supplier_list];
			}
			return { filters };
		});

		// purchase_order on a package item — only POs already added to the
		// shipment's purchase_orders table
		frm.set_query("purchase_order", "package_items", () => {
			const po_list = (frm.doc.purchase_orders || [])
				.map((r) => r.purchase_order)
				.filter(Boolean);

			if (!po_list.length) {
				// Return an impossible filter so the list comes up empty with a clear message
				return { filters: { name: ["in", ["__none__"]] } };
			}
			return { filters: { name: ["in", po_list] } };
		});

		// item_code on a package item — only items belonging to the PO
		// selected on THAT ROW
		frm.set_query("item_code", "package_items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			if (!row.purchase_order) {
				frappe.show_alert(
					{
						message: __("Please select a Purchase Order on this row first."),
						indicator: "orange",
					},
					3,
				);
				return { filters: { name: ["in", ["__none__"]] } };
			}
			return {
				query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_po_items_for_query",
				filters: { purchase_order: row.purchase_order },
			};
		});

		// purchase_receipt on a package item — read-only informational,
		// filtered by submitted PRs linked to the POs in this shipment
		frm.set_query("purchase_receipt", "package_items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const filters = {
				docstatus: 1,
				company: doc.company || frappe.defaults.get_user_default("Company"),
			};
			if (row.purchase_order) {
				filters["purchase_order"] = row.purchase_order;
			}
			return { filters };
		});

		frm.set_query("carrier", () => ({
			filters: {
				carrier_type: frm.doc.shipping_mode || "",
				is_active: 1,
			},
		}));

		frm.set_query("shipper_address", () => {
			if (frm.doc.shipper_type === "Supplier" && frm.doc.shipper_supplier) {
				return {
					query: "frappe.contacts.doctype.address.address.address_query",
					filters: { link_doctype: "Supplier", link_name: frm.doc.shipper_supplier },
				};
			}
			// Courier — no filter, any address
			return {};
		});
	},

	refresh(frm) {
		frm.trigger("toggle_route_fields");
		toggle_shipper_fields(frm);
		update_package_number_options(frm);
		add_shipment_action_buttons(frm);
	},

	shipping_mode(frm) {
		frm.trigger("toggle_route_fields");
		suggest_volumetric_divisor(frm);

		// Carrier options change with mode — clear stale selection
		const current_carrier_type = frm.doc.carrier_type;
		if (current_carrier_type && current_carrier_type !== frm.doc.shipping_mode) {
			frm.set_value("carrier", null);
			frappe.show_alert(
				{
					message: __(
						"Carrier cleared — please select a carrier for the new shipping mode.",
					),
					indicator: "orange",
				},
				4,
			);
		}
	},

	shipper_type(frm) {
		toggle_shipper_fields(frm);
		frm.set_value("shipper_supplier", null);
		frm.set_value("shipper_name", null);
		frm.set_value("shipper_address", null);
		frm.set_value("shipper_address_display", null);
	},

	shipper_supplier(frm) {
		if (!frm.doc.shipper_supplier) {
			frm.set_value("shipper_name", null);
			frm.set_value("shipper_address", null);
			frm.set_value("shipper_address_display", null);
			return;
		}

		// Populate shipper_name from supplier
		frappe.db.get_value("Supplier", frm.doc.shipper_supplier, "supplier_name", (r) => {
			if (r) frm.set_value("shipper_name", r.supplier_name);
		});

		// Fetch the supplier's default primary address
		frappe.call({
			method: "frappe.contacts.doctype.address.address.get_default_address",
			args: {
				doctype: "Supplier",
				name: frm.doc.shipper_supplier,
			},
			callback(r) {
				if (r.message) {
					frm.set_value("shipper_address", r.message);
					// Trigger display render
					frm.trigger("shipper_address");
				} else {
					frm.set_value("shipper_address", null);
					frm.set_value("shipper_address_display", null);
				}
			},
		});
	},

	shipper_address(frm) {
		if (!frm.doc.shipper_address) {
			frm.set_value("shipper_address_display", null);
			return;
		}
		frappe.call({
			method: "frappe.contacts.doctype.address.address.get_address_display",
			args: { address_dict: frm.doc.shipper_address },
			callback(r) {
				if (r.message) {
					frm.set_value("shipper_address_display", r.message);
				}
			},
		});
	},

	company(frm) {
		frm.set_value("cost_center", null);
		frm.refresh_fields(["cost_center", "purchase_receipts"]);
	},

	toggle_route_fields(frm) {
		frm.refresh_fields(["container_number", "flight_number"]);
	},
});

// ------------------------------------------------------------------ //
// Suppliers child table                                                //
// ------------------------------------------------------------------ //

frappe.ui.form.on("Inbound Shipment Supplier", {
	supplier(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.supplier) return;
		frappe.db.get_value("Supplier", row.supplier, "supplier_name", (r) => {
			if (r) frappe.model.set_value(cdt, cdn, "supplier_name", r.supplier_name);
		});

		// When a supplier is added or changed, refresh the PO query
		// so the purchase_orders table reflects the updated supplier list
		frm.refresh_field("purchase_orders");
	},

	suppliers_remove(frm) {
		// Refresh PO filter whenever supplier list changes
		frm.refresh_field("purchase_orders");
	},
});

// ------------------------------------------------------------------ //
// Purchase Orders child table                                          //
// ------------------------------------------------------------------ //

frappe.ui.form.on("Inbound Shipment Purchase Order", {
	purchase_order(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.purchase_order) return;

		frappe.db.get_value(
			"Purchase Order",
			row.purchase_order,
			["supplier", "transaction_date", "grand_total", "status"],
			(r) => {
				if (!r) return;
				frappe.model.set_value(cdt, cdn, "supplier", r.supplier);
				frappe.model.set_value(cdt, cdn, "transaction_date", r.transaction_date);
				frappe.model.set_value(cdt, cdn, "grand_total", r.grand_total);
				frappe.model.set_value(cdt, cdn, "status", r.status);
			},
		);

		// Refresh package items PO filter now that PO list changed
		frm.refresh_field("package_items");
	},

	purchase_orders_remove(frm) {
		frm.refresh_field("package_items");
	},
});

// ------------------------------------------------------------------ //
// Package child table                                                  //
// ------------------------------------------------------------------ //

frappe.ui.form.on("Inbound Shipment Package", {
	packages_add(frm, cdt, cdn) {
		// Auto-generate package number based on current row count
		// Filter out the newly added row (it's already in frm.doc.packages
		// at this point but has no package_number yet)
		const existing_numbers = (frm.doc.packages || [])
			.filter((r) => r.name !== cdn && r.package_number)
			.map((r) => r.package_number);

		const next_num = existing_numbers.length + 1;
		const pkg_no = `PKG-${String(next_num).padStart(3, "0")}`;

		frappe.model.set_value(cdt, cdn, "package_number", pkg_no);

		// Set default volumetric divisor based on shipping mode
		const divisor = get_default_divisor(frm.doc.shipping_mode);
		frappe.model.set_value(cdt, cdn, "volumetric_divisor", divisor);

		// Update package_items select options to include the new package
		update_package_number_options(frm);
	},

	packages_remove(frm) {
		// Renumber all remaining packages sequentially
		renumber_packages(frm);

		// Sync package_items select options
		update_package_number_options(frm);

		// Recompute totals
		recompute_totals(frm);
	},

	length(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
	width(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
	height(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
	net_weight(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
	volumetric_divisor(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
	unit_price_per_kg(frm, cdt, cdn) {
		compute_package_row(frm, cdt, cdn);
	},
});

// ------------------------------------------------------------------ //
// Package number helpers                                               //
// ------------------------------------------------------------------ //

function renumber_packages(frm) {
	(frm.doc.packages || []).forEach((row, idx) => {
		const new_no = `PKG-${String(idx + 1).padStart(3, "0")}`;
		if (row.package_number !== new_no) {
			frappe.model.set_value(row.doctype, row.name, "package_number", new_no);
		}
	});
	frm.refresh_field("packages");
}

function update_package_number_options(frm) {
	// Build options string from current packages — blank first for "not set"
	const pkg_numbers = (frm.doc.packages || []).map((r) => r.package_number).filter(Boolean);

	const options = ["", ...pkg_numbers].join("\n");

	// Update the Select field options on the package_items grid
	frm.fields_dict.package_items.grid.update_docfield_property(
		"package_number",
		"options",
		options,
	);
	frm.fields_dict.package_items.grid.refresh();

	// Toggle whether rows can be added at all
	toggle_package_items_addable(frm);
}

function toggle_package_items_addable(frm) {
	const has_packages = (frm.doc.packages || []).length > 0;
	const grid = frm.fields_dict.package_items.grid;

	grid.cannot_add_rows = !has_packages;
	grid.refresh();

	// Show a helper message in the grid header when locked
	const $header = frm.fields_dict.package_items.$wrapper;
	$header.find(".no-packages-msg").remove();
	if (!has_packages) {
		$header.find(".grid-heading-row").after(
			`<div class="no-packages-msg text-muted small p-2">
                ⚠ Add at least one package above before adding items.
            </div>`,
		);
	}
}

// ------------------------------------------------------------------ //
// Other Helper functions                                                     //
// ------------------------------------------------------------------ //

function toggle_shipper_fields(frm) {
	const is_supplier = frm.doc.shipper_type === "Supplier";

	frm.set_df_property("shipper_supplier", "hidden", is_supplier ? 0 : 1);
	frm.set_df_property("shipper_supplier", "reqd", is_supplier ? 1 : 0);
	frm.set_df_property("shipper_name", "read_only", is_supplier ? 1 : 0);
	frm.set_df_property("shipper_name", "reqd", 1);

	frm.set_df_property("shipper_address", "reqd", 0);

	frm.refresh_fields([
		"shipper_supplier",
		"shipper_name",
		"shipper_address",
		"shipper_address_display",
	]);
}

function compute_package_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const divisor = flt(row.volumetric_divisor) || 5000;
	const vol = (flt(row.length) * flt(row.width) * flt(row.height)) / divisor;
	const chargeable = Math.max(flt(row.net_weight), vol);
	const freight = chargeable * flt(row.unit_price_per_kg);

	frappe.model.set_value(cdt, cdn, "volumetric_weight", flt(vol, 3));
	frappe.model.set_value(cdt, cdn, "chargeable_weight", flt(chargeable, 3));
	frappe.model.set_value(cdt, cdn, "freight_charge", flt(freight, 2));

	recompute_totals(frm);
}

function get_default_divisor(mode) {
	return mode === "Sea" ? 1000000 : 5000;
}

function suggest_volumetric_divisor(frm) {
	const divisor = get_default_divisor(frm.doc.shipping_mode);
	(frm.doc.packages || []).forEach((row) => {
		if (!row.volumetric_divisor || row.volumetric_divisor === 5000) {
			frappe.model.set_value(row.doctype, row.name, "volumetric_divisor", divisor);
		}
	});
}

// ------------------------------------------------------------------ //
// Package Items child table                                            //
// ------------------------------------------------------------------ //

// Guard set — prevents bidirectional handlers from triggering each other
const _computing_item_weight = new Set();

frappe.ui.form.on("Inbound Shipment Package Item", {
	package_number(frm, cdt, cdn) {
		validate_unique_package_item(frm, cdt, cdn);
		recompute_package_net_weights(frm);
	},

	purchase_order(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// Clear item when PO changes — stale item from a different PO
		frappe.model.set_value(cdt, cdn, "item_code", null);
		frappe.model.set_value(cdt, cdn, "description", null);
		frappe.model.set_value(cdt, cdn, "uom", null);
		frappe.model.set_value(cdt, cdn, "net_weight_per_unit", null);
		frappe.model.set_value(cdt, cdn, "net_weight", 0);

		validate_unique_package_item(frm, cdt, cdn);
	},

	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;

		// Pull description and weight from Item master
		frappe.db.get_value("Item", row.item_code, ["description", "weight_per_unit"], (r) => {
			if (!r) return;
			frappe.model.set_value(cdt, cdn, "description", r.description);
			if (r.weight_per_unit && !row.net_weight_per_unit) {
				frappe.model.set_value(cdt, cdn, "net_weight_per_unit", r.weight_per_unit);
			}
		});

		// If a PO is selected on this row, also pull the ordered qty
		// from the PO line item as a convenience default
		if (row.purchase_order) {
			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_po_item_details",
				args: {
					purchase_order: row.purchase_order,
					item_code: row.item_code,
				},
				callback(r) {
					if (!r.message) return;
					const d = r.message;
					if (!row.qty) {
						frappe.model.set_value(cdt, cdn, "qty", d.qty);
					}
					if (!row.uom) {
						frappe.model.set_value(cdt, cdn, "uom", d.uom);
					}
					if (!row.net_weight_per_unit && d.weight_per_unit) {
						frappe.model.set_value(cdt, cdn, "net_weight_per_unit", d.weight_per_unit);
					}
				},
			});
		}

		validate_unique_package_item(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const qty = flt(row.qty);
		if (!qty) return;

		if (flt(row.net_weight_per_unit)) {
			set_item_total_weight(frm, cdt, cdn, flt(qty * flt(row.net_weight_per_unit), 3));
		} else if (flt(row.net_weight)) {
			set_item_unit_weight(frm, cdt, cdn, flt(flt(row.net_weight) / qty, 3));
		}
	},

	net_weight_per_unit(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (_computing_item_weight.has(cdn)) return;

		const per_unit = flt(row.net_weight_per_unit);
		const qty = flt(row.qty);
		if (!per_unit || !qty) return;

		set_item_total_weight(frm, cdt, cdn, flt(per_unit * qty, 3));
	},

	net_weight(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (_computing_item_weight.has(cdn)) return;

		const total = flt(row.net_weight);
		const qty = flt(row.qty);
		if (!total || !qty) return;

		set_item_unit_weight(frm, cdt, cdn, flt(total / qty, 3));
		recompute_package_net_weights(frm);
	},

	package_items_remove(frm) {
		recompute_package_net_weights(frm);
		recompute_totals(frm);
	},
});

// ------------------------------------------------------------------ //
// Bidirectional weight helpers                                         //
// ------------------------------------------------------------------ //

function set_item_total_weight(frm, cdt, cdn, value) {
	const rounded = flt(value, 3);
	const row = locals[cdt][cdn];
	if (flt(row.net_weight, 3) === rounded) return;
	_computing_item_weight.add(cdn);
	frappe.model.set_value(cdt, cdn, "net_weight", rounded);
	_computing_item_weight.delete(cdn);

	recompute_package_net_weights(frm);
}

function set_item_unit_weight(frm, cdt, cdn, value) {
	const rounded = flt(value, 3);
	const row = locals[cdt][cdn];
	if (flt(row.net_weight_per_unit, 3) === rounded) return;

	_computing_item_weight.add(cdn);
	frappe.model.set_value(cdt, cdn, "net_weight_per_unit", rounded);
	_computing_item_weight.delete(cdn);
}

function validate_unique_package_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.purchase_order || !row.package_number) return;

	const duplicate = (frm.doc.package_items || []).find(
		(r) =>
			r.name !== cdn &&
			r.package_number === row.package_number &&
			r.purchase_order === row.purchase_order &&
			r.item_code === row.item_code,
	);

	if (duplicate) {
		frappe.show_alert(
			{
				message: __(
					`Item <b>${row.item_code}</b> from <b>${row.purchase_order}</b> ` +
						`already exists in <b>${row.package_number}</b> ` +
						`(row #${duplicate.idx}). Please combine the quantities.`,
				),
				indicator: "red",
			},
			6,
		);

		// Clear the field that just triggered the duplicate
		// so the user is forced to correct it
		frappe.model.set_value(cdt, cdn, "item_code", null);
		frappe.model.set_value(cdt, cdn, "description", null);
		frappe.model.set_value(cdt, cdn, "qty", null);
		frappe.model.set_value(cdt, cdn, "uom", null);
		frappe.model.set_value(cdt, cdn, "net_weight_per_unit", null);
		frappe.model.set_value(cdt, cdn, "net_weight", 0);
	}
}

// ------------------------------------------------------------------ //
// Package Net Weights                                                //
// ------------------------------------------------------------------ //
function recompute_package_net_weights(frm) {
	// Sum item net weights grouped by package_number
	const weight_map = {};
	(frm.doc.package_items || []).forEach((item) => {
		if (!item.package_number) return;
		weight_map[item.package_number] =
			(weight_map[item.package_number] || 0) + flt(item.net_weight);
	});

	// Write back to each package row
	(frm.doc.packages || []).forEach((pkg) => {
		const computed = flt(weight_map[pkg.package_number] || 0, 3);
		if (flt(pkg.net_weight) !== computed) {
			frappe.model.set_value(pkg.doctype, pkg.name, "net_weight", computed);
		}
	});

	recompute_totals(frm);
}

// ------------------------------------------------------------------ //
// Purchase Receipts child table (read-only, no events needed)         //
// Populated server-side via Purchase Receipt on_submit hook           //
// ------------------------------------------------------------------ //

// ------------------------------------------------------------------ //
// Totals                                                               //
// ------------------------------------------------------------------ //

function recompute_totals(frm) {
	const pkgs = frm.doc.packages || [];
	const items = frm.doc.package_items || [];

	frm.set_value("total_packages", pkgs.length);
	frm.set_value(
		"total_items",
		items.reduce((s, i) => s + flt(i.qty), 0),
	);
	frm.set_value(
		"total_net_weight",
		flt(
			pkgs.reduce((s, p) => s + flt(p.net_weight), 0),
			3,
		),
	);
	frm.set_value(
		"total_gross_weight",
		flt(
			pkgs.reduce((s, p) => s + flt(p.gross_weight), 0),
			3,
		),
	);
	frm.set_value(
		"total_chargeable_weight",
		flt(
			pkgs.reduce((s, p) => s + flt(p.chargeable_weight), 0),
			3,
		),
	);
	frm.set_value(
		"total_freight_charges",
		flt(
			pkgs.reduce((s, p) => s + flt(p.freight_charge), 0),
			2,
		),
	);
}

// ------------------------------------------------------------------ //
// Action buttons                                                       //
// ------------------------------------------------------------------ //

function add_shipment_action_buttons(frm) {
	frm.remove_custom_button(__("View Linked Expenses"), __("View"));
	frm.remove_custom_button(__("Create Shipment Expense"), __("Create"));

	if (frm.doc.docstatus === 1) {
		frm.add_custom_button(
			__("View Linked Expenses"),
			() => {
				frappe.set_route("List", "Expense", { linked_shipment: frm.doc.name });
			},
			__("View"),
		);

		frm.add_custom_button(
			__("Create Shipment Expense"),
			() => {
				frappe.new_doc("Expense", {
					is_accompanying: 1,
					expense_scope: "Inbound Shipment",
					linked_shipment: frm.doc.name,
					company: frm.doc.company,
				});
			},
			__("Create"),
		);
	}
}
