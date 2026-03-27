import frappe
import re

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    try:
        # ✅ Run as your user (important for permissions)
        frappe.set_user("shaishav.mahaseth@acumensa.co")

        data = frappe.request.get_json()
        event = data.get("event")

        if event != "payment.captured":
            return {"status": "ignored"}

        entity = data.get("payload", {}).get("payment", {}).get("entity", {})

        payment_id = entity.get("id")
        amount = (entity.get("amount") or 0) / 100
        description = entity.get("description", "") or ""

        # 🔍 Extract invoice
        invoice_name = None

        match = re.search(r'ACC-SINV-\d{4}-\d+', description)
        if match:
            invoice_name = match.group(0)
        else:
            match = re.search(r'SINV-\d{4}-\d+', description)
            if match:
                invoice_name = "ACC-" + match.group(0)

        if not invoice_name:
            frappe.log_error("Invoice not found", "Webhook")
            return {"status": "no_invoice"}

        # Prevent duplicate
        if frappe.db.exists("Payment Entry", {"reference_no": payment_id}):
            return {"status": "duplicate"}

        # Get invoice
        invoice = frappe.get_doc("Sales Invoice", invoice_name)

        if invoice.outstanding_amount <= 0:
            return {"status": "already_paid"}

        # ✅ Create Payment Entry
        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": invoice.customer,
            "company": invoice.company,

            # 🔥 Dynamic correct account
            "paid_from": invoice.debit_to,
            "paid_to": "Demo Bank Account - AD",

            "mode_of_payment": "Razorpay",

            "paid_amount": amount,
            "received_amount": amount,

            "reference_no": payment_id,
            "reference_date": frappe.utils.nowdate(),

            "references": [
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": invoice.name,
                    "allocated_amount": amount
                }
            ]
        })

        pe.insert(ignore_permissions=True)
        pe.submit()

        # 🔥 Update Payment Request
        payment_requests = frappe.get_all(
            "Payment Request",
            filters={
                "reference_name": invoice.name,
                "status": ["!=", "Paid"]
            },
            fields=["name"]
        )

        for pr in payment_requests:
            pr_doc = frappe.get_doc("Payment Request", pr.name)
            pr_doc.status = "Paid"
            pr_doc.db_update()

        return {"status": "success"}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Webhook Error")
        return {"status": "error"}
