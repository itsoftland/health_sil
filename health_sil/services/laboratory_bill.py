import frappe
from frappe import _


@frappe.whitelist()
def create_lab_tests_for_bill(doc, method):
    """
    Create a Lab Test doc for each row in the Laboratory Bill's lab_items.
    Triggered via Laboratory Bill on_submit doc_event.
    Switches to Administrator for doc operations, patches ownership back to actual user.
    """
    original_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        for item in doc.lab_items:
            patient_data = frappe.get_value("Patient", doc.patient_name, ["sex"], as_dict=True)

            lab_test = frappe.new_doc("Lab Test")
            lab_test.patient = doc.patient_name
            lab_test.template = item.item_name
            lab_test.practitioner = doc.healthcare_practitioner
            lab_test.laboratory_bill_ref = doc.name
            lab_test.source_item_code = item.item_code
            lab_test.patient_sex = patient_data.sex

            lab_test.insert(ignore_permissions=True)

            # Patch ownership back to the actual user
            frappe.db.set_value("Lab Test", lab_test.name, {
                "owner": original_user,
                "modified_by": original_user
            }, update_modified=False)
    finally:
        frappe.set_user(original_user)
