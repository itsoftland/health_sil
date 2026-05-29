import frappe
import json
from frappe import _
from frappe.utils import flt, nowdate, now_datetime, get_datetime


@frappe.whitelist()
def process_medicine_return(pharmacy_billing_name, return_items):
    """
    Process a medicine return for a Pharmacy Billing document.

    Steps:
      1. Validate the Pharmacy Billing is submitted.
      2. For each returned item:
         a. Find the warehouse from the Stock Ledger (same query as generate_invoice_api).
         b. Create a Stock Ledger Entry with positive actual_qty (stock-in / return).
      3. Update Batch.batch_qty to reflect the new running total (cosmetic / UI).
      4. Return success with a summary.

    Args:
        pharmacy_billing_name (str): Name of the Pharmacy Billing doc.
        return_items (str | list): JSON array of items to return.
            Each item: { item_code, batch, qty, warehouse (optional) }
    """
    try:
        # ── Parse return_items ──────────────────────────────────────────
        if isinstance(return_items, str):
            return_items = json.loads(return_items)

        if not return_items:
            frappe.throw(_("No items provided for return."))

        # ── Validate the source bill ────────────────────────────────────
        bill = frappe.get_doc("Pharmacy Billing", pharmacy_billing_name)
        if bill.docstatus != 1:
            frappe.throw(
                _("Only submitted bills can be returned. Bill {0} has docstatus={1}.").format(
                    pharmacy_billing_name, bill.docstatus
                )
            )

        # ── Process each returned item ──────────────────────────────────
        processed = []
        errors    = []

        for item in return_items:
            item_code = item.get("item_code")
            batch_no  = item.get("batch")
            ret_qty   = flt(item.get("qty"))

            if not item_code or ret_qty <= 0:
                continue

            try:
                warehouse = _get_warehouse_for_batch(item_code, batch_no)
                _create_stock_ledger_entry(
                    item_code         = item_code,
                    batch_no          = batch_no,
                    warehouse         = warehouse,
                    actual_qty        = ret_qty,          # positive = inward
                    company           = bill.company,
                    voucher_type      = "Material Receipt",
                    voucher_detail_no = pharmacy_billing_name,
                    remarks           = "Medicine return from bill {0}".format(pharmacy_billing_name),
                )
                # Add returned qty back to Batch.batch_qty directly (additive, not recompute)
                _sync_batch_qty(batch_no, ret_qty)
                processed.append({
                    "item_code": item_code,
                    "batch":     batch_no,
                    "qty":       ret_qty,
                    "warehouse": warehouse,
                })
            except Exception as e:
                frappe.log_error(
                    title="Medicine Return — Item Error",
                    message="Bill: {0} | Item: {1} | Batch: {2}\nError: {3}".format(
                        pharmacy_billing_name, item_code, batch_no, str(e)
                    )
                )
                errors.append("{0} (batch {1}): {2}".format(item_code, batch_no, str(e)))

        frappe.db.commit()

        return {
            "ok":        len(errors) == 0,
            "processed": processed,
            "errors":    errors,
        }

    except Exception as e:
        frappe.log_error(
            title="Medicine Return — Fatal Error",
            message="Bill: {0}\nError: {1}".format(pharmacy_billing_name, str(e))
        )
        frappe.throw(_("Return failed: {0}").format(str(e)))


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_warehouse_for_batch(item_code, batch_no):
    """
    Find the warehouse that holds stock for this batch to route the return.

    In ERPNext v15 the SLE.batch_no column is NULL for new transactions —
    batch info lives in tabSerial and Batch Entry. tabBin also does NOT have
    a batch_no column. We query through the Serial and Batch Bundle chain.

    Falls back to Batch.warehouse, then item default warehouse.
    """
    if not batch_no:
        return _get_default_warehouse(item_code)

    # Priority 1 — Serial and Batch Bundle chain (correct for ERPNext v15).
    # SUM(sbe.qty) per warehouse gives the net current stock for this batch.
    result = frappe.db.sql("""
        SELECT sle.warehouse, SUM(sbe.qty) AS net_qty
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabSerial and Batch Bundle` sbb ON sbe.parent = sbb.name
        INNER JOIN `tabStock Ledger Entry` sle
               ON sle.serial_and_batch_bundle = sbb.name
        WHERE sbe.batch_no  = %s
          AND sle.item_code = %s
          AND sle.is_cancelled = 0
          AND sbb.docstatus  = 1
        GROUP BY sle.warehouse
        HAVING net_qty > 0
        ORDER BY net_qty DESC
        LIMIT 1
    """, (batch_no, item_code), as_dict=True)

    if result:
        return result[0]["warehouse"]

    # Priority 2 — Batch.warehouse field (set during data import)
    batch_warehouse = frappe.db.get_value("Batch", batch_no, "warehouse")
    if batch_warehouse:
        return batch_warehouse

    # Priority 3 — item default warehouse
    return _get_default_warehouse(item_code)
