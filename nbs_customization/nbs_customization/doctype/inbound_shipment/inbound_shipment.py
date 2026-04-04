# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document


class InboundShipment(Document):

	def validate(self):
		self._set_company_defaults()
		self._validate_suppliers()
		self._validate_purchase_orders()
		self._validate_carrier()
		self._compute_item_weights()                       
		self._compute_package_net_weights_from_items()     
		self._compute_package_weights()                     
		self._compute_totals()
		self._validate_package_item_references()
		self._validate_package_item_pos()
		self._validate_package_item_qty_within_po_qty()
		self._validate_unique_package_items()

	def before_submit(self):
		self._validate_before_submit()

	def on_cancel(self):
		self._unlink_all_purchase_receipts()
		self._check_linked_expenses_on_cancel()

	# ------------------------------------------------------------------ #
	# Validate Carrier                                                    #
	# ------------------------------------------------------------------ #
	def _validate_carrier(self):
		if not self.carrier or not self.shipping_mode:
			return

		carrier_type = frappe.db.get_value("Carrier", self.carrier, "carrier_type")
		if carrier_type != self.shipping_mode:
			frappe.throw(
				_(f"Carrier <b>{self.carrier}</b> is of type <b>{carrier_type}</b> "
				f"but Shipping Mode is <b>{self.shipping_mode}</b>. "
				f"Please select a carrier that matches the shipping mode.")
			)
		
		is_active = frappe.db.get_value("Carrier", self.carrier, "is_active")
		if not is_active:
			frappe.throw(
				_(f"Carrier <b>{self.carrier}</b> is inactive. "
				f"Please select an active carrier or reactivate it in the Carrier master.")
			)

	# ------------------------------------------------------------------ #
	# Defaults                                                            #
	# ------------------------------------------------------------------ #

	def _set_company_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if not self.cost_center:
			self.cost_center = frappe.db.get_value(
				"Company", self.company, "cost_center"
			)

	# ------------------------------------------------------------------ #
	# Supplier / PO validation                                            #
	# ------------------------------------------------------------------ #

	def _validate_suppliers(self):
		seen = set()
		for row in (self.suppliers or []):
			if not row.supplier:
				continue
			if row.supplier in seen:
				frappe.throw(
					_(f"Supplier <b>{row.supplier}</b> appears more than once "
					f"(row #{row.idx}). Please remove the duplicate.")
				)
			seen.add(row.supplier)
			row.supplier_name = frappe.db.get_value(
				"Supplier", row.supplier, "supplier_name"
			) or row.supplier

	def _validate_purchase_orders(self):
		supplier_set = {r.supplier for r in (self.suppliers or []) if r.supplier}
		seen = set()

		for row in (self.purchase_orders or []):
			if not row.purchase_order:
				continue
			if row.purchase_order in seen:
				frappe.throw(
					_(f"Purchase Order <b>{row.purchase_order}</b> appears more than once "
					f"(row #{row.idx}). Please remove the duplicate.")
				)
			seen.add(row.purchase_order)

			po = frappe.db.get_value(
				"Purchase Order",
				row.purchase_order,
				["docstatus", "company", "supplier", "transaction_date",
				"grand_total", "status"],
				as_dict=True,
			)
			if not po:
				frappe.throw(_(f"Purchase Order <b>{row.purchase_order}</b> not found."))
			if po.docstatus != 1:
				frappe.throw(
					_(f"Purchase Order <b>{row.purchase_order}</b> must be submitted "
					f"(row #{row.idx}).")
				)
			if po.company != self.company:
				frappe.throw(
					_(f"Purchase Order <b>{row.purchase_order}</b> belongs to "
					f"company <b>{po.company}</b>, not <b>{self.company}</b> "
					f"(row #{row.idx}).")
				)
			if supplier_set and po.supplier not in supplier_set:
				frappe.throw(
					_(f"Purchase Order <b>{row.purchase_order}</b> belongs to supplier "
					f"<b>{po.supplier}</b>, who is not in the Suppliers table "
					f"(row #{row.idx}). Add the supplier first.")
				)
			row.supplier         = po.supplier
			row.transaction_date = po.transaction_date
			row.grand_total      = po.grand_total
			row.status           = po.status

	# ------------------------------------------------------------------ #
	# Package item PO validation                                          #
	# ------------------------------------------------------------------ #

	def _validate_package_item_pos(self):
		"""
		Each package item with a purchase_order must reference a PO
		that exists in the shipment's purchase_orders table.
		Also verifies the item_code exists in that PO.
		"""
		po_set = {r.purchase_order for r in (self.purchase_orders or []) if r.purchase_order}

		for item in (self.package_items or []):
			if not item.purchase_order:
				continue
			if item.purchase_order not in po_set:
				frappe.throw(
				_(f"Package item <b>{item.item_code}</b> references Purchase Order "
					f"<b>{item.purchase_order}</b>, which is not in this shipment's "
					f"Purchase Orders table.")
				)
			# Verify item belongs to that PO
			exists = frappe.db.exists(
				"Purchase Order Item",
				{"parent": item.purchase_order, "item_code": item.item_code},
			)
			if not exists:
				frappe.throw(
				_(f"Item <b>{item.item_code}</b> does not exist in Purchase Order "
					f"<b>{item.purchase_order}</b>.")
				)

	def _validate_unique_package_items(self):
		seen = set()
		for row in (self.package_items or []):
			if not row.item_code or not row.purchase_order or not row.package_number:
				continue
			key = (row.package_number, row.purchase_order, row.item_code)
			if key in seen:
				frappe.throw(
					_(f"Duplicate entry in Package Items (row #{row.idx}): "
					f"Item <b>{row.item_code}</b> from PO <b>{row.purchase_order}</b> "
					f"already exists in <b>{row.package_number}</b>. "
					f"Please combine the quantities into one row.")
				)
			seen.add(key)

	# ------------------------------------------------------------------ #
	# Package item qty vs PO qty validation                               #
	# ------------------------------------------------------------------ #
	def _validate_package_item_qty_within_po_qty(self):
		"""Prevent over-allocation of a PO item across multiple packages.

		Rule:
		For each (purchase_order, item_code), the total qty across all package_items
		must not exceed the qty on the corresponding Purchase Order Item row.
		"""
		qty_map = {}
		for row in (self.package_items or []):
			if not row.purchase_order or not row.item_code:
				continue
			key = (row.purchase_order, row.item_code)
			qty_map[key] = qty_map.get(key, 0) + flt(row.qty)

		if not qty_map:
			return

		po_list = sorted({k[0] for k in qty_map.keys()})
		item_list = sorted({k[1] for k in qty_map.keys()})

		po_items = frappe.db.get_all(
			"Purchase Order Item",
			filters={"parent": ["in", po_list], "item_code": ["in", item_list]},
			fields=["parent", "item_code", "qty", "uom"],
			ignore_permissions=True,
		)
		po_qty_map = {(r.parent, r.item_code): flt(r.qty) for r in po_items}
		po_uom_map = {(r.parent, r.item_code): r.uom for r in po_items}

		errors = []
		for (po, item_code), total_qty in qty_map.items():
			allowed = po_qty_map.get((po, item_code))
			if allowed is not None and flt(total_qty) > flt(allowed):
				uom = po_uom_map.get((po, item_code)) or ""
				errors.append(
					f"Item <b>{item_code}</b> from PO <b>{po}</b>: "
					f"total package qty <b>{flt(total_qty)}</b> exceeds PO qty <b>{allowed}</b> {uom}."
				)

		if errors:
			frappe.throw("<br>".join(errors), title=_("Quantity Exceeds Purchase Order"))

	# ------------------------------------------------------------------ #
	# Package net weight computation                                      #
	# ------------------------------------------------------------------ #
	def _compute_package_net_weights_from_items(self):
		"""
		For each package, sum the net_weight of all package items
		that reference it by package_number.
		"""
		# Build a dict: package_number -> total net weight
		weight_map = {}
		for item in (self.package_items or []):
			if not item.package_number:
				continue
			weight_map[item.package_number] = (
				weight_map.get(item.package_number, 0) + flt(item.net_weight)
			)

		for pkg in (self.packages or []):
			pkg.net_weight = flt(weight_map.get(pkg.package_number, 0), 3)

	# ------------------------------------------------------------------ #
	# Weight computation                                                  #
	# ------------------------------------------------------------------ #

	def _compute_package_weights(self):
		for pkg in (self.packages or []):
			divisor = flt(pkg.volumetric_divisor) or 5000
			if pkg.length and pkg.width and pkg.height:
				vol = flt(
				(flt(pkg.length) * flt(pkg.width) * flt(pkg.height)) / divisor, 3
				)
			else:
				vol = 0.0
			pkg.volumetric_weight = vol
			pkg.chargeable_weight = flt(max(flt(pkg.net_weight or 0), vol), 3)
			if pkg.unit_price_per_kg:
				pkg.freight_charge = flt(pkg.chargeable_weight * flt(pkg.unit_price_per_kg), 2)

	def _compute_item_weights(self):
		for item in (self.package_items or []):
			qty          = flt(item.qty or 0)
			per_unit     = flt(item.net_weight_per_unit or 0)
			total_weight = flt(item.net_weight or 0)

			if not qty:
				continue

			if per_unit:
				item.net_weight = flt(per_unit * qty, 3)
			elif total_weight:
				item.net_weight_per_unit = flt(total_weight / qty, 3)

	# ------------------------------------------------------------------ #
	# Totals                                                              #
	# ------------------------------------------------------------------ #

	def _compute_totals(self):
		self.total_packages          = len(self.packages or [])
		self.total_items             = int(sum(flt(i.qty) for i in (self.package_items or [])))
		self.total_net_weight        = flt(sum(flt(p.net_weight)        for p in (self.packages or [])), 3)
		self.total_gross_weight      = flt(sum(flt(p.gross_weight)      for p in (self.packages or [])), 3)
		self.total_chargeable_weight = flt(sum(flt(p.chargeable_weight) for p in (self.packages or [])), 3)
		self.total_freight_charges   = flt(sum(flt(p.freight_charge)    for p in (self.packages or [])), 2)

	# ------------------------------------------------------------------ #
	# Cross-reference validation                                          #
	# ------------------------------------------------------------------ #

	def _validate_package_item_references(self):
		package_numbers = {p.package_number for p in (self.packages or []) if p.package_number}
		for item in (self.package_items or []):
			if item.package_number and item.package_number not in package_numbers:
				frappe.throw(
				_(f"Package Item for <b>{item.item_code}</b> references Package No. "
					f"<b>{item.package_number}</b>, which does not exist in the Packages table.")
				)

	# ------------------------------------------------------------------ #
	# Pre-submit guards                                                   #
	# ------------------------------------------------------------------ #

	def _validate_before_submit(self):
		if not self.purchase_orders:
			frappe.throw(_("At least one Purchase Order must be linked before submitting."))
		if not self.packages:
			frappe.throw(_("At least one Package must be defined before submitting."))

	# ------------------------------------------------------------------ #
	# Cancel guards                                                       #
	# ------------------------------------------------------------------ #

	def _unlink_all_purchase_receipts(self):
		"""
		On shipment cancel, clear custom_inbound_shipment on all linked PRs
		and remove them from the child table.
		"""
		linked_prs = frappe.db.get_all(
			"Purchase Receipt",
			filters={"custom_inbound_shipment": self.name, "docstatus": 1},
			fields=["name"],
		)
		for row in linked_prs:
			frappe.db.set_value(
				"Purchase Receipt", row.name, "custom_inbound_shipment", None
			)
		frappe.db.delete(
			"Inbound Shipment Purchase Receipt", {"parent": self.name}
		)

	def _check_linked_expenses_on_cancel(self):
		linked = frappe.db.get_all(
			"Expense",
			filters={"linked_shipment": self.name, "docstatus": 1},
			fields=["name"],
			limit=1,
		)
		if linked:
			frappe.throw(
				_(f"Cannot cancel Shipment <b>{self.name}</b>. "
				f"Submitted Expense <b>{linked[0].name}</b> is linked to it. "
				f"Cancel the expense first.")
			)

