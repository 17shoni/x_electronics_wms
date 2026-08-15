# Copyright (c) 2026, Victor Musyoni Mutua and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, nowtime

from x_electronics_wms.x_electronics_wms.utils.stock import get_stock_position

VALID_STOCK_ENTRY_TYPES = ("Receipt", "Consume", "Transfer")


class StockEntry(Document):
    def before_validate(self):
        self.set_posting_datetime()

    def validate(self):
        self.validate_transaction_type()
        self.validate_warehouses()
        self.validate_items()

    def before_submit(self):
        self.prepare_valuation()

    def on_submit(self):
        self.create_stock_ledger_entries()

    def before_cancel(self):
        self.validate_cancellation()

    def on_cancel(self):
        self.cancel_stock_ledger_entries()

    def set_posting_datetime(self):
        """Set posting date and time when they have not been provided."""
        if not self.posting_date:
            self.posting_date = nowdate()

        if not self.posting_time:
            self.posting_time = nowtime()

    def validate_transaction_type(self):
        """Ensure only supported stock transaction types are used."""
        if self.stock_entry_type not in VALID_STOCK_ENTRY_TYPES:
            frappe.throw(
                _("Stock Entry Type must be Receipt, Consume, or Transfer.")
            )

    def validate_warehouses(self):
        """Validate warehouse requirements for each transaction type."""
        if self.stock_entry_type == "Receipt":
            if not self.to_warehouse:
                frappe.throw(_("To Warehouse is required for a Receipt."))

            if self.from_warehouse:
                frappe.throw(
                    _("From Warehouse must be empty for a Receipt.")
                )

            self.validate_stock_warehouse(self.to_warehouse)

        elif self.stock_entry_type == "Consume":
            if not self.from_warehouse:
                frappe.throw(
                    _("From Warehouse is required for a Consume entry.")
                )

            if self.to_warehouse:
                frappe.throw(
                    _("To Warehouse must be empty for a Consume entry.")
                )

            self.validate_stock_warehouse(self.from_warehouse)

        elif self.stock_entry_type == "Transfer":
            if not self.from_warehouse:
                frappe.throw(
                    _("From Warehouse is required for a Transfer.")
                )

            if not self.to_warehouse:
                frappe.throw(
                    _("To Warehouse is required for a Transfer.")
                )

            if self.from_warehouse == self.to_warehouse:
                frappe.throw(
                    _("From Warehouse and To Warehouse cannot be the same.")
                )

            self.validate_stock_warehouse(self.from_warehouse)
            self.validate_stock_warehouse(self.to_warehouse)

    def validate_stock_warehouse(self, warehouse):
        """Ensure stock is posted only to enabled leaf warehouses."""
        warehouse_details = frappe.db.get_value(
            "Warehouse",
            warehouse,
            ["warehouse_name", "is_group", "disabled"],
            as_dict=True,
        )

        if not warehouse_details:
            frappe.throw(
                _("Warehouse {0} does not exist.").format(warehouse)
            )

        if warehouse_details.disabled:
            frappe.throw(
                _("Warehouse {0} is disabled.").format(
                    warehouse_details.warehouse_name
                )
            )

        if warehouse_details.is_group:
            frappe.throw(
                _(
                    "Warehouse {0} is a group warehouse and cannot hold stock."
                ).format(warehouse_details.warehouse_name)
            )

    def validate_items(self):
        """Validate Stock Entry Item rows."""
        if not self.items:
            frappe.throw(_("At least one item is required."))

        seen_items = set()

        for row in self.items:
            if not row.item:
                frappe.throw(
                    _("Item is required in row {0}.").format(row.idx)
                )

            if row.item in seen_items:
                frappe.throw(
                    _("Item {0} appears more than once.").format(row.item)
                )

            seen_items.add(row.item)

            if flt(row.qty) <= 0:
                frappe.throw(
                    _("Quantity must be greater than zero in row {0}.").format(
                        row.idx
                    )
                )

            item_details = frappe.db.get_value(
                "Item",
                row.item,
                ["item_name", "disabled"],
                as_dict=True,
            )

            if not item_details:
                frappe.throw(
                    _("Item {0} does not exist.").format(row.item)
                )

            if item_details.disabled:
                frappe.throw(
                    _("Item {0} is disabled.").format(row.item)
                )

            if self.stock_entry_type == "Receipt":
                if flt(row.incoming_rate) <= 0:
                    frappe.throw(
                        _(
                            "Incoming Rate must be greater than zero "
                            "for item {0}."
                        ).format(row.item)
                    )


    def prepare_valuation(self):
        """
        calculates valuation rate and amount before submission.
        we implemented receipt first.
        """
        for row in self.items:
            qty = flt(row.qty)

            if self.stock_entry_type == "Receipt":
                row.valuation_rate = flt(row.incoming_rate)
                row.amount = flt(row.qty) * flt(row.valuation_rate)

            elif self.stock_entry_type in ("Consume", "Transfer"):
                stock_position = get_stock_position(
                    row.item,
                    self.from_warehouse,
                )

                available_qty = flt(stock_position["qty"])
                valuation_rate = flt(stock_position["valuation_rate"])

                if available_qty <= 0:
                    frappe.throw(
                        (
                            "No stock is available for items {0} "
                            "in warehouse {1}."
                        ).format(
                            row.item,
                            self.from_warehouse,
                        )
                    )

                if qty > available_qty:
                    frappe.throw(
                        (
                            "Insufficient stock for item {0} in warehouse {1}."
                            "Available quantity is {2}, but {3} was requested."

                        ).format(
                            row.item,
                            self.from_warehouse,
                            available_qty,
                            qty,
                        )
                    )

                row.valuation_rate = valuation_rate
                row.amount = qty * valuation_rate


    def create_stock_ledger_entries(self):
        """
        creates stock ledger entries for the stock entry.
        we implement receipt first.
        """
        if self.stock_entry_type == "Receipt":
           self.create_receipt_ledger_entries()

        elif self.stock_entry_type == "Consume":
            self.create_consume_ledger_entries()

        elif self.stock_entry_type == "Transfer":
            self.create_transfer_ledger_entries()

    def create_receipt_ledger_entries(self):
        for row in self.items:
            qty = flt(row.qty)
            valuation_rate = flt(row.valuation_rate)
            stock_value_difference = qty * valuation_rate

            ledger_entry = frappe.get_doc(
                {
                    "doctype": "Stock Ledger Entry",
                    "posting_date": self.posting_date,
                    "posting_time": self.posting_time,
                    "item": row.item,
                    "warehouse": self.to_warehouse,
                    "actual_qty": qty,
                    "valuation_rate": valuation_rate,
                    "stock_value_difference": stock_value_difference,
                    "voucher_type": "Stock Entry",
                    "voucher_no": self.name,
                    "voucher_detail_no": row.name,
                    "is_cancelled": 0,
                }
            )

            ledger_entry.insert(ignore_permissions=True)

    def create_consume_ledger_entries(self):
        """
        creates negative Stock Ledger Entries for consumed stock.
        """
        for row in self.items:
            qty = flt(row.qty)
            valuation_rate = flt(row.valuation_rate)

            stock_value_difference = qty * valuation_rate

            ledger_entry = frappe.get_doc(
                {
                    "doctype": "Stock Ledger Entry",
                    "posting_date": self.posting_date,
                    "posting_time":self.posting_time,
                    "item": row.item,
                    "warehouse": self.from_warehouse,
                    "actual_qty": -qty,
                    "valuation_rate": valuation_rate,
                    "stock_value_difference": -stock_value_difference,
                    "voucher_type": "Stock Entry",
                    "voucher_no": self.name,
                    "voucher_detail_no": row.name,
                    "is_cancelled": 0, 
                }
            )

            ledger_entry.insert(ignore_permissions=True)

    def create_transfer_ledger_entries(self):
        """
        creates two Stock ledger entries for a warehouse transfer
        from the source warehouse we remove items
        to the source warehouse we add items
        """

        for row in self.items:
            qty = flt(row.qty)
            valuation_rate = flt(row.valuation_rate)
            stock_value = qty * valuation_rate

            # items leaving the source warehouse

            source_ledger_entry = frappe.get_doc(
                {
                    "doctype": "Stock Ledger Entry",
                    "posting_date": self.posting_date,
                    "posting_time": self.posting_time,
                    "item": row.item,
                    "warehouse": self.from_warehouse,
                    "actual_qty": -qty,
                    "valuation_rate": valuation_rate,
                    "stock_value_difference": -stock_value,
                    "voucher_type": "Stock Entry",
                    "voucher_no": self.name,
                    "voucher_detail_no": row.name,
                    "is_cancelled": 0,
                }
            )

            source_ledger_entry.insert(ignore_permissions=True)

            # same items entering the destination warehouse

            destination_ledger_entry = frappe.get_doc(
                {
                    "doctype": "Stock Ledger Entry",
                    "posting_date": self.posting_date,
                    "posting_time": self.posting_time,
                    "item": row.item,
                    "warehouse": self.to_warehouse,
                    "actual_qty": qty,
                    "valuation_rate": valuation_rate,
                    "stock_value_difference": stock_value,
                    "voucher_type": "Stock Entry",
                    "voucher_no": self.name,
                    "voucher_detail_no": row.name,
                    "is_cancelled": 0,
                }
            )

            destination_ledger_entry.insert(ignore_permissions=True)

    def get_active_stock_ledger_entries(self):
        """
        returns active stock ledger entries that are created by this stock entry.
        """
        return frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": self.name,
                "is_cancelled": 0,
            },
            fields=[
                "name",
                "item",
                "warehouse",
                "creation",
            ],
            order_by="creation asc",
        )

    def validate_cancellation(self):
        # prevents cancellation when stock movements exist.

        ledger_entries = self.get_active_stock_ledger_entries()

        if not ledger_entries:
            frappe.throw(
                (
                    "No active Stock Ledger Entries exist"
                    "for Stock Entry {0}."
                ).format(self.name)
            )

        for ledger_entry in ledger_entries:
            later_entry = frappe.db.exists(
                "Stock Ledger Entry",
                {
                    "item": ledger_entry.item,
                    "warehouse": ledger_entry.warehouse,
                    "is_cancelled": 0,
                    "creation": [">", ledger_entry.creation],
                    "voucher_no": ["!=", self.name],
                },
            )

            if later_entry:
                later_voucher = frappe.db.get_value(
                    "Stock Ledger Entry",
                    later_entry,
                    "voucher_no"
                )

                frappe.throw(
                    (
                        "Cannot cancel Stock Entry {0} because a later "
                        "stock movement ({1}) exists for item {2} "
                        "in warehouse {3}. Cancel later transactions first."
                    ).format(
                        self.name,
                        later_voucher,
                        ledger_entry.item,
                        ledger_entry.warehouse,
                    )
                )


    def cancel_stock_ledger_entries(self):

        # Marks this Stock Entry's ledger movements as cancelled

        ledger_entries = self.get_active_stock_ledger_entries()

        for ledger_entry in ledger_entries:
            frappe.db.set_value(
                "Stock Ledger Entry",
                ledger_entry.name,
                "is_cancelled",
                1,
                update_modified=False,
            )
       