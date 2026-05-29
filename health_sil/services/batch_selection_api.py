import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_batches_for_item(item_code):
    if not item_code:
        return []

    batches = frappe.db.sql("""
        SELECT
            b.name          AS batch_no,
            b.expiry_date,
            b.batch_qty,
            COALESCE(NULLIF(b.custom_mrp_per_unit, 0), i.valuation_rate, 0) AS mrp_per_tablet,
            COALESCE(
                NULLIF(b.custom_mrp, 0),
                COALESCE(NULLIF(b.custom_mrp_per_unit, 0), i.valuation_rate, 0)
                    * COALESCE(NULLIF(b.custom_strips, 0), i.weight_per_unit, 1)
            , 0) AS mrp_per_strip,
            COALESCE(NULLIF(b.custom_strips, 0), i.weight_per_unit, 1) AS strips
        FROM `tabBatch` b
        LEFT JOIN `tabItem` i ON b.item = i.name
        WHERE b.item     = %s
          AND b.disabled = 0
        ORDER BY b.expiry_date ASC
    """, item_code, as_dict=True)

    result = []

    for b in batches:
        # In ERPNext v15, batch quantities live in Serial and Batch Bundle/Entry,
        # not in SLE.batch_no (which is always NULL in v15).
        # Sum SBB entries: positive = inward, negative = outward.
        sbb_qty = frappe.db.sql("""
            SELECT COALESCE(SUM(sbe.qty), 0) AS net_qty
            FROM `tabSerial and Batch Entry` sbe
            INNER JOIN `tabSerial and Batch Bundle` sbb ON sbe.parent = sbb.name
            INNER JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
            WHERE sbe.batch_no  = %s
              AND sle.item_code = %s
              AND sle.is_cancelled = 0
              AND sbb.docstatus  = 1
        """, (b.batch_no, item_code), as_dict=True)

        if sbb_qty and sbb_qty[0].net_qty is not None:
            b.qty_available = flt(sbb_qty[0].net_qty)
        else:
            # No SBB entries yet — batch was created via import, use batch_qty directly
            b.qty_available = flt(b.batch_qty or 0)

        if b.qty_available > 0:
            result.append(b)

    return result


@frappe.whitelist()
def validate_batch_qty(batch_no, qty):
    if not batch_no:
        return {"ok": False, "available": 0, "message": "No batch selected"}

    batch_info = frappe.db.get_value(
        "Batch", batch_no, ["batch_qty", "item"], as_dict=True
    )
    if not batch_info:
        return {"ok": False, "available": 0, "message": "Batch not found"}

    # In ERPNext v15, batch quantities live in Serial and Batch Bundle/Entry.
    # SLE.batch_no is always NULL in v15, so query SBB directly.
    sbb_qty = frappe.db.sql("""
        SELECT COALESCE(SUM(sbe.qty), 0) AS net_qty
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabSerial and Batch Bundle` sbb ON sbe.parent = sbb.name
        INNER JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
        WHERE sbe.batch_no  = %s
          AND sle.item_code = %s
          AND sle.is_cancelled = 0
          AND sbb.docstatus  = 1
    """, (batch_no, batch_info.item), as_dict=True)

    if sbb_qty and sbb_qty[0].net_qty is not None:
        available = flt(sbb_qty[0].net_qty)
    else:
        # No SBB entries — imported batch, use batch_qty
        available = flt(batch_info.batch_qty or 0)

    requested = flt(qty)

    if requested <= 0:
        return {"ok": False, "available": available, "message": "Qty must be greater than zero"}

    if requested > available:
        return {
            "ok": False,
            "available": available,
            "message": "Insufficient stock. Only {0} Nos available for this batch.".format(int(available))
        }

    return {"ok": True, "available": available}


@frappe.whitelist()
def deduct_batch_stock(batch_no, qty):
    if not batch_no:
        return {"ok": False, "message": "No batch selected"}

    qty = flt(qty)
    if qty <= 0:
        return {"ok": False, "message": "Qty must be greater than zero"}

    current_qty = flt(frappe.db.get_value("Batch", batch_no, "batch_qty") or 0)

    if qty > current_qty:
        return {
            "ok": False,
            "message": "Cannot deduct {0} from batch {1}. Only {2} available.".format(
                int(qty), batch_no, int(current_qty)
            )
        }

    new_qty = current_qty - qty
    frappe.db.set_value("Batch", batch_no, "batch_qty", new_qty)
    frappe.db.commit()

    return {"ok": True, "remaining": new_qty}