# ------------------------------------------------------------------ #
# Purchase Receipt hook handlers                                      #
# ------------------------------------------------------------------ #

def validate_purchase_receipt_shipment_link(doc, method):
	"""
	Called on Purchase Receipt 'validate' (before save).
	Ensures that if a custom_inbound_shipment is selected, it is valid.
	"""
	if not doc.custom_inbound_shipment:
		return

	# 1. Basic Shipment Checks
	shipment = frappe.db.get_value(
		"Inbound Shipment", 
		doc.custom_inbound_shipment, 
		["docstatus", "company"], 
		as_dict=True
	)
	
	if not shipment:
		frappe.throw(_("Inbound Shipment {0} not found.").format(doc.custom_inbound_shipment))
	
	if shipment.docstatus != 1:
		frappe.throw(_("Inbound Shipment {0} must be submitted.").format(doc.custom_inbound_shipment))
		
	if shipment.company != doc.company:
		frappe.throw(_("Shipment company mismatch."))

	# 2. PO and Item Logic
	shipment_pos = {
		r.purchase_order for r in frappe.get_all(
			"Inbound Shipment Purchase Order",
			filters={"parent": doc.custom_inbound_shipment},
			fields=["purchase_order"]
		)
	}

	# Map (po, item) in shipment
	pkg_items = {
		(r.purchase_order, r.item_code) for r in frappe.get_all(
			"Inbound Shipment Package Item",
			filters={"parent": doc.custom_inbound_shipment},
			fields=["purchase_order", "item_code"]
		)
	}

	has_valid_po = False
	for item in doc.items:
		if not item.purchase_order:
			continue
		
		has_valid_po = True
		
		if item.purchase_order not in shipment_pos:
			frappe.throw(_("Purchase Order {0} is not part of Shipment {1}")
				.format(item.purchase_order, doc.custom_inbound_shipment))
		
		if (item.purchase_order, item.item_code) not in pkg_items:
			frappe.throw(_("Item {0} from PO {1} is not expected in Shipment {2}")
				.format(item.item_code, item.purchase_order, doc.custom_inbound_shipment))

	if not has_valid_po:
		frappe.throw(_("Purchase Receipt must have at least one Item linked to a Purchase Order to link a Shipment."))

