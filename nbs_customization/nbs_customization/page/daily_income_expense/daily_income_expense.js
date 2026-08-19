frappe.pages["daily_income_expense"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Daily Income and Expense"),
		single_column: true,
	});
	const page = wrapper.page;
	const $filters = $('<div class="daily-ie-filters"></div>').appendTo(page.main);
	const $body = $('<div class="daily-ie-body"></div>').appendTo(page.main);

	const controls = {};

	function is_valid_date(value) {
		return /^\d{4}-\d{2}-\d{2}$/.test(value) && !isNaN(new Date(value).getTime());
	}

	const url_date = frappe.utils.get_url_arg("report_date");
	const url_company = frappe.utils.get_url_arg("company");
	const default_date = is_valid_date(url_date) ? url_date : frappe.datetime.get_today();
	const default_company = url_company || frappe.defaults.get_user_default("Company");

	const filter_df = [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: default_company,
		},
		{
			fieldname: "report_date",
			label: __("Date"),
			fieldtype: "Date",
			default: default_date,
		},
	];

	let initializing = true;

	filter_df.forEach((df) => {
		const $wrap = $('<div class="daily-ie-filter"></div>').appendTo($filters);
		const control = frappe.ui.form.make_control({
			df: {
				...df,
				reqd: 1,
				onchange: () => {
					if (!initializing) {
						load();
						update_url();
					}
				},
			},
			parent: $wrap,
			render_input: true,
			only_input: true,
		});
		control.refresh();
		controls[df.fieldname] = control;
	});

	controls.company.set_value(filter_df[0].default);
	controls.report_date.set_value(filter_df[1].default);
	initializing = false;

	function update_url() {
		const company = controls.company.get_value();
		const report_date = controls.report_date.get_value();
		const qs = frappe.utils.make_query_string({ company, report_date });
		window.history.replaceState(null, "", location.pathname + (qs === "?" ? "" : qs));
	}

	load();
	update_url();

	async function load() {
		const company = controls.company.get_value();
		const report_date = controls.report_date.get_value();
		if (!company || !report_date) {
			return;
		}

		const res = await frappe.call({
			method: "nbs_customization.nbs_customization.page.daily_income_expense.daily_income_expense.get_data",
			args: { company, report_date },
		});
		if (res.message) {
			render(res.message);
		}
	}

	function render(data) {
		$body.empty();
		render_cards(data);
		render_cash_bank_table(data);
		render_pnl_table(data, "income", __("Income"), __("Total Income"), [
			{ label: __("Voucher No"), render: (row) => voucher_link(row) },
			{ label: __("Date"), render: (row) => row.posting_date || "" },
			{ label: __("Party / Payee"), render: (row) => row.party || "" },
			{ label: __("Mode of Payment"), render: (row) => row.mode_of_payment || "" },
			{ label: __("Linked Invoice"), render: (row) => row.linked_invoice || "" },
			{
				label: __("Amount"),
				align: "right",
				render: (row) => amount(row.amount, data.currency),
			},
		]);
		render_pnl_table(data, "expenses", __("Expenses"), __("Total Expenses"), [
			{ label: __("Voucher No"), render: (row) => voucher_link(row) },
			{ label: __("Type"), render: (row) => row.type || "" },
			{ label: __("Date"), render: (row) => row.posting_date || "" },
			{ label: __("Party / Payee"), render: (row) => row.party || "" },
			{ label: __("Mode of Payment"), render: (row) => row.mode_of_payment || "" },
			{ label: __("Linked Ref"), render: (row) => row.linked_invoice || "" },
			{
				label: __("Amount"),
				align: "right",
				render: (row) => amount(row.amount, data.currency),
			},
		]);
	}

	function voucher_link(row) {
		if (!row.voucher_type || !row.voucher_no) {
			return $("<span></span>").text(row.voucher_no || "");
		}
		return $("<a></a>")
			.attr("href", frappe.utils.get_form_link(row.voucher_type, row.voucher_no))
			.text(row.voucher_no);
	}

	function render_cards(data) {
		const $cards = $('<div class="daily-ie-cards"></div>').appendTo($body);
		[
			{
				label: __("Net Income (Loss)"),
				value: data.net,
				css: data.net < 0 ? "text-danger" : "text-success",
			},
			{
				label: __("Total Income"),
				value: data.income.total,
				css: "text-success",
			},
			{
				label: __("Total Expenses"),
				value: data.expenses.total,
				css: "text-danger",
			},
			{
				label: __("Cash & Bank Carried Forward"),
				value: data.cash_bank_total.carried_forward,
				css: "daily-ie-cash",
			},
		].forEach((card) => {
			const $card = $('<div class="daily-ie-card"></div>').appendTo($cards);
			$card.append(`<div class="daily-ie-card-label">${card.label}</div>`);
			const $value = $(
				`<div class="daily-ie-card-value ${card.css}">${amount(card.value, data.currency)}</div>`,
			);
			$card.append($value);
			$card.css("border-left-color", getComputedStyle($value[0]).color);
		});
	}

	function render_cash_bank_table(data) {
		const $section = $('<div class="daily-ie-section"></div>').appendTo($body);
		$section.append(`<h3>${__("Cash & Bank Balances")}</h3>`);

		const $wrap = $('<div class="daily-ie-table-wrap"></div>').appendTo($section);
		const $table = $('<table class="table daily-ie-table"></table>').appendTo($wrap);
		$("<thead></thead>")
			.appendTo($table)
			.append(
				$("<tr></tr>")
					.append($("<th></th>").text(__("Account")))
					.append($('<th class="text-right"></th>').text(__("Brought Forward")))
					.append($('<th class="text-right"></th>').text(__("Day Movement")))
					.append($('<th class="text-right"></th>').text(__("Carried Forward")))
					.append($("<th></th>").text(__("Currency"))),
			);

		const $tbody = $("<tbody></tbody>").appendTo($table);
		(data.accounts || []).forEach((row) => {
			$("<tr></tr>")
				.append($("<td></td>").text(row.account))
				.append(
					$('<td class="text-right"></td>').text(
						amount(row.brought_forward, row.currency),
					),
				)
				.append(
					$('<td class="text-right"></td>').text(amount(row.day_movement, row.currency)),
				)
				.append(
					$('<td class="text-right"></td>').text(
						amount(row.carried_forward, row.currency),
					),
				)
				.append($("<td></td>").text(row.currency))
				.appendTo($tbody);
		});

		const total = data.cash_bank_total;
		$("<tr></tr>")
			.addClass("daily-ie-total")
			.append($("<td></td>").text(__("Total Cash & Bank")))
			.append(
				$('<td class="text-right"></td>').text(
					amount(total.brought_forward, data.currency),
				),
			)
			.append(
				$('<td class="text-right"></td>').text(amount(total.day_movement, data.currency)),
			)
			.append(
				$('<td class="text-right"></td>').text(
					amount(total.carried_forward, data.currency),
				),
			)
			.append($("<td></td>").text(data.currency))
			.appendTo($tbody);
	}

	function render_pnl_table(data, key, title, total_label, columns) {
		const $section = $('<div class="daily-ie-section"></div>').appendTo($body);
		$section.append(`<h3>${title} — ${data.date_label}</h3>`);

		const $wrap = $('<div class="daily-ie-table-wrap"></div>').appendTo($section);
		const $table = $('<table class="table daily-ie-table"></table>').appendTo($wrap);
		$("<thead></thead>")
			.appendTo($table)
			.append(
				$("<tr></tr>").append(
					columns.map((col) => {
						const $th = $("<th></th>").text(col.label);
						if (col.align === "right") {
							$th.addClass("text-right");
						}
						return $th;
					}),
				),
			);

		const $tbody = $("<tbody></tbody>").appendTo($table);
		(data[key].rows || []).forEach((row) => {
			$("<tr></tr>")
				.append(
					columns.map((col) => {
						const $td = $("<td></td>");
						if (col.align === "right") {
							$td.addClass("text-right");
						}
						$td.append(col.render(row));
						return $td;
					}),
				)
				.appendTo($tbody);
		});

		$("<tr></tr>")
			.addClass("daily-ie-total")
			.append($("<td></td>").text(total_label))
			.append(columns.slice(1, -1).map(() => $("<td></td>")))
			.append($('<td class="text-right"></td>').text(amount(data[key].total, data.currency)))
			.appendTo($tbody);
	}

	function amount(value, currency) {
		return format_currency(value, currency);
	}

	load();
};
