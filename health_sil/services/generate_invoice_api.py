import frappe
import json
import traceback
from frappe import _
from frappe.utils import nowdate, flt


@frappe.whitelist()
def create_sales_invoice(patient, patient_name, doctor=None, items=None, mode_of_payment=None, price_list=None, discount_amount_cash=None, discount_amount_percentage=None):
    """
    Creates a Sales Invoice and auto-generates Payment Entry.
    Switches to Administrator for doc operations, then patches ownership
    back to the actual user so the audit trail is preserved.
    """
    original_user = frappe.session.user
    try:
        customer = get_validated_customer(patient_name)

        # Switch to Administrator to bypass all nested ERPNext permission checks
        frappe.set_user("Administrator")

        invoice = create_and_submit_invoice(
            customer, patient, patient_name, doctor, items,
            price_list, discount_amount_cash, discount_amount_percentage,
            original_user,
        )
        process_payment(invoice, mode_of_payment, original_user) if mode_of_payment else None
        return invoice

    except Exception as e:
        handle_errors(e, original_user)
    finally:
        frappe.set_user(original_user)


# ----------
# Helper Functions
# ----------
def get_validated_customer(patient_name):
    """Get and validate customer"""
    customer = frappe.get_cached_value("Patient", patient_name, "customer")

    if not customer:
        frappe.throw(_("No Customer linked to Patient {0}").format(patient_name))

    if frappe.get_cached_value("Customer", customer, "disabled"):
        frappe.throw(_("Customer {0} is disabled").format(customer))

    return customer


def create_and_submit_invoice(customer, patient, patient_name, doctor, items, price_list, discount_amount_cash, discount_amount_percentage, original_user):
    items = json.loads(items)
    invoice = frappe.new_doc("Sales Invoice")

    prepared_items = [validate_and_prepare_item(row) for row in items]
    contains_medications = any(
        frappe.get_cached_value("Item", row["item_code"], "item_group") == "Medications"
        for row in prepared_items
    )

    invoice.update({
        "customer": customer,
        "patient": patient,
        "patient_name": patient_name,
        "ref_practitioner": doctor,
        "selling_price_list": price_list or "Standard Selling",
        "due_date": nowdate(),
        "update_stock": 1 if contains_medications else 0,
        "items": prepared_items,
        "taxes_and_charges": frappe.db.get_value("Sales Taxes and Charges Template", {"is_default": 1}, "name"),
        "discount_amount": flt(discount_amount_cash or 0),
        "additional_discount_percentage": flt(discount_amount_percentage or 0),
    })

    invoice.set_missing_values()
    invoice.insert(ignore_permissions=True)
    invoice.submit()

    # Patch ownership back to the actual user
    frappe.db.set_value("Sales Invoice", invoice.name, {
        "owner": original_user,
        "modified_by": original_user
    }, update_modified=False)

    return invoice



def validate_and_prepare_item(item):
    """Validate individual item and prepare for insertion"""
    item_code = item.get("item_code")
    qty = flt(item.get("qty", 1))
    rate = flt(item.get("rate", 0))
    batch_no = item.get("batch_no")

    if qty <= 0:
        frappe.throw(_("Invalid quantity for item {0}").format(item_code))
    if rate < 0:
        frappe.throw(_("Negative rate for item {0}").format(item_code))

    item_group = frappe.get_cached_value("Item", item_code, "item_group")
    warehouse = None

    if item_group == "Medications" and batch_no:
        warehouse = get_warehouse_for_batch(item_code, batch_no)
        if not warehouse:
            frappe.throw(_("No warehouse found with stock for item {0} and batch {1}").format(item_code, batch_no))

    return {
        "item_code": item_code,
        "qty": qty,
        "uom": "Nos",
        "rate": rate,
        "batch_no": batch_no if item_group == "Medications" else "",
        "warehouse": warehouse if item_group == "Medications" else None,
    }


