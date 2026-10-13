# NBS Customization — review standards

## Login page (`nbs_customization/www/login.html`)

- The two-column login is fixed at `100dvh` with `overflow: hidden` on
  desktop **by design**. Do not flag clipping or missing scrollbars:
  the supported configuration (one or two login providers, normal
  desktop viewports) always fits, and a desktop scrollbar is an
  explicit UX rejection. Mobile (`<=768px`) keeps normal flow.
- `Back to website` stays visible but disabled until Website is set up.
- Auth markup (input IDs, section classes, `login.js` include) must stay
  byte-compatible with stock Frappe login.

## Navigation (`nbs_customization/setup.py`)

- Sidebar placements write to `Custom Sidebar` site layers only, never to
  shipped `Sidebar` docs or ERPNext/Frappe files. Admin and per-user rows
  are never removed or reordered — only `NBS_MANAGED_LABELS` rows are
  managed, and `NBS_RETIRED_LABELS` tracks removals.
- Dock renames are static single-language title overrides sourced from
  site Translation records; they intentionally do not switch per language.
