import frappe
from frappe.utils import flt


def get_stock_position(item, warehouse):
    """
    returns the current quantity, stock value, and moving-average
    valuation rate for an Item in a Warehouse.
    """

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(actual_qty), 0) AS qty,
            COALESCE(SUM(stock_value_difference), 0) AS stock_value
        FROM `tabStock Ledger Entry`
        WHERE
            item = %s
            AND warehouse = %s
            AND IFNULL(is_cancelled, 0) = 0
        """,
        (item, warehouse),
        as_dict=True,
    )[0]

    qty = flt(result.qty)
    stock_value = flt(result.stock_value)

    valuation_rate = stock_value / qty if qty else 0

    return {
        "qty": qty,
        "stock_value": stock_value,
        "valuation_rate": valuation_rate,
    }