def on_purchase_receipt_submit(doc, method):
	"""
	When a PR is submitted with custom_inbound_shipment set,
	directly append it to that shipment's purchase_receipts child table.
	"""
	if not doc.custom_inbound_shipment:
		return
	try:
		_add_pr_to_shipment(doc.name, doc.custom_inbound_shipment)
		frappe.msgprint(
			_(f"Purchase Receipt <b>{doc.name}</b> added to "
			f"Inbound Shipment <b>{doc.custom_inbound_shipment}</b>."),
			alert=True, indicator="green"
		)
	except Exception as e:
		frappe.log_error(
			f"Failed to add PR {doc.name} to shipment "
			f"{doc.custom_inbound_shipment}: {e}",
			"Inbound Shipment Sync Error"
		)


def on_purchase_receipt_cancel(doc, method):
	"""
	When a PR is cancelled, remove it from its shipment's
	purchase_receipts table and clear the link field.
	"""
	shipment_name = doc.custom_inbound_shipment
	if not shipment_name:
		return
	try:
		_remove_pr_from_shipment(doc.name, shipment_name)
		frappe.db.set_value(
			"Purchase Receipt", doc.name, "custom_inbound_shipment", None
		)
		frappe.msgprint(
			_(f"Purchase Receipt <b>{doc.name}</b> removed from "
			f"Inbound Shipment <b>{shipment_name}</b>."),
			alert=True, indicator="orange"
		)
	except Exception as e:
		frappe.log_error(
			f"Failed to remove PR {doc.name} from shipment "
			f"{shipment_name}: {e}",
			"Inbound Shipment Sync Error"
		)


