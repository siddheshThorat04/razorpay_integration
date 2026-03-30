import frappe
import re

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    try:
        frappe.set_user("Administrator")
        data = frappe.request.get_json()
        event = data.get("event")
        if event != "payment.captured":
            return {"status": "ignored"}

        entity = data.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = entity.get("id")
        amount = (entity.get("amount") or 0) / 100
        description = entity.get("description", "") or ""

        # Prevent duplicate
        if frappe.db.exists("Payment Entry", {"reference_no": payment_id}):
            return {"status": "duplicate"}

        # ─────────────────────────────────────────
        # 🔍 Detect document type from description
        # ─────────────────────────────────────────

        # Check for Fees document (e.g. EDU-FEE-2026-00059)
        fee_match = re.search(r'EDU-FEE-\d{4}-\d+', description)

        # Check for Sales Invoice (e.g. ACC-SINV-2024-00001 or SINV-2024-00001)
        sinv_match = re.search(r'ACC-SINV-\d{4}-\d+', description)
        if not sinv_match:
            sinv_match = re.search(r'SINV-\d{4}-\d+', description)

        if fee_match:
            return _handle_fee_payment(fee_match.group(0), payment_id, amount)
        elif sinv_match:
            invoice_name = sinv_match.group(0)
            if not invoice_name.startswith("ACC-"):
                invoice_name = "ACC-" + invoice_name
            return _handle_sinv_payment(invoice_name, payment_id, amount)
        else:
            frappe.log_error(f"No invoice/fee found in description: {description}", "Webhook")
            return {"status": "no_document"}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Webhook Error")
        return {"status": "error"}


# ─────────────────────────────────────────
# 💳 Handle Sales Invoice Payment
# ─────────────────────────────────────────
def _handle_sinv_payment(invoice_name, payment_id, amount):
    if not frappe.db.exists("Sales Invoice", invoice_name):
        frappe.log_error(f"Sales Invoice not found: {invoice_name}", "Webhook")
        return {"status": "invoice_not_found"}

    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    if invoice.outstanding_amount <= 0:
        return {"status": "already_paid"}

    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": invoice.customer,
        "company": invoice.company,
        "paid_from": invoice.debit_to,
        "paid_to": "Razorpay - D",
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

    _mark_payment_requests_paid(invoice.name)
    return {"status": "success", "type": "sales_invoice", "document": invoice_name}


# ─────────────────────────────────────────
# 🎓 Handle Fees Payment
# ─────────────────────────────────────────
def _handle_fee_payment(fee_name, payment_id, amount):
    if not frappe.db.exists("Fees", fee_name):
        frappe.log_error(f"Fee document not found: {fee_name}", "Webhook")
        return {"status": "fee_not_found"}

    fee = frappe.get_doc("Fees", fee_name)

    if fee.outstanding_amount <= 0:
        return {"status": "already_paid"}

    # Fees use "Student" as party_type in ERPNext Education
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Student",
        "party": fee.student,
        "company": fee.company,
        "paid_from": fee.receivable_account,   # debit account on Fees doc
        "paid_to": "Razorpay - D",
        "mode_of_payment": "Razorpay",
        "paid_amount": amount,
        "received_amount": amount,
        "reference_no": payment_id,
        "reference_date": frappe.utils.nowdate(),
        "references": [
            {
                "reference_doctype": "Fees",
                "reference_name": fee.name,
                "allocated_amount": amount
            }
        ]
    })
    pe.insert(ignore_permissions=True)
    pe.submit()

    _mark_payment_requests_paid(fee.name)
    return {"status": "success", "type": "fees", "document": fee_name}


# ─────────────────────────────────────────
# 🔄 Mark Payment Requests as Paid
# ─────────────────────────────────────────
def _mark_payment_requests_paid(reference_name):
    payment_requests = frappe.get_all(
        "Payment Request",
        filters={
            "reference_name": reference_name,
            "status": ["!=", "Paid"]
        },
        fields=["name"]
    )
    for pr in payment_requests:
        pr_doc = frappe.get_doc("Payment Request", pr.name)
        pr_doc.status = "Paid"
        pr_doc.db_update()