def get_warehouse_for_batch(item_code, batch_no):
    """Get the warehouse holding the given batch of an item.

    In ERPNext v15, batch quantities live in tabSerial and Batch Entry (child of
    tabSerial and Batch Bundle), linked to tabStock Ledger Entry via
    serial_and_batch_bundle. tabBin does NOT have a batch_no column.

    Falls back to Batch.warehouse (set during data import) if no SBB transactions
    exist yet for this batch (e.g. initial stock import with no sales history).
    """
    # Priority 1 — Serial and Batch Bundle chain (correct for ERPNext v15).
    # sbe.qty is positive for inward and negative for outward movements, so
    # SUM(sbe.qty) per warehouse gives the current net stock for this batch.
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

    # Priority 2 — Batch.warehouse field (populated during data import for
    # batches that have no SBB transactions yet, e.g. initial stock import).
    batch_warehouse = frappe.db.get_value("Batch", batch_no, "warehouse")
    if batch_warehouse:
        return batch_warehouse

    frappe.throw(_("No warehouse found with stock for item {0} and batch {1}").format(item_code, batch_no))


def process_payment(invoice, mode_of_payment, original_user=None):
    """Handle payment processing"""
    try:
        validate_mode_of_payment(mode_of_payment, invoice.company)
        return create_payment_entry(invoice, mode_of_payment, original_user)
    except Exception as e:
        log_and_notify_payment_error(invoice.name, e)
        return None


def validate_mode_of_payment(mode, company):
    """Validate mode of payment configuration"""
    if not frappe.db.exists("Mode of Payment", {"name": mode}):
        frappe.throw(_("Invalid Mode of Payment: {0}").format(mode))

    if not frappe.get_cached_value("Mode of Payment Account",
        {"parent": mode, "company": company}, "default_account"):
        frappe.throw(_("Mode of Payment {0} not configured for company {1}").format(mode, company))


def log_and_notify_payment_error(invoice_name, error):
    """Centralized error handling for payments"""
    frappe.log_error(
        title=_("Payment Processing Failed"),
        message=(
            f"User: {frappe.session.user}\n"
            f"Roles: {', '.join(frappe.get_roles())}\n"
            f"Invoice: {invoice_name}\n"
            f"Error type: {type(error).__name__}\n"
            f"Error: {repr(error)}\n\n"
            f"Traceback:\n{traceback.format_exc()}"
        ),
    )


def create_payment_entry(invoice, mode_of_payment, original_user=None):
    """Create payment entry using existing invoice doc"""
    if invoice.outstanding_amount <= 0:
        return None

    pe = frappe.new_doc("Payment Entry")
    pe.update({
        "posting_date": nowdate(),
        "payment_type": "Receive",
        "mode_of_payment": mode_of_payment,
        "paid_from": invoice.debit_to,
        "paid_to": get_payment_account(mode_of_payment, invoice.company),
        "party_type": "Customer",
        "party": invoice.customer,
        "paid_amount": invoice.outstanding_amount,
        "received_amount": invoice.outstanding_amount,
        "references": [{
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice.name,
            "allocated_amount": invoice.outstanding_amount,
        }],
    })

    pe.insert(ignore_permissions=True)
    pe.submit()

    # Patch ownership back to the actual user
    if original_user:
        frappe.db.set_value("Payment Entry", pe.name, {
            "owner": original_user,
            "modified_by": original_user
        }, update_modified=False)

    return pe


def get_payment_account(mode, company):
    """Cached lookup for payment account"""
    return frappe.get_cached_value("Mode of Payment Account",
        {"parent": mode, "company": company}, "default_account")


def handle_errors(error, original_user=None):
    """Global error handler — full traceback to logs, generic message to user."""
    user = original_user or frappe.session.user
    frappe.log_error(
        title=_("Pharmacy Billing Error"),
        message=(
            f"User: {user}\n"
            f"Roles: {', '.join(frappe.get_roles(user))}\n"
            f"Error: {str(error)}\n\n"
            f"Traceback:\n{traceback.format_exc()}"
        ),
    )
    frappe.throw(_("Process failed. Please check error logs for details."))
