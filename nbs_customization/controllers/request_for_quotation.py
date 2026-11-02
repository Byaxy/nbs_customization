"""
Overrides for the standard Request for Quotation DocType.
Stores the first supplier on the vendor header field so the standard
Supplier list column and filters show a value.
"""


def _set_vendor_from_first_supplier(doc):
	doc.vendor = doc.suppliers[0].supplier if doc.suppliers else None


def before_save(doc, method=None):
	_set_vendor_from_first_supplier(doc)


def before_submit(doc, method=None):
	_set_vendor_from_first_supplier(doc)
