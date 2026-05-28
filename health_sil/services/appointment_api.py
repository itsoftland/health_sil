import frappe
from datetime import date

@frappe.whitelist()
def manage_token(practitioner_name):
    today_str = date.today().strftime('%Y-%m-%d')

    try:
        # Fetch the Healthcare Practitioner doc
        doctor = frappe.get_doc("Healthcare Practitioner", practitioner_name)

        # Look for today's token entry
        token_entry = next(
            (t for t in doctor.custom_token_history if str(t.date) == today_str),
            None
        )

        if not token_entry:
            # If no entry exists for today, create a new one with token series "doctor_name-"
            new_token_series = doctor.custom_token_series.upper() 
            new_token_number = 1
            new_token = f"{new_token_series}-{new_token_number}"

        else:
            # Increment last token number for the given date
            series = token_entry.token_series
            last_token = int(token_entry.last_token) + 1  # Increment the last token number
            new_token = f"{series}-{last_token}"

            # Update the last token number in the token entry
            token_entry.last_token = last_token

        
        doctor.save(ignore_permissions=True)
        frappe.db.commit()

        return new_token

    except Exception as e:
        frappe.log_error(f"Error generating token for doctor {practitioner_name}: {e}")
        return None


@frappe.whitelist()
def check_last_encounter(patient):
    last_encounter = frappe.db.get_value(
        "Patient Encounter",
        {"patient": patient},
        ["name", "practitioner"],
        order_by="creation desc"
    )
    if last_encounter:
        return {
            "has_encounter": True,
            "encounter": last_encounter[0],
            "doctor": last_encounter[1]
        }
    else:
        return { "has_encounter": False }
