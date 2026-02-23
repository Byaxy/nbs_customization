frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		add_linked_document_buttons(frm);

		if (!frm.doc.customer) return;
		if (frm.doc.per_delivered >= 100) return;

		frm.add_custom_button(__("Check Pending Loan Waybills"), () =>
			check_pending_loans(frm),
		).addClass("btn-danger");
	},
});

function add_linked_document_buttons(frm) {
	if (!frm.doc.custom_customer_delivery_note) {
		frm.add_custom_button(
			__("Customer Delivery Note"),
			() => create_linked_doc(frm, "Customer Delivery Note"),
			__("Create"),
		);
	}

	if (!frm.doc.custom_promissory_note) {
		frm.add_custom_button(
			__("Promissory Note"),
			() => create_linked_doc(frm, "Promissory Note"),
			__("Create"),
		);
	}
}

function create_linked_doc(frm, doctype) {
	const method =
		doctype === "Customer Delivery Note"
			? "nbs_customization.controllers.sales_order.create_customer_delivery_note_from_sales_order"
			: "nbs_customization.controllers.sales_order.create_promissory_note_from_sales_order";

	frappe.call({
		method,
		args: {
			sales_order: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Creating {0}...", [doctype]),
		callback: (r) => {
			if (!r.message) return;
			frappe.set_route("Form", doctype, r.message);
		},
	});
}

function check_pending_loans(frm) {
	frappe.call({
		method: "nbs_customization.controllers.sales_order.get_pending_loan_waybills",
		args: {
			sales_order: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Checking pending loan waybills..."),
		callback(r) {
			const data = r.message;

			if (!data || !data.loan_waybills || !data.loan_waybills.length) {
				frappe.msgprint({
					title: __("No Pending Loans"),
					message: __(
						"No matching pending loan waybills were found for this Sales Order.",
					),
					indicator: "green",
				});
				return;
			}

			show_loan_selection_dialog(frm, data);
		},
	});
}

function show_loan_selection_dialog(frm, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Pending Loan Waybills"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "context_info",
			},
			{
				fieldtype: "Section Break",
			},
			{
				fieldname: "loan_table",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Convert Selected"),
		primary_action() {
			const selected = get_selected_loan(dialog);

			if (!selected) {
				frappe.msgprint(__("Please select a Loan Waybill to convert."));
				return;
			}

			dialog.hide();
			open_conversion_dialog(frm, selected);
		},
	});

	dialog.show();

	render_context_info(dialog, data);
	render_loan_table(frm, dialog, data.loan_waybills, data.customer);
}

function render_context_info(dialog, data) {
	const wrapper = dialog.fields_dict.context_info.$wrapper;

	wrapper.html(`
		<div style="margin-bottom: 10px;">
			<strong>${__("Customer")}: </strong> ${data.customer}<br>
			<strong>${__("Sales Order")}: </strong>
			<a href="/app/sales-order/${data.sales_order}" target="_blank">
				${data.sales_order}
			</a>
		</div>
	`);

	// store full payload
	dialog.context_data = data;
}

function render_loan_table(frm, dialog, loan_waybills, customer) {
	const wrapper = dialog.fields_dict.loan_table.$wrapper;

	let html = `
		<div class="table-responsive">
			<table class="table table-bordered table-hover">
				<thead>
					<tr>
						<th style="width:40px;"></th>
						<th>${__("Loan Date")}</th>
						<th>${__("Loan Waybill")}</th>
						<th>${__("Total Qnty Supplied")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	loan_waybills.forEach((loan, i) => {
		const total_items = loan.items.reduce((total, item) => total + item.qty_loaned, 0);

		html += `
			<tr class="loan-row" data-index="${i}" style="cursor:pointer;">
				<td>
					<input type="radio" name="loan_select" class="loan-select" data-index="${i}">
				</td>
				<td>${frappe.datetime.str_to_user(loan.loan_date)}</td>
				<td>
					<a href="/app/loan-waybill/${loan.loan_waybill}" target="_blank">
						${loan.loan_waybill}
					</a>
				</td>
				<td>${total_items}</td>
			</tr>
		`;
	});

	html += `</tbody></table></div>`;

	wrapper.html(html);
	dialog.loan_waybills = loan_waybills;

	wrapper.find(".loan-row").on("click", function (e) {
		// ignore clicks on radio button itself
		if ($(e.target).is("input")) return;

		const index = $(this).data("index");
		const loan = dialog.loan_waybills[index];

		show_loan_detail_dialog(frm, loan, customer);
	});
}

function show_loan_detail_dialog(frm, loan, customer) {
	const dialog = new frappe.ui.Dialog({
		title: __("Loan Waybill Details: {0}", [loan.loan_waybill]),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "context_info" },
			{ fieldtype: "Section Break" },
			{ fieldtype: "HTML", fieldname: "items_table" },
		],
	});

	dialog.show();

	render_loan_detail_context(dialog, loan, customer);
	render_loan_items_table(dialog, loan.items);
}

function render_loan_detail_context(dialog, loan, customer) {
	const wrapper = dialog.fields_dict.context_info.$wrapper;

	wrapper.html(`
		<div style="margin-bottom:10px">
			<strong>${__("Loan Waybill")}:</strong> ${loan.loan_waybill}<br>
			<strong>${__("Customer")}:</strong> ${customer}<br>
			<strong>${__("Loan Date")}:</strong>
			${frappe.datetime.str_to_user(loan.loan_date)}
		</div>
	`);
}

function render_loan_items_table(dialog, items) {
	const wrapper = dialog.fields_dict.items_table.$wrapper;

	let html = `
		<div class="table-responsive">
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("PID")}</th>
						<th>${__("Description")}</th>
						<th >${__("Qty Supplied")}</th>
						<th >${__("Qty Converted")}</th>
						<th >${__("Qty Remaining")}</th>
						<th >${__("Max Convertible")}</th>
						<th>${__("Batch No.")}</th>
						<th>${__("Serial No.")}</th>
						<th>${__("Expiry")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	items.forEach((it) => {
		html += `
			<tr>
				<td>${it.item_code}</td>
				<td>${it.description}</td>
				<td>${it.qty_loaned}</td>
				<td>${it.qty_converted}</td>
				<td>${it.qty_remaining}</td>
				<td class="text-bold" style="background-color: #f8f9fa; color: #007bff;">${it.max_convertible_qty || 0}</td>
				<td>${it.batch_no || ""}</td>
				<td>${it.serial_no || ""}</td>
				<td>${it.expiry_date || ""}</td>
			</tr>
		`;
	});

	html += `</tbody></table></div>`;

	wrapper.html(html);
}

