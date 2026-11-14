# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.utils.placement.progress import apply_progress


class TestProgressAllocation(IntegrationTestCase):
	def test_shared_item_delivery_is_counted_once(self):
		lines = [
			frappe._dict(item_code="SHARED", qty_required_total=10),
			frappe._dict(item_code="SHARED", qty_required_total=10),
		]
		contract = frappe._dict(
			contract_reagent_lines=lines,
			contract_consumable_lines=[],
			is_new=lambda: False,
		)
		with patch(
			"nbs_customization.utils.placement.progress.delivered_by_item",
			return_value={"SHARED": 10},
		):
			apply_progress(contract)

		self.assertEqual(contract.progress_reagent_delivered, 10)
		self.assertEqual([line.delivered_qty for line in lines], [5, 5])
		self.assertEqual([line.remaining_qty for line in lines], [5, 5])

	def test_shared_item_over_delivery_allocates_full_quantity(self):
		lines = [
			frappe._dict(item_code="SHARED", qty_required_total=10),
			frappe._dict(item_code="SHARED", qty_required_total=5),
		]
		contract = frappe._dict(
			contract_reagent_lines=lines,
			contract_consumable_lines=[],
			is_new=lambda: False,
		)
		with patch(
			"nbs_customization.utils.placement.progress.delivered_by_item",
			return_value={"SHARED": 15},
		):
			apply_progress(contract)

		self.assertAlmostEqual(contract.progress_reagent_delivered, 15)
		self.assertAlmostEqual(sum(line.delivered_qty for line in lines), 15)
