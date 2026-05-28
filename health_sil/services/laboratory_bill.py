# import frappe
# from frappe import _

# @frappe.whitelist()
# def create_lab_tests_for_bill(doc, method):
#     for item in doc.lab_items:
#         lab_test = frappe.new_doc("Lab Test")
#         lab_test.patient = doc.patient_name
#         lab_test.template = item.item_name
#         lab_test.practitioner = doc.healthcare_practitioner
#         lab_test.laboratory_bill_ref = doc.name
#         lab_test.source_item_code = item.item_code

#         lab_test.insert()  # Draft state

import frappe
from frappe import _

@frappe.whitelist()
def create_lab_tests_for_bill(doc, method):
    original_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        for item in doc.lab_items:
            # Fetch patient gender
            patient_data = frappe.get_value("Patient", doc.patient_name, ["sex"], as_dict=True)
            lab_test = frappe.new_doc("Lab Test")
            lab_test.patient = doc.patient_name
            lab_test.template = item.item_name
            lab_test.practitioner = doc.healthcare_practitioner
            lab_test.laboratory_bill_ref = doc.name
            lab_test.source_item_code = item.item_code
            lab_test.patient_sex = patient_data.sex
            
            lab_test.insert(ignore_permissions=True)
    finally:
        frappe.set_user(original_user)