function get_selected_loan(dialog) {
	const selected_radio = dialog.$wrapper.find(".loan-select:checked");

	if (!selected_radio.length) return null;

	const index = selected_radio.data("index");
	return dialog.loan_waybills[index];
}

function open_conversion_dialog(frm, loan) {
	const dialog = new frappe.ui.Dialog({
		title: __("Convert Loan Waybill: {0}", [loan.loan_waybill]),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "context_info" },
			{ fieldtype: "Section Break" },
			{ fieldtype: "HTML", fieldname: "conversion_table" },
		],
		primary_action_label: __("Create Conversion Waybill"),
		primary_action() {
			const payload = collect_conversion_data(dialog, loan);

			if (!payload.items.length) {
				frappe.msgprint(__("Enter at least one quantity to convert."));
				return;
			}

			dialog.hide();
			create_draft_delivery_note(frm, loan, payload);
		},
	});

	dialog.show();

	render_conversion_context(dialog, loan, frm.doc.customer);
	render_conversion_table(dialog, loan.items);
}

function render_conversion_context(dialog, loan, customer) {
	const wrapper = dialog.fields_dict.context_info.$wrapper;

	wrapper.html(`
		<div style="margin-bottom:10px">
			<strong>${__("Loan Waybill")}:</strong> ${loan.loan_waybill}<br>
			<strong>${__("Customer")}:</strong> ${customer}<br>
			<strong>${__("Loan Date")}:</strong>
			${frappe.datetime.str_to_user(loan.loan_date)}
		</div>
	`);
}

function render_conversion_table(dialog, items) {
	const wrapper = dialog.fields_dict.conversion_table.$wrapper;

	let html = `
		<div class="table-responsive">
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th>${__("Batch")}</th>
						<th>${__("Serial")}</th>
						<th>${__("Loan Remaining")}</th>
						<th>${__("SO Remaining")}</th>
						<th>${__("Max Convertible")}</th>
						<th style="width:140px">${__("Convert Qty")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	items.forEach((it, i) => {
		html += `
			<tr>
				<td>${it.item_code}</td>
				<td>${it.batch_no || ""}</td>
				<td>${it.serial_no || ""}</td>
				<td class="loan-remaining" data-index="${i}">
					${it.qty_remaining}
				</td>
				<td class="so-remaining" data-index="${i}">
					${it.so_qty_remaining || 0}
				</td>
				<td class="text-bold" style="background-color: #f8f9fa; color: #007bff;" data-index="${i}">
					${it.max_convertible_qty || 0}
				</td>
				<td>
					<input
						type="number"
						min="0"
						max="${it.max_convertible_qty || 0}"
						step="0.01"
						class="form-control convert-input"
						data-index="${i}"
					>
				</td>
			</tr>
		`;
	});

	html += `</tbody></table></div>`;

	wrapper.html(html);

	// 🔒 Prevent over-conversion in real time
	wrapper.find(".convert-input").on("input", function () {
		const max = parseFloat($(this).attr("max")) || 0;
		let val = parseFloat($(this).val()) || 0;

		if (val > max) {
			val = max;
			$(this).val(max);

			frappe.show_alert({
				message: __("Cannot convert more than maximum convertible quantity."),
				indicator: "orange",
			});
		}

		if (val < 0) {
			$(this).val(0);
		}
	});
}

function collect_conversion_data(dialog, loan) {
	const items = [];

	dialog.$wrapper.find(".convert-input").each(function () {
		const qty = parseFloat($(this).val()) || 0;
		if (!qty) return;

		const index = $(this).data("index");
		const src = loan.items[index];

		items.push({
			item_code: src.item_code,
			qty: qty,
			batch_no: src.batch_no,
			serial_no: src.serial_no,
			warehouse: src.warehouse,
			expiry_date: src.expiry_date,
			loan_waybill: loan.loan_waybill,
			stock_entry_detail: src.stock_entry_detail,
		});
	});

	return { items };
}

function create_draft_delivery_note(frm, loan, payload) {
	frappe.call({
		method: "nbs_customization.controllers.sales_order.create_delivery_note_from_loan",
		args: {
			sales_order: frm.doc.name,
			loan_waybill: loan.loan_waybill,
			items: payload.items,
		},
		freeze: true,
		freeze_message: __("Creating Waybill..."),
		callback(r) {
			if (!r.message) return;

			// Redirect to Draft Waybill
			frappe.set_route("Form", "Delivery Note", r.message);
		},
	});
}
