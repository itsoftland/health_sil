import frappe
import frappe.utils

@frappe.whitelist()
def reset_doctor_token(doctor):
    """
    Resets the doctor's token by inserting a new row with Last Token = "X-0".
    """
    try:
        doc = frappe.get_doc("Healthcare Practitioner", {"practitioner_name":doctor})

        last_entry = doc.token_history[-1] if doc.token_history else None
        token_series = last_entry.token_series if last_entry else frappe.throw("No token series assigned.")

        # Reset the token
        new_token = f"{token_series}0"
        last_entry.date = frappe.utils.today()
        last_entry.last_token = f"{last_entry.token_series}0"

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        return f"Token reset successful: {new_token}"
    except Exception as e:
        frappe.log_error(f"Error resetting doctor token: {e}")
        return {"error": "Error resetting doctor token"}

@frappe.whitelist(allow_guest=False)
def get_login_redirect_url():
    """
    Returns the appropriate redirect URL based on the user's roles.
    If the user has the 'Dashboard_user' role, redirect to daily-report.
    Otherwise, redirect to the home page.
    """
    roles = frappe.get_roles(frappe.session.user)
    if "Dashboard_user" in roles:
        return "/app/daily-report"
    return "/app/home"

