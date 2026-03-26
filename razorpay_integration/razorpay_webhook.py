import frappe
from frappe.utils import nowdate

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    try:
        # ✅ Get JSON safely
        data = frappe.request.get_json()

        if not data:
            return {"status": "no_data"}

        event = data.get("event")

        # ✅ Only process captured payments
        if event != "payment.captured":
            return {"status": "ignored"}

        entity = data.get("payload", {}).get("payment", {}).get("entity", {})

        payment_id = entity.get("id")
        amount = entity.get("amount", 0) / 100  # paise → rupees
        description = entity.get("description", "") or ""

        # ✅ Safe logging
        frappe.log_error(
            message=str(data)[:2000],
            title="Razorpay Webhook Data"
        )

        # 🔍 Extract FULL invoice name (IMPORTANT FIX)
        invoice_name = None

        for part in description.split():
            clean = part.strip(".,")
            if "SINV-" in clean:
                invoice_name = clean
                break

        if not invoice_name:
            frappe.log_error(
                message=description,
                title="Invoice not found in description"
            )
            return {"status": "no_invoice"}

        # 🚫 Prevent duplicate Payment Entry
        if frappe.db.exists("Payment Entry", {"reference_no": payment_id}):
            return {"status": "duplicate"}

        # 📦 Fetch Sales Invoice (NOW CORRECT)
        invoice = frappe.get_doc("Sales Invoice", invoice_name)

        if invoice.outstanding_amount <= 0:
            return {"status": "already_paid"}

        company = invoice.company
        customer = invoice.customer

        # 💰 Create Payment Entry
        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": customer,
            "company": company,
            "paid_amount": amount,
            "received_amount": amount,
            "reference_no": payment_id,
            "reference_date": nowdate()
        })

        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice.name,
            "allocated_amount": amount
        })

        pe.insert(ignore_permissions=True)
        pe.submit()

        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Razorpay Webhook Error"
        )
        return {"status": "error", "message": str(e)}