def _add_pr_to_shipment(pr_name, shipment_name):
	"""
	Directly insert a child row into the submitted shipment's
	purchase_receipts table — no full save needed.
	"""
	already_exists = frappe.db.exists(
		"Inbound Shipment Purchase Receipt",
		{"parent": shipment_name, "receipt_document": pr_name}
	)
	if already_exists:
		return

	pr = frappe.db.get_value(
		"Purchase Receipt", pr_name,
		["supplier", "grand_total"],
		as_dict=True
	)
	if not pr:
		frappe.throw(_(f"Purchase Receipt {pr_name} not found."))

	# Count existing rows to set idx correctly
	existing_count = frappe.db.count(
		"Inbound Shipment Purchase Receipt", {"parent": shipment_name}
	)

	frappe.new_doc("Inbound Shipment Purchase Receipt").update({
		"parent":               shipment_name,
		"parenttype":           "Inbound Shipment",
		"parentfield":          "purchase_receipts",
		"receipt_document":     pr_name,
		"supplier":             pr.supplier,
		"grand_total":          pr.grand_total,
		"idx":                  existing_count + 1,
	}).insert(ignore_permissions=True)

	# Touch modified timestamp so form refresh detects the change
	frappe.db.set_value(
		"Inbound Shipment", shipment_name,
		"modified", frappe.utils.now(),
		update_modified=False
	)


