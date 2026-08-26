// Copyright (c) 2026, Victor Musyoni Mutua and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry", {
    onload(frm) {
        set_posting_defaults(frm);
        update_items_table(frm);
    },

    refresh(frm) {
        update_items_table(frm);
    },

    stock_entry_type(frm) {
        clear_irrelevant_warehouses(frm);
        update_items_table(frm);
    },
});


function set_posting_defaults(frm) {
    //provides defaults when date and time has not been set.
    if (!frm.doc.posting_date) {
        frm.set_value("posting_date", frappe.datetime.get_today());
    }

    if (!frm.doc.posting_time) {
        frm.set_value("posting_time", frappe.datetime.now_time());
    }
}


function clear_irrelevant_warehouses(frm) {
    const entry_type = frm.doc.stock_entry_type;

    if (entry_type === "Receipt") {
        // Receipts only adds stock into a warehouse.
        if (frm.doc.from_warehouse) {
            frm.set_value("from_warehouse", null);
        }
    }

    if (entry_type === "Consume") {
        // Consumption only removes stock from a warehouse.
        if (frm.doc.to_warehouse) {
            frm.set_value("to_warehouse", null);
        }
    }
}


function update_items_table(frm) {
    const grid = frm.fields_dict.items?.grid;

    if (!grid) {
        return;
    }

    const is_receipt = frm.doc.stock_entry_type === "Receipt";

    // Incoming Rate is entered by the user only for Receipts.
    grid.update_docfield_property(
        "incoming_rate",
        "reqd",
        is_receipt
    );

    grid.update_docfield_property(
        "incoming_rate",
        "read_only",
        !is_receipt
    );

    // Valuation Rate and Amount are always system calculated.
    grid.update_docfield_property(
        "valuation_rate",
        "read_only",
        1
    );

    grid.update_docfield_property(
        "amount",
        "read_only",
        1
    );

    frm.refresh_field("items");
}