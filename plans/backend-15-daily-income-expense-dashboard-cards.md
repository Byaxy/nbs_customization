# B15 — Daily Income & Expense Dashboard: Insight Cards + Filter Alignment

**Depends on:** B14 (`daily_income_and_expense` report) and the dashboard Page `nbs_customization/nbs_customization/nbs_customization/page/daily_income_expense/` (frontend-only work — **no backend, report, test, or migrate changes**). All card values already come from the existing `get_data` payload (`net`, `income.total`, `expenses.total`, `cash_bank_total.carried_forward`).
**Provides:** A row of at-a-glance insight cards at the top of the dashboard (Net Income (Loss), Total Income, Total Expenses, Cash & Bank Carried Forward), replacing the Net Income footer line, plus a properly aligned Company + Date filter bar.

---

## Objective

The CEO opens the dashboard and wants the day's headline figures without scanning tables:

1. **Net Income (Loss)** as a card at the top (green when positive, red when negative) — it currently sits as a muted footer line.
2. **Two–three more at-a-glance cards** for the day. Confirmed set (user-approved):
   - **Total Income** — income recognized that day (green value)
   - **Total Expenses** — expenses that day (red value)
   - **Cash & Bank Carried Forward** — money on hand at end of day (navy value)
3. **Company and Date selectors well aligned** — both controls currently render via `page.add_field` with default widths/offsets, so labels and inputs don't share a clean lane.

---

## Design decisions (ui-design skill applied)

- **Minimalist; information on surfaces, not boxes.** Cards are light (`--bg-color`), `1px` `--border-color` border, `8px` radius — same language as the table wraps. No gradients/shadows. Color is used sparingly: only the **value** is tinted (green income, red expenses, navy cash, green/red net), never the card shell.
- **Clear hierarchy.** Small uppercase muted label + large bold value (restraint: label ≤12px is acceptable here — dense productivity UI).
- **Net Income is the centerpiece.** It leads the row and gets a subtle emphasis: `--control-bg` background + `4px` navy left accent. Other cards stay quiet.
- **Vertical lane alignment.** Each filter control is wrapped in an identical `min-width: 220px` column with label-above-input, so Company (Link) and Date inputs align on the same vertical lane and baseline.
- **No fake affordances.** (B15a) rows already use `cursor: default`; cards are informational, not links — no hover states.

---

## Changes

### `daily_income_expense.js`

1. **Filter bar rebuild** — replace the two `page.add_field(...)` calls with explicit, consistent markup:
   ```js
   const controls = {};
   const filter_df = [
     { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
       default: frappe.defaults.get_user_default("Company") },
     { fieldname: "report_date", label: __("Date"), fieldtype: "Date",
       default: frappe.datetime.get_today() },
   ];
   filter_df.forEach((df) => {
     const $wrap = $('<div class="daily-ie-filter"></div>').appendTo($filters);
     $wrap.append(`<label class="daily-ie-filter-label">${__(df.label)}</label>`);
     const control = frappe.ui.form.make_control({
       df: { ...df, reqd: 1, onchange: () => load() },
       parent: $wrap,
       render_input: true,
     });
     control.refresh();
     controls[df.fieldname] = control;
   });
   // apply defaults → one full load (company set first early-returns, date set triggers load)
   controls.company.set_value(filter_df[0].default);
   controls.report_date.set_value(filter_df[1].default);
   ```
   `load()` switches from `page.fields_dict.company` to `controls.company` / `controls.report_date`.

2. **Cards** — in `render()` call `render_cards(data)` **first** and drop `render_net_row(data)`; delete the `render_net_row` function entirely.
   ```js
   function render_cards(data) {
     const $cards = $('<div class="daily-ie-cards"></div>').appendTo($body);
     [
       { label: __("Net Income (Loss)"), value: data.net,
         css: data.net < 0 ? "text-danger" : "text-success", emphasis: true },
       { label: __("Total Income"), value: data.income.total, css: "text-success" },
       { label: __("Total Expenses"), value: data.expenses.total, css: "text-danger" },
       { label: __("Cash & Bank Carried Forward"), value: data.cash_bank_total.carried_forward,
         css: "daily-ie-cash" },
     ].forEach((card) => {
       const $card = $('<div class="daily-ie-card"></div>').appendTo($cards);
       if (card.emphasis) $card.addClass("daily-ie-card--net");
       $card.append(`<div class="daily-ie-card-label">${card.label}</div>`);
       $card.append(`<div class="daily-ie-card-value ${card.css}">${amount(card.value, data.currency)}</div>`);
     });
   }
   ```

### `daily_income_expense.css`

1. **Filters** — replace the flex `.daily-ie-filters` body with aligned columns:
   ```css
   .daily-ie-filters { display: flex; gap: 16px; align-items: flex-end; margin-bottom: 24px; }
   .daily-ie-filter { display: flex; flex-direction: column; gap: 4px; min-width: 220px; }
   .daily-ie-filter-label { font-size: 12px; font-weight: 600; color: var(--text-muted, #8d99a6);
     text-transform: uppercase; letter-spacing: 0.4px; }
   .daily-ie-filter .frappe-control { margin-bottom: 0; }
   ```
2. **Cards**:
   ```css
   .daily-ie-cards { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 28px; }
   .daily-ie-card { flex: 1 1 200px; min-width: 200px; padding: 16px;
     border: 1px solid var(--border-color, #d1d8dd); border-radius: 8px;
     background: var(--bg-color, #ffffff); }
   .daily-ie-card--net { border-left: 4px solid var(--nbs-table-header-bg, #001b52);
     background: var(--control-bg, #f4f5f6); }
   .daily-ie-card-label { font-size: 12px; font-weight: 600; color: var(--text-muted, #8d99a6);
     text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 8px; }
   .daily-ie-card-value { font-size: 1.6rem; font-weight: 700; line-height: 1.2; }
   .daily-ie-cash { color: var(--nbs-table-header-bg, #001b52); }
   ```
3. **Remove** the `.daily-ie-net` rule (footer line is gone).

---

## Verification

1. `cd apps/nbs_customization && npx prettier --check` on the JS + CSS (pre-commit uses prettier v2.7.1).
2. Browser (`agent-browser`, Administrator) on `http://nbsolutions.localhost:8000/app/daily_income_expense`:
   - Cards row renders above tables: **Net Income (Loss)**, **Total Income**, **Total Expenses**, **Cash & Bank Carried Forward** — values in `$`, net red for loss.
   - Today (18-08-2026): Net −100 (red), Income 0, Expenses 100, Cash & Bank CF 6,033.22.
   - Set date 11-08-2026: Net −100 (red), Income 0, Expenses 100, Cash & Bank CF 6,018.32.
   - Company + Date inputs share the same lane (computed `min-width`/layout check) and filter changes still drive the report.
   - No Net Income footer line remains.
3. Screenshot saved to `/tmp/opencode/dashboard_cards.png` for the record.

---

## Out of scope

- Backend/report/test/migrate changes (none needed — payload already carries all card values).
- Additional cards (Largest Expense, Transactions Today) — can be added later from the same payload.