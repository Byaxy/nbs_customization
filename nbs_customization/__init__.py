__version__ = "0.0.1"

# PDF pipeline adjustments live in nbs_customization.pdf_patch (applied via
# before_request). No print_designer patches here: that app is not installed,
# and any future footer/body height compensation must be reviewed together
# with pdf_patch Patch 2 to avoid double-counting page margins.
