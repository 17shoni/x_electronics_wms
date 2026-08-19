import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("as_on_date"):
        filters.as_on_date = nowdate()

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Item"),
            "fieldname": "item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 200,
        },
        {
            "label": _("Balance Qty"),
            "fieldname": "balance_qty",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": _("Stock Value"),
            "fieldname": "stock_value",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "label": _("Valuation Rate"),
            "fieldname": "valuation_rate",
            "fieldtype": "Currency",
            "width": 160,
        },
    ]


def get_data(filters):
    conditions = [
        "IFNULL(is_cancelled, 0) = 0",
        "posting_date <= %(as_on_date)s",
    ]

    values = {
        "as_on_date": getdate(filters.as_on_date),
    }

    if filters.get("item"):
        conditions.append("item = %(item)s")
        values["item"] = filters.item

    warehouse_names = []

    if filters.get("warehouse"):
        warehouse_names = get_warehouse_names(
            filters.warehouse,
            filters.get("consolidate"),
        )

        if not warehouse_names:
            return []

        warehouse_placeholders = []

        for index, warehouse_name in enumerate(warehouse_names):
            key = f"warehouse_{index}"
            warehouse_placeholders.append(f"%({key})s")
            values[key] = warehouse_name

        conditions.append(
            "warehouse IN ({})".format(
                ", ".join(warehouse_placeholders)
            )
        )

    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            item,
            warehouse,
            SUM(actual_qty) AS balance_qty,
            SUM(stock_value_difference) AS stock_value
        FROM `tabStock Ledger Entry`
        WHERE {where_clause}
        GROUP BY
            item,
            warehouse
        ORDER BY
            item,
            warehouse
        """,
        values,
        as_dict=True,
    )

    if filters.get("warehouse") and filters.get("consolidate"):
        return consolidate_balances(
            rows,
            filters.warehouse,
        )

    return prepare_balances(rows)


def get_warehouse_names(warehouse, consolidate):
    """
    Return the selected warehouse.

    When consolidation is enabled, return all leaf warehouses
    contained below the selected warehouse in the warehouse tree.
    """
    if not consolidate:
        return [warehouse]

    warehouse_details = frappe.db.get_value(
        "Warehouse",
        warehouse,
        ["lft", "rgt"],
        as_dict=True,
    )

    if not warehouse_details:
        return []

    warehouses = frappe.db.sql(
        """
        SELECT name
        FROM `tabWarehouse`
        WHERE
            lft >= %(lft)s
            AND rgt <= %(rgt)s
            AND IFNULL(is_group, 0) = 0
        ORDER BY lft
        """,
        {
            "lft": warehouse_details.lft,
            "rgt": warehouse_details.rgt,
        },
        as_dict=True,
    )

    return [row.name for row in warehouses]


def prepare_balances(rows):
    data = []

    for row in rows:
        qty = flt(row.balance_qty)
        stock_value = flt(row.stock_value)

        if not qty and not stock_value:
            continue

        valuation_rate = (
            stock_value / qty
            if qty
            else 0
        )

        data.append(
            {
                "item": row.item,
                "warehouse": row.warehouse,
                "balance_qty": qty,
                "stock_value": stock_value,
                "valuation_rate": valuation_rate,
            }
        )

    return data


def consolidate_balances(rows, selected_warehouse):
    """
    Combine balances from child warehouses and display them
    against the selected parent warehouse.
    """
    consolidated = {}

    for row in rows:
        if row.item not in consolidated:
            consolidated[row.item] = {
                "qty": 0,
                "value": 0,
            }

        consolidated[row.item]["qty"] += flt(
            row.balance_qty
        )
        consolidated[row.item]["value"] += flt(
            row.stock_value
        )

    data = []

    for item, balance in consolidated.items():
        qty = flt(balance["qty"])
        stock_value = flt(balance["value"])

        if not qty and not stock_value:
            continue

        valuation_rate = (
            stock_value / qty
            if qty
            else 0
        )

        data.append(
            {
                "item": item,
                "warehouse": selected_warehouse,
                "balance_qty": qty,
                "stock_value": stock_value,
                "valuation_rate": valuation_rate,
            }
        )

    return data