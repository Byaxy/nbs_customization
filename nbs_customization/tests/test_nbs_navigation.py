import frappe
from frappe.boot import get_module_sidebars
from frappe.desk.doctype.sidebar.sidebar import ShellIndex, get_navigable_modules
from frappe.tests import IntegrationTestCase

from nbs_customization.setup import NBS_RETIRED_LABELS, NBS_SIDEBAR_PLACEMENTS, _site_layer_name

LEGACY_SIDEBAR = "NBS Customization"
EXPECTED_HEIRS = ["Selling", "Buying", "Stock", "Assets", "Accounts", "Setup"]
LEGACY_DOCTYPES = {"Test Panel Group"}


class TestNBSNavigation(IntegrationTestCase):
	def test_legacy_sidebar_removed(self):
		if frappe.db.exists("DocType", "Workspace Sidebar"):
			self.assertFalse(frappe.db.exists("Workspace Sidebar", LEGACY_SIDEBAR))

		self.assertFalse(frappe.db.exists("Sidebar", LEGACY_SIDEBAR))
		self.assertTrue(frappe.db.exists("Module Def", LEGACY_SIDEBAR))

	def test_nbs_module_is_code_only(self):
		hooks = frappe.get_hooks("code_only_modules")
		self.assertEqual(hooks.get(LEGACY_SIDEBAR), EXPECTED_HEIRS)
		self.assertNotIn(LEGACY_SIDEBAR, get_navigable_modules())
		self.assertNotIn(LEGACY_SIDEBAR, get_module_sidebars())

	def test_module_sidebars_keep_nbs_links(self):
		for module, spec in NBS_SIDEBAR_PLACEMENTS.items():
			layer = _site_layer_name(module)
			self.assertTrue(layer, f"Missing site sidebar layer for {module}")

			rows = frappe.get_all(
				"Sidebar Item",
				filters={"parenttype": "Custom Sidebar", "parent": layer},
				fields=["label", "link_type", "link_to"],
			)
			present = {(row.label, row.link_type, row.link_to) for row in rows}
			missing = [row[0] for row in spec if (row[0], row[2], row[1]) not in present]
			self.assertFalse(missing, f"{module} is missing NBS links: {missing}")

	def test_stock_sidebar_drops_retired_placement_items(self):
		layer = _site_layer_name("Stock")
		rows = frappe.get_all(
			"Sidebar Item",
			filters={"parenttype": "Custom Sidebar", "parent": layer},
			fields=["label", "child"],
		)
		labels = {row.label for row in rows}
		stale = sorted(labels & NBS_RETIRED_LABELS)
		self.assertFalse(stale, f"Stock sidebar still has retired rows: {stale}")

		analyzer_type = next(row for row in rows if row.label == "Analyzer Type")
		profile = next(row for row in rows if row.label == "Analyzer Profile")
		self.assertEqual(analyzer_type.child, 1)
		self.assertEqual(profile.child, 1)

	def test_nbs_entities_resolve_to_expected_sidebars(self):
		index = ShellIndex(get_module_sidebars())
		expected = {
			("DocType", "Loan Waybill"): "Selling",
			("DocType", "Promissory Note"): "Selling",
			("DocType", "Instrument Placement Contract"): "Assets",
			("DocType", "Desk Theme"): "Setup",
			("Report", "Cheques in Transit"): "Accounts",
			("Report", "Daily Income and Expense"): "Accounts",
			("Report", "Item Pricing Tier Lookup"): "Selling",
			("Page", "daily_income_expense"): "Accounts",
		}

		for (kind, entity), shell in expected.items():
			self.assertEqual(index.resolve(kind, entity, LEGACY_SIDEBAR), shell, f"{kind} {entity}")

		for kind, entity in self._nbs_entities():
			self.assertIsNotNone(index.resolve(kind, entity, LEGACY_SIDEBAR), f"{kind} {entity}")

	def test_every_nbs_entity_has_sidebar_placement(self):
		placed = {(row[2], row[1]) for rows in NBS_SIDEBAR_PLACEMENTS.values() for row in rows}
		missing = sorted(self._nbs_entities() - placed)
		self.assertFalse(missing, f"NBS entities missing sidebar placement: {missing}")

	def _nbs_entities(self):
		doctypes = frappe.get_all(
			"DocType",
			filters={"module": LEGACY_SIDEBAR, "istable": 0},
			pluck="name",
		)
		doctypes = [name for name in doctypes if name not in LEGACY_DOCTYPES]
		reports = frappe.get_all("Report", filters={"module": LEGACY_SIDEBAR}, pluck="name")
		pages = frappe.get_all("Page", filters={"module": LEGACY_SIDEBAR}, pluck="name")

		return (
			{("DocType", name) for name in doctypes}
			| {("Report", name) for name in reports}
			| {("Page", name) for name in pages}
		)
