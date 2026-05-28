import frappe
import traceback
from frappe import _

@frappe.whitelist()
def create_stock_entry_from_purchase_invoice(purchase_invoice):
    original_user = frappe.session.user
    try:
        # Fetch the Purchase Invoice document
        pi = frappe.get_doc("Purchase Invoice", purchase_invoice)

        # Switch to Administrator for stock entry operations
        frappe.set_user("Administrator")
        
        # Loop through all items in the purchase invoice
        for item in pi.items:
            # Check if custom_is_free_qty is True and custom_free_qty is greater than 0
            if item.custom_is_free_qty and item.custom_free_qty > 0:
                # Create a new Stock Entry
                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.custom_purchase_invoice_no = purchase_invoice
                stock_entry.purpose = "Material Receipt"
                stock_entry.stock_entry_type = "Purchase Receipt"
                stock_entry.company = pi.company
                
                # Add the item to Stock Entry
                stock_entry.append("items", {
                    "item_code": item.item_code,
                    "qty": item.custom_free_qty,
                    "rate": 0,
                    "t_warehouse": item.warehouse,
                    "item_name": item.item_name,
                    "uom": item.uom,
                    "batch_no": item.batch_no,
                    "stock_uom": item.uom,
                    "basic_rate": 0,
                })
                
                # Submit the Stock Entry
                stock_entry.insert(ignore_permissions=True)
                stock_entry.submit()
                
                # Optionally, you can log that the stock entry was created
                # frappe.msgprint(f"Stock Entry for {item.item_code} created with qty {item.custom_free_qty}")
    except Exception as e:
        tb = traceback.format_exc()
        frappe.log_error(
            title="Stock Entry Creation Error",
            message=(
                f"User: {original_user}\n"
                f"Roles: {', '.join(frappe.get_roles())}\n"
                f"Purchase Invoice: {purchase_invoice}\n"
                f"Error: {str(e)}\n\n"
                f"Full Traceback:\n{tb}"
            )
        )
        frappe.throw(_("Stock Entry failed: {0}").format(str(e)))
    finally:
        frappe.set_user(original_user)

