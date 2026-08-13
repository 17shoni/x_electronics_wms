# Copyright (c) 2026, Victor Musyoni Mutua and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, nowtime


VALID_STOCK_ENTRY_TYPES = ("Receipt", "Consume", "Transfer")


class StockEntry(Document):
    def before_validate(self):
        self.set_posting_datetime()

    def validate(self):
        self.validate_transaction_type()
        self.validate_warehouses()
        self.validate_items()

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
