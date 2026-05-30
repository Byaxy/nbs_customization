__version__ = "0.0.1"

# Monkey-patch print_designer's Browser.prepare_options_for_pdf to fix
# double-counted bottom margin. footer_height (measured from the footer page)
# already includes marginBottom (via footerHeightWithMargin), but the CSS
# margin-bottom is added again, shrinking the body page and causing footer
# content to be cut/split on multi-page PDFs.

try:
	from print_designer.pdf_generator.browser import Browser as _Browser

	_original_prepare_options_for_pdf = _Browser.prepare_options_for_pdf

	def _patched_prepare_options_for_pdf(self):
		_original_prepare_options_for_pdf(self)
		if self.is_print_designer and self.footer_page:
			margin_top_px = self._get_converted_num(self.options.get("margin-top", 0))
			margin_bottom_px = self._get_converted_num(self.options.get("margin-bottom", 0))
			extra_px = margin_top_px + margin_bottom_px
			if extra_px:
				from print_designer.print_designer.page.print_designer.print_designer import (
					convert_uom,
				)
				extra_in = convert_uom(extra_px, "px", "in", only_number=True)
				self.body_page.options["paperHeight"] += extra_in

	_Browser.prepare_options_for_pdf = _patched_prepare_options_for_pdf
except ImportError:
	pass