def _remove_pr_from_shipment(pr_name, shipment_name):
	"""
	Directly delete the child row from the submitted shipment's
	purchase_receipts table.
	"""
	frappe.db.delete(
		"Inbound Shipment Purchase Receipt",
		{"parent": shipment_name, "receipt_document": pr_name}
	)
	frappe.db.set_value(
		"Inbound Shipment", shipment_name,
		"modified", frappe.utils.now(),
		update_modified=False
	)

# ------------------------------------------------------------------ #
# Whitelisted query — item_code search filtered to a PO               #
# ------------------------------------------------------------------ #

@frappe.whitelist()
def get_po_items_for_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom search query for item_code in package_items.
	Returns items from a specific Purchase Order's line items.
	Called by frm.set_query with query: path.to.function.
	"""
	purchase_order = filters.get("purchase_order")
	if not purchase_order:
		return []

	return frappe.db.sql(
		"""
		SELECT poi.item_name, poi.item_code, poi.description, poi.uom
		FROM `tabPurchase Order Item` poi
		WHERE poi.parent = %(purchase_order)s
			AND (
			poi.item_code LIKE %(txt)s
			OR poi.item_name LIKE %(txt)s
			)
		ORDER BY poi.item_code
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"purchase_order": purchase_order,
			"txt":      f"%{txt}%",
			"page_len": page_len,
			"start":    start,
		},
	)


@frappe.whitelist()
def get_po_item_details(purchase_order, item_code):
	"""
	Returns ordered qty, UOM and weight for a specific item in a PO.
	Called from JS when item_code is selected on a package item row.
	"""
	result = frappe.db.get_value(
		"Purchase Order Item",
		{"parent": purchase_order, "item_code": item_code},
		["qty", "uom", "weight_per_unit"],
		as_dict=True,
	)
	return result or {}


@frappe.whitelist()
def get_shipment_purchase_receipts(shipment_name):
	shipment = frappe.get_doc("Inbound Shipment", shipment_name)
	if not shipment.purchase_receipts:
		frappe.throw(_(f"Inbound Shipment <b>{shipment_name}</b> has no linked Purchase Receipts."))
	return [
		{
			"receipt_document":       row.receipt_document,
			"supplier":               row.supplier,
			"grand_total":            row.grand_total,
		}
		for row in shipment.purchase_receipts
	]


@frappe.whitelist()
def get_shipment_summary(shipment_name):
	s = frappe.db.get_value(
		"Inbound Shipment",
		shipment_name,
		["shipment_status", "shipping_date", "shipping_mode", "carrier",
 		"total_packages", "total_chargeable_weight", "total_freight_charges",
 		"company", "docstatus"],
		as_dict=True,
	)
	if not s:
		frappe.throw(_(f"Inbound Shipment {shipment_name} not found."))

	s["status"] = s.pop("shipment_status")
	s["pr_count"] = frappe.db.count(
	"Inbound Shipment Purchase Receipt", {"parent": shipment_name}
	)
	return s


@frappe.whitelist()
def get_item_weights_from_shipment(shipment_name):
	"""F
	Enterprise Logic:
	Allocates a package's chargeable weight to its items based on their net weight contribution.
	"""
	# 1. Get Packages (The source of Chargeable Weight)
	packages = frappe.get_all(
		"Inbound Shipment Package",
		filters={"parent": shipment_name},
		fields=["package_number", "chargeable_weight"]
	)
	pkg_chargeable_map = {p.package_number: flt(p.chargeable_weight) for p in packages}

	# 2. Get Package Items (The consumers of weight)
	package_items = frappe.get_all(
		"Inbound Shipment Package Item",
		filters={"parent": shipment_name},
		fields=["package_number", "purchase_order", "item_code", "net_weight"]
	)

	# 3. Sum total Net Weight per package to calculate the ratio
	pkg_total_net_weight = {}
	for pi in package_items:
		pkg = pi.package_number
		pkg_total_net_weight[pkg] = pkg_total_net_weight.get(pkg, 0) + flt(pi.net_weight)

	# 4. Allocate Chargeable weight to (PO + Item)
	# Result format: { "PO-123||ITEM-001": 45.5 }
	allocated_weights = {}
	for pi in package_items:
		pkg = pi.package_number
		total_pkg_net = flt(pkg_total_net_weight.get(pkg, 0))
		pkg_chargeable = flt(pkg_chargeable_map.get(pkg, 0))

		if total_pkg_net > 0:
			# Item's weight = (Item Net / Total Pkg Net) * Package Chargeable Weight
			item_share = (flt(pi.net_weight) / total_pkg_net) * pkg_chargeable
			
			key = f"{pi.purchase_order}||{pi.item_code}"
			allocated_weights[key] = flt(allocated_weights.get(key, 0) + item_share, 3)

	return allocated_weights


