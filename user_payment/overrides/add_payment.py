import frappe

def add_row_payment(doc, method):
    """
    Add a row to the Payment Entry with the Sales Person's incentives and commission rate.

    c
    """
    cash_account = frappe.get_value(
        "Company", doc.company, "default_cash_account")
    # doc.is_pos = 1
    doc.cash_account = cash_account

    # Clear the payments table to avoid duplicates
    doc.set("payments", [])

    if doc.is_cash:
        doc.append("payments",{
            "account": cash_account,
            "amount": doc.rounded_total,
            "mode_of_payment": "نقد",
            
        })
