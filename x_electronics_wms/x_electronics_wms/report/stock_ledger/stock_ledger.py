# Copyright (c) 2026, Victor Musyoni Mutua and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)

	return columns, data

def get_columns():
	return[
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Posting Time"),
			"fieldname": "posting_time",
			"fieldtype": "Time",
			"width": 100, 
		},
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("In Qty"),
			"fieldname": "in_qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Out Qty"),
			"fieldname": "out_qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Stock Value Difference"),
			"fieldname": "stock_value_difference",
			"fieldtype": "Currency",
			"width": 160,
		},
		{
			"label": _("Balance Qty"),
			"fieldname": "balance_qty",
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"label": _("Balance Value"),
			"fieldname": "balance_value",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": _("Balance Valuation Rate"),
			"fieldname": "balance_valuation_rate",
			"fieldtype": "Currency",
			"width": 170,
		},
	]


def get_data(filters):
	conditions = [
		"IFNULL(is_cancelled, 0) = 0",
	]

	values = {}

	if filters.get("to_date"):
		condition.append("posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("item"):
		conditions.append("item = %(item)s")
		values["item"] = filters.item

	if filters.get("warehouse"):
		conditions.append("warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse

	where_clause = " AND ".join(conditions)

	ledger_entries = frappe.db.sql(
		f"""
		SELECT 
			name,
			posting_date,
			posting_time,
			item,
			warehouse,
			actual_qty,
			valuation_rate,
			stock_value_difference,
			voucher_type,
			voucher_no,
			creation
		FROM `tabStock Ledger Entry`
		WHERE {where_clause}
		ORDER BY
			item,
			warehouse,
			posting_date,
			posting_time,
			creation,
			name
		""",
		values,
		as_dict=True,
	)

	data = []
	balances = {}

	from_date = (
		getdate(filters.from_date)
		if filters.get("from_date")
		else None
	)

	for entry in ledger_entries:
		key = (entry.item, entry.warehouse)

		if key not in balances:
			balances[key] = {
				"qty": 0,
				"value": 0,
			}

		actual_qty = flt(entry.actual_qty)
		value_difference = flt(entry.stock_value_difference)

		balances[key]["qty"] += actual_qty
		balances[key]["value"] += value_difference

		balance_qty = balances[key]["qty"]
		balance_value = balances[key]["value"]

		balance_valuation_rate = (
			balance_value / balance_qty
			if balance_qty
			else 0
		)

		# Earlier entries still contribute to the running balance,
        # but are not displayed when a From Date filter is used.
		if from_date and getdate(entry.posting_date) < from_date:
			continue

		data.append(
			{
				"posting_date": entry.posting_date,
				"posting_time": entry.posting_time,
				"item": entry.item,
				"warehouse": entry.warehouse,
				"voucher_type": entry.voucher_type,
				"voucher_no": entry.voucher_no,
				"in_qty": actual_qty if actual_qty > 0 else 0,
				"out_qty": abs(actual_qty) if actual_qty < 0 else 0,
				"valuation_rate": flt(entry.valuation_rate),
				"stock_value_difference": value_difference,
				"balance_qty": balance_qty,
				"balance_value": balance_value,
				"balance_valuation_rate": balance_valuation_rate,
			}
		)

	return data