def _get_default_warehouse(item_code):
    """Get item default warehouse or fall back to first enabled warehouse."""
    default_wh = frappe.get_cached_value("Item", item_code, "default_warehouse")
    if default_wh:
        return default_wh
    wh = frappe.db.get_value("Warehouse", {"disabled": 0, "is_group": 0}, "name")
    if not wh:
        frappe.throw(_("No warehouse found for item {0}").format(item_code))
    return wh


def _create_stock_ledger_entry(
    item_code, batch_no, warehouse, actual_qty,
    company, voucher_type, voucher_detail_no, remarks=""
):
    """
    Insert a Stock Ledger Entry for the returned stock (inward movement).
    actual_qty is POSITIVE (we are adding stock back).
    
    Uses frappe.get_doc + insert so that all validation hooks run properly,
    including qty_after_transaction recalculation.
    """
    posting_dt = now_datetime()

    # ── Determine qty_after_transaction ──────────────────────────────────
    # ALWAYS use Batch.batch_qty as the baseline, NOT the last SLE's
    # qty_after_transaction.
    #
    # Why: In this system, batches are imported with batch_qty set directly
    # WITHOUT a purchase Stock Ledger Entry (the SLE chain starts at 0).
    # When a sale of 500 happens on a batch with batch_qty=1637:
    #   - Frappe SLE: actual_qty=-500, qty_after_transaction = 0-500 = -500
    #     (Frappe sees no prior SLE → starts from 0)
    #   - batch_qty correctly updated to 1637-500 = 1137 by ERPNext's stock system
    # If we use the SLE qty_after_transaction (-500) as our baseline:
    #   return 250 → SLE qty_after = -500+250 = -250 → next billing throws negative stock error
    # If we use batch_qty (1137) as our baseline:
    #   return 250 → SLE qty_after = 1137+250 = 1387 → correct ✓
    # ─────────────────────────────────────────────────────────────────────
    # batch_qty at this point = current stock BEFORE this return
    # (ERPNext additively adjusts it on every stock movement, and
    #  _sync_batch_qty is called AFTER this function, so it's still the pre-return value)
    prev_qty_after = flt(frappe.db.get_value("Batch", batch_no, "batch_qty") or 0)
    new_qty_after  = prev_qty_after + actual_qty

    sle = frappe.get_doc({
        "doctype":               "Stock Ledger Entry",
        "item_code":             item_code,
        "warehouse":             warehouse,
        "posting_date":          posting_dt.date(),
        "posting_time":          posting_dt.strftime("%H:%M:%S"),
        "actual_qty":            actual_qty,             # positive = stock in
        "qty_after_transaction": new_qty_after,
        "batch_no":              batch_no or "",
        "voucher_type":          voucher_type,
        "voucher_no":            voucher_detail_no,
        "voucher_detail_no":     voucher_detail_no,
        "company":               company,
        "is_cancelled":          0,
        "remarks":               remarks or "Medicine return",
        "incoming_rate":         0,                      # no valuation needed for return
        "stock_uom":             frappe.get_cached_value("Item", item_code, "stock_uom") or "Nos",
    })

    sle.flags.ignore_permissions   = True
    sle.flags.ignore_links         = True
    sle.flags.ignore_validate_update_after_submit = True
    sle.insert(ignore_permissions=True)

    # Submit via the document API so on_submit hooks (including
    # validate_serial_batch_no_bundle) run properly.
    # We set ignore_serial_batch_bundle_validation because this SLE is a
    # manual stock correction that does not have a Serial and Batch Bundle
    # (Bug F fix — replaces the raw db.set_value('docstatus', 1) hack).
    frappe.flags.ignore_serial_batch_bundle_validation = True
    try:
        sle.submit()
    finally:
        frappe.flags.ignore_serial_batch_bundle_validation = False

    # NOTE: frappe.db.commit() intentionally removed from here (Bug F fix).
    # The outer process_medicine_return() commits once after all items succeed,
    # so a mid-loop failure can roll back all earlier stock entries atomically.

    return sle.name


def _sync_batch_qty(batch_no, ret_qty):
    """
    Add the returned qty directly to Batch.batch_qty.

    WHY additive (not recomputed from SLE sum):
      In this system, batches are often created via import with batch_qty
      set directly, WITHOUT a corresponding purchase Stock Ledger Entry.
      Recomputing SUM(actual_qty) from SLEs would only see entries that
      have batch_no set — skipping older purchase SLEs — and produce a
      wrong (too-low or negative) value.

      Example:
        batch_qty = 50  (100 purchased, 50 sold — tracked correctly)
        Return 30  → new batch_qty = 50 + 30 = 80  ✓
        (SLE sum approach would give: 0 purchase SLE + (−50 sale SLE) + 30 return = −20 or just 30  ✗)
    """
    if not batch_no:
        return

    current_qty = flt(frappe.db.get_value("Batch", batch_no, "batch_qty") or 0)
    new_qty     = current_qty + ret_qty
    frappe.db.set_value("Batch", batch_no, "batch_qty", new_qty, update_modified=False)
