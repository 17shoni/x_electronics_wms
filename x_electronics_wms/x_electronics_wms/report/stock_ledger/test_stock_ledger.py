from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from x_electronics_wms.x_electronics_wms.report.stock_ledger.stock_ledger import (
    execute as stock_ledger_execute,
)

class TestStockLedgerReport(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        self.test_id = uuid4().hex[:8].upper()

        self.item = self.create_test_item()

        self.root_warehouse = self.create_test_root_warehouse()

        self.main_warehouse = self.create_test_warehouse(
            f"_Ledger Main Store {self.test_id}",
            self.root_warehouse,
        )

        self.destination_warehouse = self.create_test_warehouse(
            f"_Ledger Destination Store {self.test_id}",
            self.root_warehouse,
        )

    def create_test_item(self):
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": f"_LEDGER-ITEM-{self.test_id}",
                "item_name": f"Ledget Test Item {self.test_id}",
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
                "warehouse_name": (
                    f"_Ledger All Warehouses {self.test_id}"
                ),
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
        posting_date,
        posting_time,
    ):

        stock_entry = frappe.get_doc(
            {
                "doctype" : "Stock Entry",
                "stock_entry_type" : "Receipt",
                "posting_date": posting_date,
                "posting_time": posting_time,
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
        posting_date,
        posting_time,
    ):

        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Consume",
                "posting_date": posting_date,
                "posting_time": posting_time,
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
        stock_entry.submit()

        return stock_entry

    def create_transfer(
        self,
        qty,
        posting_date,
        posting_time,
    ):

        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Transfer",
                "posting_date": posting_date,
                "posting_time": posting_time,
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
        stock_entry.submit()

        return stock_entry

    def test_stock_ledger_running_balances(self):
        receipt = self.create_receipt(
            qty=10,
            incoming_rate=100,
            posting_date="2026-08-01",
            posting_time="09:00:00",
        )

        consume = self.create_consume(
            qty=4,
            posting_date="2026-08-02",
            posting_time="10:00:00",
        )

        transfer = self.create_transfer(
            qty=2,
            posting_date="2026-08-03",
            posting_time="11:00:00",
        )

        columns, data = stock_ledger_execute(
            {
                "from_date": "2026-08-01",
                "to_date": "2026-08-31",
                "item": self.item,
                "warehouse": self.main_warehouse,
            }
        )

        self.assertTrue(columns)

        self.assertEqual(
            len(data),
            3,
        )

        receipt_row = data[0]
        consume_row = data[1]
        transfer_row = data[2]

        #Receipt
        self.assertEqual(
            receipt_row["voucher_no"],
            receipt.name,
        )

        self.assertEqual(
            receipt_row["voucher_type"],
            "Stock Entry",
        )

        self.assertAlmostEqual(
            receipt_row["in_qty"],
            10,
        )

        self.assertAlmostEqual(
            receipt_row["out_qty"],
            0,
        )

        self.assertAlmostEqual(
            receipt_row["stock_value_difference"],
            1000,
        )

        self.assertAlmostEqual(
            receipt_row["balance_qty"],
            10,
        )

        self.assertAlmostEqual(
            receipt_row["balance_valuation_rate"],
            100,
        )

        #Consume

        self.assertEqual(
            consume_row["voucher_no"],
            consume.name,
        )

        self.assertAlmostEqual(
            consume_row["in_qty"],
            0,
        )

        self.assertAlmostEqual(
            consume_row["out_qty"],
            4,
        )

        self.assertAlmostEqual(
            consume_row["stock_value_difference"],
            -400,
        )

        self.assertAlmostEqual(
            consume_row["balance_qty"],
            6,
        )

        self.assertAlmostEqual(
            consume_row["balance_value"],
            600,
        )

        self.assertAlmostEqual(
            consume_row["balance_valuation_rate"],
            100,
        )

        #Transfer leaving the source warehouse

        self.assertEqual(
            transfer_row["voucher_no"],
            transfer.name,
        )

        self.assertAlmostEqual(
            transfer_row["in_qty"],
            0,
        )

        self.assertAlmostEqual(
            transfer_row["out_qty"],
            2,
        )

        self.assertAlmostEqual(
            transfer_row["stock_value_difference"],
            -200,
        )

        self.assertAlmostEqual(
            transfer_row["balance_qty"],
            4,
        )

        self.assertAlmostEqual(
            transfer_row["balance_valuation_rate"],
            100,
        )

        self.assertAlmostEqual(
            transfer_row["balance_value"],
            400,
        )

    def test_cancelled_entries_are_excluded(self):
        receipt = self.create_receipt(
            qty=10,
            incoming_rate=100,
            posting_date="2026-08-01",
            posting_time="09:00:00",
        )

        transfer = self.create_transfer(
            qty=2,
            posting_date="2026-08-02",
            posting_time="10:00:00",
        )

        transfer.cancel()

        columns, data = stock_ledger_execute(
            {
                "from_date": "2026-08-01",
                "to_date": "2026-08-31",
                "item": self.item,
                "warehouse": self.main_warehouse,
            }
        )

        self.assertTrue(columns)

        # Cancelled transfer should not appear

        self.assertEqual(
            len(data),
            1,
        )

        self.assertEqual(
            data[0]["voucher_no"],
            receipt.name,
        )

        self.assertEqual(
            data[0]["balance_qty"],
            10,
        )

        self.assertEqual(
            data[0]["balance_value"],
            1000,
        )

    def test_from_date_preserves_opening_balances(self):
        self.create_receipt(
            qty=10,
            incoming_rate=100,
            posting_date="2026-08-01",
            posting_time="09:00:00"
        )

        consume = self.create_consume(
            qty=4,
            posting_date="2026-08-05",
            posting_time="10:00:00",
        )

        columns, data = stock_ledger_execute(
            {
                "from_date": "2026-08-05",
                "to_date": "2026-08-31",
                "item": self.item,
                "warehouse": self.main_warehouse,
            }
        )

        self.assertTrue(columns)

        # only consume will be displayed because receipt occured before the from date

        self.assertEqual(
            len(data),
            1,
        )

        row = data[0]

        self.assertEqual(
            row["voucher_no"],
            consume.name,
        )

        self.assertAlmostEqual(
            row["out_qty"],
            4,
        )

        self.assertAlmostEqual(
            row["balance_qty"],
            6,
        )

        self.assertAlmostEqual(
            row["balance_valuation_rate"],
            100,
        )

        self.assertAlmostEqual(
            row["balance_value"],
            600,
        )