@frappe.whitelist()
def get_item_net_weights_from_shipment(shipment_name):
	"""Return aggregated item net weight from shipment package items.

	Result format: { "PO-123||ITEM-001": 12.345 }
	"""
	package_items = frappe.get_all(
		"Inbound Shipment Package Item",
		filters={"parent": shipment_name},
		fields=["purchase_order", "item_code", "net_weight"],
		ignore_permissions=True,
	)

	net_weights = {}
	for pi in package_items:
		key = f"{pi.purchase_order}||{pi.item_code}"
		net_weights[key] = flt(net_weights.get(key, 0) + flt(pi.net_weight), 3)

	return net_weights

@frappe.whitelist()
def validate_and_link_pr_to_shipment(pr_name, shipment_name):
	"""
	Validates a PR-to-shipment link then performs it.
	Called from the Purchase Receipt form button.

	Validation rules:
	1. Shipment must be submitted and not cancelled
	2. PR must be submitted
	3. PR must not already be linked to any shipment
	4. At least one PR item's purchase_order must be in the shipment's PO table
	5. Every PR item's purchase_order (if set) must be in the shipment's PO table
	6. Every PR item's item_code must exist in the shipment's package_items for that PO
	"""
	# --- Guard: shipment state ---
	shipment = frappe.db.get_value(
		"Inbound Shipment", shipment_name,
		["docstatus", "company", "shipment_status"],
		as_dict=True
	)
	if not shipment:
		frappe.throw(_(f"Inbound Shipment <b>{shipment_name}</b> not found."))
	if shipment.docstatus != 1:
		frappe.throw(
			_(f"Inbound Shipment <b>{shipment_name}</b> must be submitted "
			f"before linking Purchase Receipts.")
		)

	# --- Guard: PR state ---
	pr = frappe.get_doc("Purchase Receipt", pr_name)
	if pr.docstatus != 1:
		frappe.throw(
			_(f"Purchase Receipt <b>{pr_name}</b> must be submitted.")
		)
	if pr.custom_inbound_shipment:
		frappe.throw(
			_(f"Purchase Receipt <b>{pr_name}</b> is already linked to "
			f"Inbound Shipment <b>{pr.custom_inbound_shipment}</b>. "
			f"Unlink it first by cancelling the PR.")
		)
	if pr.company != shipment.company:
		frappe.throw(
			_(f"Purchase Receipt <b>{pr_name}</b> belongs to company "
			f"<b>{pr.company}</b>, not <b>{shipment.company}</b>.")
		)

	# --- Guard: already in child table ---
	if frappe.db.exists(
		"Inbound Shipment Purchase Receipt",
		{"parent": shipment_name, "receipt_document": pr_name}
	):
		frappe.throw(
			_(f"Purchase Receipt <b>{pr_name}</b> is already in the "
			f"purchase receipts table of <b>{shipment_name}</b>.")
		)

	# --- Build shipment PO set and package item map ---
	shipment_pos = {
		r.purchase_order
		for r in frappe.get_all(
			"Inbound Shipment Purchase Order",
			filters={"parent": shipment_name},
			fields=["purchase_order"]
		)
		if r.purchase_order
	}

	# Map (purchase_order, item_code) -> total expected qty from package items
	pkg_items = frappe.db.sql(
		"""
		SELECT purchase_order, item_code, SUM(qty) AS total_qty
		FROM `tabInbound Shipment Package Item`
		WHERE parent = %(shipment)s
			AND purchase_order IS NOT NULL
			AND item_code IS NOT NULL
		GROUP BY purchase_order, item_code
		""",
		{"shipment": shipment_name},
		as_dict=True,
	)
	pkg_item_map = {
		(r.purchase_order, r.item_code): flt(r.total_qty)
		for r in pkg_items
	}

	# --- Validate each PR item ---
	pr_pos = set()
	warnings = []

	for item in pr.items:
		if not item.purchase_order:
			continue

		pr_pos.add(item.purchase_order)

		# PO must be in the shipment
		if item.purchase_order not in shipment_pos:
			frappe.throw(
				_(f"PR item row #{item.idx}: Purchase Order "
				f"<b>{item.purchase_order}</b> is not in Inbound Shipment "
				f"<b>{shipment_name}</b>. Add it to the shipment first.")
			)

		# Item must be in the package items for this PO
		key = (item.purchase_order, item.item_code)
		if key not in pkg_item_map:
			frappe.throw(
				_(f"PR item row #{item.idx}: Item <b>{item.item_code}</b> "
				f"from PO <b>{item.purchase_order}</b> is not found in the "
				f"package items of <b>{shipment_name}</b>.")
			)

		# Warn if PR qty exceeds expected package qty
		expected = pkg_item_map[key]
		if flt(item.qty) > expected:
			warnings.append(
				f"Item <b>{item.item_code}</b> from PO <b>{item.purchase_order}</b>: "
				f"PR qty {item.qty} exceeds expected shipment qty {expected}."
			)

	# At least one PR item must belong to a shipment PO
	if not pr_pos:
		frappe.throw(
			_(f"No items in Purchase Receipt <b>{pr_name}</b> have a "
			f"Purchase Order set. Cannot link to a shipment.")
		)

	if pr_pos.isdisjoint(shipment_pos):
		frappe.throw(
			_(f"None of the Purchase Orders in <b>{pr_name}</b> are "
			f"linked to Inbound Shipment <b>{shipment_name}</b>.")
		)

	# --- Link: set field on PR and add to child table ---
	frappe.db.set_value(
		"Purchase Receipt", pr_name, "custom_inbound_shipment", shipment_name
	)
	_add_pr_to_shipment(pr_name, shipment_name)

	result = {"success": True, "warnings": warnings}
	return result


