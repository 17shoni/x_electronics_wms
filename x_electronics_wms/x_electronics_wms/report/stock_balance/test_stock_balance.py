from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from x_electronics_wms.x_electronics_wms.report.stock_balance.stock_balance import (
    execute as stock_balance_execute,
)

class TestStockBalanceReport(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administator")

        self.test_id = uuid4().hex[:8].upper()

        self.item = self.create_test_item()

        self.root_warehouse = self.create_test_warehouse(
            warehouse_name=f"_Balance All Warehouses {self.test_id}",
            parent_warehouse=None,
            is_group=1,
        )

        self.region_warehouse = self.create_test_warehouse(
            warehouse_name=f"_Balance Region {self.test_id}",
            parent_warehouse=self.root_warehouse,
            is_group=1,
        )

        self.main_warehouse = self.create_test_warehouse(
            warehouse_name=f"_Balance Main Store {self.test_id}",
            parent_warehouse=self.region_warehouse,
            is_group=0,
        )

        self.secondary_warehouse = self.create_test_warehouse(
            warehouse_name=f"_Balance Secondary Store {self.test_id}",
            parent_warehouse=self.region_warehouse,
            is_group=0,
        )

    def create_test_item(self):
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": f"_BALANCE-ITEM-{self.test_id}",
                "item_name": f"Balance Test Item {self.test_id}",
                "stock_uom": "Nos",
                "disabled": 0,
            }
        )

        item.insert(ignore_permissions=True)

        return item.name

    def create_test_warehouse(
        self,
        warehouse_name,
        parent_warehouse,
        is_group,
    ):
        warehouse = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": warehouse_name,
                "parent_warehouse": parent_warehouse,
                "is_group": is_group,
                "disabled": 0,
            }
        )

        warehouse.insert(ignore_permissions=True)

        return warehouse.name

    def create_receipt(
        self,
        warehouse,
        qty,
        incoming_rate,
        posting_date,
        posting_time,
    ):
        stock_entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Receipt",
                "posting_date": posting_date,
                "posting_time": posting_time,
                "to_warehouse": warehouse,
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
        warehouse,
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
                "from_warehouse": warehouse,
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
        from_warehouse,
        to_warehouse,
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
                "from_warehouse": from_warehouse,
                "to_warehouse": to_warehouse,
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


    def test_individual_warehouse_balances(self):
        initial_qty = 10
        incoming_rate = 100
        transfer_qty = 3

        self.create_receipt(
            warehouse=self.main_warehouse,
            qty=initial_qty,
            incoming_rate=incoming_rate,
            posting_date="2026-08-01",
            posting_time='09:00:00',
        )

        self.create_transfer(
            from_warehouse=self.main_warehouse,
            to_warehouse=self.secondary_warehouse,
            qty=transfer_qty,
            posting_date="2026-08-02",
            posting_time="10:00:00",
        )

        columns, data = stock_balance_execute(
            {
                "as_on_date": "2026-08-31",
                "item": self.item,
            }
        )

        self.assertTrue(columns)

        balances = {
            row["warehouse"]: row
            for row in data
        }

        self.assertIn(
            self.main_warehouse,
            balances,
        )

        self.assertIn(
            self.secondary_warehouse,
            balances,
        )

        main_balance = balances[
            self.main_warehouse
        ]

        secondary_balance = balances[
            self.secondary_warehouse
        ]

        expected_main_qty = (
            initial_qty - transfer_qty
        )

        expected_main_value = (
            expected_main_qty * incoming_rate
        )

        expected_secondary_value = (
            transfer_qty * incoming_rate
        )

        self.assertAlmostEqual(
            main_balance["balance_qty"],
            expected_main_qty,
        )

        self.assertAlmostEqual(
            main_balance["stock_value"],
            expected_main_value,
        )

        self.assertAlmostEqual(
            main_balance["valuation_rate"],
            incoming_rate,
        )

        self.assertAlmostEqual(
            secondary_balance["balance_qty"],
            transfer_qty,
        )

        self.assertAlmostEqual(
            secondary_balance["stock_value"],
            expected_secondary_value,
        )

        self.assertAlmostEqual(
            secondary_balance["valuation_rate"],
            incoming_rate,
        )

    
    def test_as_on_date_returns_historical_balance(self):
        initial_qty = 10
        incoming_rate = 100
        consume_qty = 4

        self.create_receipt(
            warehouse=self.main_warehouse,
            qty=initial_qty,
            incoming_rate=incoming_rate,
            posting_date="2026-08-01",
            posting_time="09:00:00",
        )

        self.create_consume(
            warehouse=self.main_warehouse,
            qty=consume_qty,
            posting_date="2026-08-10",
            posting_time="09:00:00"
        )

        columns, data = stock_balance_execute(
            {
                "as_on_date": "2026-08-05",
                "item": self.item,
                "warehouse": self.main_warehouse,
                "consolidate": 0,
            }
        )

        self.assertTrue(columns)

        self.assertEqual(
            len(data),
            1,
        )

        balance = data[0]

        # as consume date is on aug 10th and as on date is on 5th, we should still see originat receipt balance.

        self.assertEqual(
            balance["warehouse"],
            self.main_warehouse,
        )

        self.assertAlmostEqual(
            balance["balance_qty"],
            initial_qty,
        )

        self.assertAlmostEqual(
            balance["stock_value"],
            initial_qty * incoming_rate,
        )

        self.assertAlmostEqual(
            balance["valuation_rate"],
            incoming_rate,
        )


    def test_parent_warehouse_consolidation(self):
        initial_qty = 10
        incoming_rate = 100
        transfer_qty = 3

        self.create_receipt(
            warehouse=self.main_warehouse,
            qty=initial_qty,
            incoming_rate=incoming_rate,
            posting_date="2026-08-01",
            posting_time="09:00:00",
        )

        self.create_transfer(
            from_warehouse=self.main_warehouse,
            to_warehouse=self.secondary_warehouse,
            qty=transfer_qty,
            posting_date="2026-08-02",
            posting_time="10:00:00",
        )

        columns, data = stock_balance_execute(
            {
                "as_on_date": "2026-08-31",
                "item": self.item,
                "warehouse": self.region_warehouse,
                "consolidate": 1,
            }
        )

        self.assertTrue(columns)

        self.assertEqual(
            len(data),
            1,
        )

        consolidated_balance = data[0]

        self.assertEqual(
            consolidated_balance["warehouse"],
            self.region_warehouse,
        )

        # Main Store:
        # 10 - 3 = 7
        #
        # Secondary Store:
        # 3
        #
        # Consolidated total:
        # 7 + 3 = 10

        self.assertAlmostEqual(
            consolidated_balance["balance_qty"],
            initial_qty,
        )

        self.assertAlmostEqual(
            consolidated_balance["stock_value"],
            initial_qty * incoming_rate,
        )

        self.assertAlmostEqual(
            consolidated_balance["valuation_rate"],
            incoming_rate,
        )
