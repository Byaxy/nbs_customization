import frappe


def apply_patches():
	from frappe.utils.pdf_generator.browser import Browser as _Browser

	if getattr(_Browser, "_nbs_patched", False):
		return
	_Browser._nbs_patched = True

	# --- Patch 1: set_html — inject body margin reset + prevent CSS/@page double-stacking ---
	_original_set_html = _Browser.set_html

	def _patched_set_html(self, html):
		_original_set_html(self, html)

		# Zero out body spacing that interferes with @page margins.
		# print.bundle.css contains body { padding: 15px; border-top: 2px solid ... }
		# with no @media guard, so they apply in print mode and add ~17px at the top.
		body_reset = self.soup.new_tag("style")
		body_reset.string = "body { margin: 0 !important; padding: 0 !important; border: none !important; }"
		self.soup.head.append(body_reset)

		# Prevent double-stacking: .print-format { margin-top: 10mm } from user CSS is
		# parsed BOTH as a @page margin (via printToPDF) AND applied as CSS on the div.
		# Inject at end of <body> (after user's <style> tag inside body) to override.
		reset = self.soup.new_tag("style")
		reset.string = ".print-format { margin: 0 !important; }"
		self.soup.body.append(reset)

		# Ensure a consistent gap (~5mm ≈ 20px) between body content and footer.
		# The desktop UI applies inline margin-top/padding via JS that doesn't run
		# in the PDF pipeline. This CSS targets #footer-html in the rendered footer
		# page (the soup <head> carries over via chrome_pdf_header_footer.html).
		footer_gap = self.soup.new_tag("style")
		footer_gap.string = "#footer-html { margin-top: 5mm !important; padding-top: 0 !important; }"
		self.soup.head.append(footer_gap)

	_Browser.set_html = _patched_set_html

	# --- Patch 2: prepare_options_for_pdf — fix footer height + body min-height ---
	_original_prepare_options = _Browser.prepare_options_for_pdf

	def _patched_prepare_options_for_pdf(self):
		_original_prepare_options(self)

		# 2a: Fix footer paperHeight to include margin_bottom
		if hasattr(self, "footer_page") and self.footer_page:
			fp = self.footer_page.options
			paper_height = fp.get("paperHeight", 0)
			margin_bottom = fp.get("marginBottom", 0)
			fp["paperHeight"] = paper_height + margin_bottom

	_Browser.prepare_options_for_pdf = _patched_prepare_options_for_pdf

	# --- Patch 3: print_designer pdf_header_footer_html — zero header wrapper padding, reduce footer ---
	try:
		import print_designer.pdf as _pd_pdf

		_original_hf = _pd_pdf.pdf_header_footer_html

		def _patched_pdf_header_footer_html(soup, head, content, styles, html_id, css):
			html = _original_hf(soup, head, content, styles, html_id, css)
			if html_id == "header-html":
				# Header: remove wrapper padding — only @page margin-top (from .print-format CSS)
				# should control top spacing. The template's 17mm padding stacks on top.
				extra_css = "<style>.wrapper { padding: 0 !important; }</style>"
				html = html.replace("</head>", extra_css + "</head>")
			elif html_id == "footer-html":
				extra_css = "<style>.wrapper { padding: 1mm 0 1mm !important; }</style>"
				html = html.replace("</head>", extra_css + "</head>")
			return html

		_pd_pdf.pdf_header_footer_html = _patched_pdf_header_footer_html
	except ImportError:
		pass
