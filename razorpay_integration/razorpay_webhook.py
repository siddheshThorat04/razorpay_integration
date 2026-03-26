import frappe

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    try:
        data = frappe.request.get_json()
        event = data.get("event")

        if event != "payment.captured":
            return {"status": "ignored"}

        entity = data.get("payload", {}).get("payment", {}).get("entity", {})

        payment_id = entity.get("id")
        amount = (entity.get("amount") or 0) / 100
        description = entity.get("description", "") or ""

        # Extract invoice name
        invoice_name = None
        for part in description.split():
            clean = part.strip(",.")
            if "SINV" in clean:
                invoice_name = clean
                break

        if not invoice_name:
            frappe.log_error("Invoice not found in description", "Webhook")
            return {"status": "no_invoice"}

        # Remove ACC- prefix
        if invoice_name.startswith("ACC-"):
            invoice_name = invoice_name.replace("ACC-", "")

        # Prevent duplicate
        if frappe.db.exists("Payment Entry", {"reference_no": payment_id}):
            return {"status": "duplicate"}

        # Get invoice
        invoice = frappe.get_doc("Sales Invoice", invoice_name)

        if invoice.outstanding_amount <= 0:
            return {"status": "already_paid"}

        # ✅ YOUR ACTUAL ACCOUNTS
        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": invoice.customer,
            "company": invoice.company,

            "paid_from": "Demo Bank Account - AD",
            "paid_to": "Accounts Receivable - AD",

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

        return {"status": "success"}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Webhook Error")
        return {"status": "error"}
