import datetime
import frappe

def generate_custom_uid(doc, method):
    if not doc.uid:
        year_suffix = str(datetime.datetime.now().year)[-2:]
        key = "patient_uid_sequence"

        # Use raw query to avoid ORDER BY errors
        try:
            current = frappe.db.get_value("Series", key, "current", order_by=None)
        except Exception as e:
            frappe.log_error(f"Failed to set patient uid: {e}")
            return

        if current is None:
            current = 15000
            try:
                frappe.db.sql(
                    "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
                    (key, current)
                )
            except Exception as e:
                frappe.log_error(f"Failed to set patient uid: {e}")
                return

        current = int(current) + 1

        # Save new value using SQL (not set_value!)
        try:
            frappe.db.sql(
                "UPDATE `tabSeries` SET `current` = %s WHERE `name` = %s",
                (current, key)
            )
        except Exception as e:
            frappe.log_error(f"Failed to set patient uid: {e}")
            return

        # Compose UID and set as primary key
        uid = f"DR-PID{year_suffix}-{current}"
        doc.uid = uid
        doc.name = uid  # Makes the PID the Frappe document ID (primary key)

