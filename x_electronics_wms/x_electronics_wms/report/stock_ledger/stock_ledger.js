// Copyright (c) 2026, Victor Musyoni Mutua and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Ledger"] = {
	"filters": [
		{
			fielname: "from_date",
			label: _("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: _("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "item",
			label: _("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "warehouse",
			label: _("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
};