@frappe.whitelist()
def get_shipments_filtered_by_pos(doctype, txt, searchfield, start, page_len, filters):
	pos = filters.get("pos")
	company = filters.get("company")

	# This SQL finds Shipments that are submitted, match company, 
	# and have at least one row in their 'purchase_orders' table matching the PR's POs.
	return frappe.db.sql(
		"""
		SELECT DISTINCT s.name, s.shipping_mode, s.shipper_name, s.carrier, s.shipment_status
		FROM `tabInbound Shipment` s
		JOIN `tabInbound Shipment Purchase Order` spo ON s.name = spo.parent
		WHERE s.docstatus = 1
			AND s.company = %(company)s
			AND spo.purchase_order IN %(pos)s
			AND (s.name LIKE %(txt)s OR s.shipper_name LIKE %(txt)s OR s.carrier LIKE %(txt)s)
		ORDER BY s.creation DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"company": company,
			"pos": pos,
			"txt": f"%{txt}%",
			"page_len": page_len,
			"start": start
		}
	)


@frappe.whitelist()
def get_shipments_search(doctype, txt, searchfield, start, page_len, filters):
	company = (filters or {}).get("company")

	return frappe.db.sql(
		"""
		SELECT
			s.name,
			s.shipper_name,
			s.carrier,
			s.shipping_mode,
			s.shipment_status
		FROM `tabInbound Shipment` s
		WHERE s.docstatus = 1
			AND (%(company)s IS NULL OR s.company = %(company)s)
			AND (
				s.name LIKE %(txt)s
				OR IFNULL(s.shipper_name, '') LIKE %(txt)s
				OR IFNULL(s.carrier, '') LIKE %(txt)s
				OR IFNULL(s.shipping_mode, '') LIKE %(txt)s
				OR IFNULL(s.shipment_status, '') LIKE %(txt)s
			)
		ORDER BY s.creation DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"company": company,
			"txt": f"%{txt}%",
			"page_len": page_len,
			"start": start,
		},
	)

@frappe.whitelist()
def get_pr_items_purchase_orders(pr_item_names):
	"""
	Given a list of Purchase Receipt Item names, return a dict
	mapping { pr_item_name: purchase_order }.
	"""
	if not pr_item_names:
		return {}

	# In some client calls (esp. lists/arrays), args may arrive as a JSON string.
	# Normalize to a real Python list before using it in an "in" filter.
	try:
		pr_item_names = frappe.parse_json(pr_item_names)
	except Exception:
		pass

	if not pr_item_names:
		return {}
	
	items = frappe.db.get_all(
		"Purchase Receipt Item",
		filters={"name": ["in", pr_item_names]},
		fields=["name", "purchase_order"],
		ignore_permissions=True,
	)
	
	return {item.name: item.purchase_order for item in items}