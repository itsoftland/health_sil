import frappe

def create_address_from_patient(doc, method):
    """
    After a Patient is inserted, create a new Address document using the custom address fields.
    The dynamic link is added as a child record in the dynamic_links table.

    State and Pincode are only required for Indian patients (custom_country == 'India').
    Foreign patients only require Address Line, City, and Country.
    """
    is_indian_patient = (doc.get("custom_country") or "").strip().lower() == "india"

    # Fields always required for every patient
    always_required = [
        ('custom_address_line', "Address Line"),
        ('custom_city', "City"),
        ('custom_country', "Country"),
    ]

    # Fields required only when the patient is from India
    india_required = [
        ('custom_state', "State"),
        ('custom_pincode', "Pincode"),
    ]

    # Build the effective required list based on country
    required_fields = always_required + (india_required if is_indian_patient else [])

    # Check for missing required fields in the patient document
    missing_fields = [label for field, label in required_fields if not doc.get(field)]
    if missing_fields:
        error_message = f"Missing required fields for Patient {doc.name}: {', '.join(missing_fields)}"
        frappe.log_error(title="Missing Fields in Patient", message=error_message)
        return

    try:
        # Create a new Address document and set its fields
        address = frappe.new_doc("Address")

        # Use patient name for address title; if not provided, fallback to document name
        address.address_title = doc.patient_name or doc.name
        address.address_line1 = doc.custom_address_line
        address.city = doc.custom_city
        address.country = doc.custom_country
        address.address_type = "Personal"
        address.is_your_company_address = 0

        # Only set state and pincode if they are provided (optional for foreign patients)
        if doc.get("custom_state"):
            address.state = doc.custom_state
        if doc.get("custom_pincode"):
            address.pincode = doc.custom_pincode

        # Append the dynamic link to the address document linking to the Patient
        address.append("links", {
            "link_doctype": "Patient",
            "link_name": doc.name  # using doc.name to reference the actual document
        })

        # Insert the address document into the system
        address.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception as e:
        # Log any errors that occur during the process with a clear error title and message
        frappe.log_error(
            title="Error Creating Address from Patient",
            message=f"Patient {doc.name}: {str(e)}"
        )
        raise
