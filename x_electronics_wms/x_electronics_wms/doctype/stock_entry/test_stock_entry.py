# Copyright (c) 2026, Victor Musyoni Mutua and Contributors
# See license.txt

from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from x_electronics_wms.x_electronics_wms.utils.stock import (
    get_stock_position,
)


class TestStockEntry(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        # Give every test unique Item and Warehouse names.
        # This prevents duplicate-key errors between test runs.
        self.test_id = uuid4().hex[:8].upper()

        self.item = self.create_test_item()

        self.root_warehouse = self.create_test_root_warehouse()

        self.main_warehouse = self.create_test_warehouse(
            f"_Test Main Store {self.test_id}",
            self.root_warehouse,
        )

        self.destination_warehouse = self.create_test_warehouse(
            f"_Test Destination Store {self.test_id}",
            self.root_warehouse,
        )

    def create_test_item(self):
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": f"_TEST-ITEM-{self.test_id}",
                "item_name": f"Test Laptop {self.test_id}",
                "stock_uom": "Nos",
                "disabled": 0,
            }
        )

        item.insert(ignore_permissions=True)

        return item.name

    def create_test_root_warehouse(self):
        warehouse = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": f"_Test All Warehouses {self.test_id}",
                "is_group": 1,
                "disabled": 0,
            }
        )

        warehouse.insert(ignore_permissions=True)

        return warehouse.name

    def create_test_warehouse(
        self,
        warehouse_name,
        parent_warehouse,
    ):
        warehouse = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": warehouse_name,
                "parent_warehouse": parent_warehouse,
                "is_group": 0,
                "disabled": 0,
            }
        )

        warehouse.insert(ignore_permissions=True)

        return warehouse.name

    def create_receipt(
        self,
        qty,
        incoming_rate,
    ):
        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Receipt",
                "to_warehouse": self.main_warehouse,
                "items": [
                    {
                        "item": self.item,
                        "qty": qty,
                        "incoming_rate": incoming_rate,
                    }
                ],
            }
        )

        stock_entry.insert(ignore_permissions=True)
        stock_entry.submit()

        return stock_entry

    def create_consume(
        self,
        qty,
        submit=True,
    ):
        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Consume",
                "from_warehouse": self.main_warehouse,
                "items": [
                    {
                        "item": self.item,
                        "qty": qty,
                    }
                ],
            }
        )

        stock_entry.insert(ignore_permissions=True)

        if submit:
            stock_entry.submit()

        return stock_entry

    def create_transfer(
        self,
        qty,
        submit=True,
    ):
        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Transfer",
                "from_warehouse": self.main_warehouse,
                "to_warehouse": self.destination_warehouse,
                "items": [
                    {
                        "item": self.item,
                        "qty": qty,
                    }
                ],
            }
        )

        stock_entry.insert(ignore_permissions=True)

        if submit:
            stock_entry.submit()

        return stock_entry

    def test_receipt_creates_stock(self):
        initial_qty = 10
        incoming_rate = 100

        receipt = self.create_receipt(
            qty=initial_qty,
            incoming_rate=incoming_rate,
        )

        ledger_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": receipt.name,
                "is_cancelled": 0,
            },
            fields=[
                "actual_qty",
                "valuation_rate",
                "stock_value_difference",
                "warehouse",
            ],
        )

        self.assertEqual(
            len(ledger_entries),
            1,
        )

        ledger_entry = ledger_entries[0]

        expected_stock_value = (
            initial_qty * incoming_rate
        )

        self.assertEqual(
            ledger_entry.warehouse,
            self.main_warehouse,
        )

        self.assertAlmostEqual(
            ledger_entry.actual_qty,
            initial_qty,
        )

        self.assertAlmostEqual(
            ledger_entry.valuation_rate,
            incoming_rate,
        )

        self.assertAlmostEqual(
            ledger_entry.stock_value_difference,
            expected_stock_value,
        )

        stock_position = get_stock_position(
            self.item,
            self.main_warehouse,
        )

        self.assertAlmostEqual(
            stock_position["qty"],
            initial_qty,
        )

        self.assertAlmostEqual(
            stock_position["stock_value"],
            expected_stock_value,
        )

        self.assertAlmostEqual(
            stock_position["valuation_rate"],
            incoming_rate,
        )

    def test_consume_uses_moving_average(self):
        first_receipt_qty = 10
        first_receipt_rate = 100

        second_receipt_qty = 10
        second_receipt_rate = 200

        consume_qty = 4

        self.create_receipt(
            qty=first_receipt_qty,
            incoming_rate=first_receipt_rate,
        )

        self.create_receipt(
            qty=second_receipt_qty,
            incoming_rate=second_receipt_rate,
        )

        consume = self.create_consume(
            qty=consume_qty,
        )

        ledger_entry = frappe.get_value(
            "Stock Ledger Entry",
            {
                "voucher_type": "Stock Entry",
                "voucher_no": consume.name,
                "is_cancelled": 0,
            },
            [
                "actual_qty",
                "valuation_rate",
                "stock_value_difference",
            ],
            as_dict=True,
        )

        first_value = (
            first_receipt_qty
            * first_receipt_rate
        )

        second_value = (
            second_receipt_qty
            * second_receipt_rate
        )

        total_qty_before_consume = (
            first_receipt_qty
            + second_receipt_qty
        )

        total_value_before_consume = (
            first_value
            + second_value
        )

        expected_valuation_rate = (
            total_value_before_consume
            / total_qty_before_consume
        )

        expected_consumed_value = (
            consume_qty
            * expected_valuation_rate
        )

        self.assertAlmostEqual(
            ledger_entry.actual_qty,
            -consume_qty,
        )

        self.assertAlmostEqual(
            ledger_entry.valuation_rate,
            expected_valuation_rate,
        )

        self.assertAlmostEqual(
            ledger_entry.stock_value_difference,
            -expected_consumed_value,
        )

        stock_position = get_stock_position(
            self.item,
            self.main_warehouse,
        )

        expected_remaining_qty = (
            total_qty_before_consume
            - consume_qty
        )

        expected_remaining_value = (
            total_value_before_consume
            - expected_consumed_value
        )

        self.assertAlmostEqual(
            stock_position["qty"],
            expected_remaining_qty,
        )

        self.assertAlmostEqual(
            stock_position["stock_value"],
            expected_remaining_value,
        )

        self.assertAlmostEqual(
            stock_position["valuation_rate"],
            expected_valuation_rate,
        )

    def test_consume_rejects_insufficient_stock(self):
        available_qty = 5
        incoming_rate = 100
        requested_qty = 6

        self.create_receipt(
            qty=available_qty,
            incoming_rate=incoming_rate,
        )

        consume = self.create_consume(
            qty=requested_qty,
            submit=False,
        )

        with self.assertRaises(
            frappe.ValidationError
        ):
            consume.submit()

        ledger_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": consume.name,
                "is_cancelled": 0,
            },
        )

        self.assertEqual(
            len(ledger_entries),
            0,
        )

        stock_position = get_stock_position(
            self.item,
            self.main_warehouse,
        )

        self.assertAlmostEqual(
            stock_position["qty"],
            available_qty,
        )

        self.assertAlmostEqual(
            stock_position["stock_value"],
            available_qty * incoming_rate,
        )

    def test_transfer_creates_two_ledger_entries(self):
        initial_qty = 10
        incoming_rate = 100
        transfer_qty = 3

        self.create_receipt(
            qty=initial_qty,
            incoming_rate=incoming_rate,
        )

        transfer = self.create_transfer(
            qty=transfer_qty,
        )

        ledger_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": transfer.name,
                "is_cancelled": 0,
            },
            fields=[
                "warehouse",
                "actual_qty",
                "valuation_rate",
                "stock_value_difference",
            ],
        )

        self.assertEqual(
            len(ledger_entries),
            2,
        )

        entries_by_warehouse = {
            row.warehouse: row
            for row in ledger_entries
        }

        source_entry = entries_by_warehouse[
            self.main_warehouse
        ]

        destination_entry = entries_by_warehouse[
            self.destination_warehouse
        ]

        expected_transfer_value = (
            transfer_qty * incoming_rate
        )

        self.assertAlmostEqual(
            source_entry.actual_qty,
            -transfer_qty,
        )

        self.assertAlmostEqual(
            source_entry.valuation_rate,
            incoming_rate,
        )

        self.assertAlmostEqual(
            source_entry.stock_value_difference,
            -expected_transfer_value,
        )

        self.assertAlmostEqual(
            destination_entry.actual_qty,
            transfer_qty,
        )

        self.assertAlmostEqual(
            destination_entry.valuation_rate,
            incoming_rate,
        )

        self.assertAlmostEqual(
            destination_entry.stock_value_difference,
            expected_transfer_value,
        )

    def test_transfer_preserves_total_stock(self):
        initial_qty = 10
        incoming_rate = 100
        transfer_qty = 3

        self.create_receipt(
            qty=initial_qty,
            incoming_rate=incoming_rate,
        )

        self.create_transfer(
            qty=transfer_qty,
        )

        source_position = get_stock_position(
            self.item,
            self.main_warehouse,
        )

        destination_position = get_stock_position(
            self.item,
            self.destination_warehouse,
        )

        expected_source_qty = (
            initial_qty - transfer_qty
        )

        expected_destination_qty = transfer_qty

        expected_source_value = (
            expected_source_qty
            * incoming_rate
        )

        expected_destination_value = (
            expected_destination_qty
            * incoming_rate
        )

        self.assertAlmostEqual(
            source_position["qty"],
            expected_source_qty,
        )

        self.assertAlmostEqual(
            source_position["stock_value"],
            expected_source_value,
        )

        self.assertAlmostEqual(
            destination_position["qty"],
            expected_destination_qty,
        )

        self.assertAlmostEqual(
            destination_position["stock_value"],
            expected_destination_value,
        )

        total_qty = (
            source_position["qty"]
            + destination_position["qty"]
        )

        total_value = (
            source_position["stock_value"]
            + destination_position["stock_value"]
        )

        self.assertAlmostEqual(
            total_qty,
            initial_qty,
        )

        self.assertAlmostEqual(
            total_value,
            initial_qty * incoming_rate,
        )

    def test_cancel_transfer_restores_stock(self):
        initial_qty = 10
        incoming_rate = 100
        transfer_qty = 3

        self.create_receipt(
            qty=initial_qty,
            incoming_rate=incoming_rate,
        )

        transfer = self.create_transfer(
            qty=transfer_qty,
        )

        transfer.cancel()

        ledger_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": transfer.name,
            },
            fields=[
                "warehouse",
                "actual_qty",
                "is_cancelled",
            ],
        )

        self.assertEqual(
            len(ledger_entries),
            2,
        )

        for ledger_entry in ledger_entries:
            self.assertEqual(
                ledger_entry.is_cancelled,
                1,
            )

        source_position = get_stock_position(
            self.item,
            self.main_warehouse,
        )

        destination_position = get_stock_position(
            self.item,
            self.destination_warehouse,
        )

        self.assertAlmostEqual(
            source_position["qty"],
            initial_qty,
        )

        self.assertAlmostEqual(
            source_position["stock_value"],
            initial_qty * incoming_rate,
        )

        self.assertAlmostEqual(
            destination_position["qty"],
            0,
        )

        self.assertAlmostEqual(
            destination_position["stock_value"],
            0,
        )

    def test_cannot_cancel_entry_with_later_stock_movement(
        self,
    ):
        receipt = self.create_receipt(
            qty=10,
            incoming_rate=100,
        )

        self.create_consume(
            qty=2,
        )

        with self.assertRaises(
            frappe.ValidationError
        ):
            receipt.cancel()

        receipt.reload()

        # docstatus 1 means Submitted.
        self.assertEqual(
            receipt.docstatus,
            1,
        )

        receipt_ledger_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_type": "Stock Entry",
                "voucher_no": receipt.name,
            },
            fields=[
                "is_cancelled",
            ],
        )

        self.assertEqual(
            len(receipt_ledger_entries),
            1,
        )

        self.assertEqual(
            receipt_ledger_entries[
                0
            ].is_cancelled,
            0,
        )