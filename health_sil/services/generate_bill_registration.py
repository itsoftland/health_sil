from datetime import datetime, timedelta
import frappe
from frappe import _
from frappe.utils import nowdate, flt,cint, getdate
from frappe.model.document import Document
from frappe import json


@frappe.whitelist()
def create_registration_only(patient, patient_name, items=None, mode_of_payment=None):
    """
    Creates a Sales Invoice for a Patient with optimizations and auto-generates Payment Entry.
    Runs under Administrator context for backend doc operations.
    """
    if frappe.db.get_value("Patient", patient, "custom_is_registered"):
        frappe.throw("Patient already registered")

    if isinstance(items, str):
        items = json.loads(items)
    
    registration_items = [item for item in items if item["item_code"] == "Registration Fee"]
    if not registration_items:
        frappe.throw("Registration must include Registration Fee item")

    original_user = frappe.session.user
    try:
        # Validate inputs (as original user)
        validate_mandatory(patient, items)
        items = safe_json_parse(items)
        validate_items_existence(items)
        customer = get_validated_customer(patient)

        # Switch to Administrator for doc operations
        frappe.set_user("Administrator")

        update_patient_registration_details(patient)
        invoice = create_and_submit_invoice_only(patient, patient_name, customer, items)
        payment_entry = process_payment(invoice, mode_of_payment) if mode_of_payment else None
        
        return build_response(invoice)

    except Exception as e:
        handle_errors(e)
    finally:
        frappe.set_user(original_user)

# ----------
# Helper Functions
# ----------
def validate_mandatory(patient, items):
    """Pre-flight validations"""
    if not patient:
        frappe.throw(_("Patient is mandatory"))
    
    if not items or (isinstance(items, list) and len(items) == 0):
        frappe.throw(_("At least one item is required"))

def safe_json_parse(items):
    """Safely parse JSON string input"""
    if isinstance(items, str):
        try:
            return frappe.parse_json(items)
        except:
            frappe.throw(_("Invalid items format"))
    return items

def validate_items_existence(items):
    """Batch validate items in single query"""
    item_codes = {item.get("item_code") for item in items}
    existing_items = {d.name for d in frappe.get_all("Item", filters={"name": ["in", item_codes]}, fields=["name"], ignore_permissions=True)}
    
    if missing := item_codes - existing_items:
        frappe.throw(_("Invalid items: {0}").format(", ".join(missing)))

def get_validated_customer(patient):
    """Get and validate customer"""
    customer = frappe.get_cached_value("Patient", patient, "customer")
    
    if not customer:
        frappe.throw(_("No Customer linked to Patient {0}").format(patient))
    
    if frappe.get_cached_value("Customer", customer, "disabled"):
        frappe.throw(_("Customer {0} is disabled").format(customer))
    
    return customer

def create_and_submit_invoice_only(patient, patient_name, customer, items):
    """Create and submit Sales Invoice with optimized validations"""
    invoice = frappe.new_doc("Sales Invoice")
    invoice.update({
        "customer": customer,
        "patient": patient,
        "patient_name": patient_name,
        "due_date": nowdate(),
        "items": [validate_and_prepare_item(row) for row in items]
    })
    
    invoice.insert(ignore_permissions=True)
    invoice.submit()
    return invoice

def update_patient_registration_details(patient):
    try:
        frappe.db.begin()
        
        # Lock the document for update
        patient_doc = frappe.get_doc("Patient", patient)
        patient_doc = frappe.get_doc("Patient", patient_doc.name).as_dict()
        patient_doc = frappe.get_doc("Patient", patient_doc.name, for_update=True)

        changed = False

        if cint(patient_doc.custom_is_registered) == 0:
            patient_doc.custom_is_registered = 1
            changed = True

        if changed:
            patient_doc.save(ignore_permissions=True)
        
        frappe.db.commit()

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error updating registration for patient {patient}: {str(e)}")
        raise

def validate_and_prepare_item(item):
    """Validate individual item and prepare for insertion"""
    if (qty := flt(item.get("qty", 1))) <= 0:
        frappe.throw(_("Invalid quantity for item {0}").format(item.get("item_code")))
    
    if (rate := flt(item.get("rate", 0))) < 0:
        frappe.throw(_("Negative rate for item {0}").format(item.get("item_code")))
    
    return {
        "item_code": item.get("item_code"),
        "qty": qty,
        "rate": rate
    }

def process_payment(invoice, mode_of_payment):
    """Handle payment processing"""
    try:
        validate_mode_of_payment(mode_of_payment, invoice.company)
        return create_payment_entry(invoice, mode_of_payment)
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

def create_payment_entry(invoice, mode_of_payment):
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
            "allocated_amount": invoice.outstanding_amount
        }]
    })
    
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe

def get_payment_account(mode, company):
    """Cached lookup for payment account"""
    return frappe.get_cached_value("Mode of Payment Account", 
        {"parent": mode, "company": company}, "default_account")


def build_response(invoice):
    """Standardized response format"""
    return {
        "sales_invoice": invoice.name,
        "total_amount": invoice.grand_total,
        "outstanding_amount": invoice.outstanding_amount
    }

def log_and_notify_payment_error(invoice_name, error):
    """Centralized error handling for payments"""
    frappe.log_error(
        title=_("Payment Processing Failed"),
        message=f"Invoice: {invoice_name}\nError: {str(error)}"
    )

def handle_errors(error):
    """Global error handler"""
    frappe.log_error(
        title=_("Sales Pipeline Error"),
        message=f"Error: {str(error)}"
    )
    frappe.throw(_("Process failed. Please check error logs for details."))