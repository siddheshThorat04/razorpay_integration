import frappe
import json
import hmac
import hashlib
import re

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    try:
        data = frappe.request.get_json()
        event = data.get("event")

        frappe.log_error(str(data), "Razorpay Webhook Data")

        if event != "payment.captured":
            return {"status": "ignored"}

        entity = data.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = entity.get("id")
        amount = entity.get("amount", 0) / 100
        notes = entity.get("notes", {}) or {}

        # 🔍 Get invoice from notes
        invoice_name = notes.get("invoice") or notes.get("sales_invoice")

        if not invoice_name:
            frappe.log_error("Invoice not found in notes", "Webhook Error")
            return {"status": "no_invoice"}

        # ❌ Prevent duplicate
        if frappe.db.exists("Payment Entry", {"reference_no": payment_id}):
            return {"status": "duplicate"}

        # 📦 Fetch invoice details
        invoice = frappe.get_doc("Sales Invoice", invoice_name)

        if invoice.outstanding_amount <= 0:
            return {"status": "already_paid"}

        company = invoice.company
        customer = invoice.customer

        receivable_account = frappe.db.get_value(
            "Company", company, "default_receivable_account"
        )

        bank_account = "Demo Bank Account - AD"  # ⚠️ CHANGE THIS

        allocated = min(amount, invoice.outstanding_amount)

        # 💰 Create Payment Entry
        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "posting_date": frappe.utils.today(),
            "company": company,
            "mode_of_payment": "Razorpay",
            "party_type": "Customer",
            "party": customer,
            "paid_from": receivable_account,
            "paid_to": bank_account,
            "paid_amount": amount,
            "received_amount": amount,
            "reference_no": payment_id,
            "reference_date": frappe.utils.today(),
            "remarks": f"Razorpay | {payment_id}",
            "references": [{
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice_name,
                "allocated_amount": allocated,
                "total_amount": invoice.grand_total,
                "outstanding_amount": invoice.outstanding_amount
            }]
        })

        pe.insert(ignore_permissions=True)
        pe.submit()

        frappe.db.commit()

        return {"status": "success", "payment_entry": pe.name}

    except Exception as e:
        frappe.log_error(str(e), "Webhook ERROR")
        return {"status": "error", "message": str(e)}


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
@frappe.whitelist(allow_guest=True)
def razorpay_webhook():
    try:
        raw_body = frappe.request.get_data()
        signature = frappe.request.headers.get("X-Razorpay-Signature", "")
        # Optional: verify webhook secret if configured
        try:
            rz_settings = frappe.get_doc("Razorpay Settings")
            webhook_secret = rz_settings.get_password("webhook_secret") if hasattr(rz_settings, "webhook_secret") else None
            if webhook_secret and signature:
                if not verify_signature(raw_body, signature, webhook_secret):
                    frappe.response["http_status_code"] = 400
                    return {"status": "error", "message": "Invalid signature"}
        except Exception:
            pass  # Don't block on signature check if settings missing
        data = json.loads(raw_body)
        event = data.get("event")
        frappe.logger().info(f"[Razorpay Webhook] Event received: {event}")
        if event in ("payment.captured", "payment.authorized"):
            return handle_payment(data)
        else:
            return {"status": "ignored", "event": event}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Razorpay Webhook - Unhandled Error")
        frappe.response["http_status_code"] = 500
        return {"status": "error", "message": "Internal server error"}
def handle_payment(data: dict):
    entity = data.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id  = entity.get("id")               # pay_SK1DxyvN3d5Bcd
    amount      = entity.get("amount", 0) / 100  # paise → INR
    currency    = entity.get("currency", "INR")
    description = entity.get("description", "")  # "Payment Request for ACC-SINV-2026-00754"
    notes       = entity.get("notes", {})
    frappe.logger().info(
        f"[Razorpay Webhook] payment_id={payment_id}, amount={amount}, desc={description}"
    )
    # --- Duplicate check ---
    existing = frappe.db.get_value(
        "Payment Entry",
        {"reference_no": payment_id, "docstatus": ["!=", 2]},
        "name"
    )
    if existing:
        frappe.logger().info(f"[Razorpay Webhook] Duplicate - PE already exists: {existing}")
        return {"status": "duplicate", "payment_entry": existing}
    # --- Find the Sales Invoice ---
    invoice_name = extract_invoice_name(description, notes)
    if not invoice_name:
        frappe.log_error(
            f"Could not extract invoice name.\ndescription={description}\nnotes={notes}",
            "Razorpay Webhook - No Invoice Found"
        )
        return {"status": "error", "message": "Could not identify Sales Invoice from payment data"}
    # Verify invoice exists and is unpaid
    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["name", "outstanding_amount", "currency", "customer", "company"],
        as_dict=True
    )
    if not invoice:
        frappe.log_error(
            f"Sales Invoice {invoice_name} not found",
            "Razorpay Webhook - Invoice Missing"
        )
        return {"status": "error", "message": f"Sales Invoice {invoice_name} not found"}
    if invoice.outstanding_amount <= 0:
        frappe.logger().info(f"[Razorpay Webhook] Invoice {invoice_name} already paid")
        return {"status": "already_paid", "invoice": invoice_name}
    # --- Create and submit Payment Entry ---
    try:
        # Switch to Administrator to bypass guest permission restrictions
        frappe.set_user("Administrator")
        pe = create_payment_entry(
            invoice=invoice,
            payment_id=payment_id,
            amount=amount,
            currency=currency
        )
        return {
            "status": "success",
            "payment_entry": pe.name,
            "invoice": invoice_name,
            "amount": amount
        }
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Razorpay Webhook - Payment Entry Failed for {invoice_name}"
        )
        return {"status": "error", "message": f"Payment Entry creation failed. Check Error Log."}
    finally:
        # Always restore guest user after
        frappe.set_user("Guest")
def extract_invoice_name(description: str, notes: dict) -> str:
    """
    Extract Sales Invoice name from:
    1. description: "Payment Request for ACC-SINV-2026-00754"
    2. notes dict keys/values
    3. Any SINV pattern in description
    """
    # Pattern 1: Standard ERPNext description format
    # "Payment Request for ACC-SINV-2026-00754"
    match = re.search(r'([\w-]+-SINV-[\d-]+)', description)
    if match:
        return match.group(1)
    # Pattern 2: notes may have reference_name or invoice key
    for key in ("reference_name", "invoice", "sales_invoice", "sinv"):
        if key in notes:
            return notes[key]
    # Pattern 3: scan all note values for SINV pattern
    for val in notes.values():
        if isinstance(val, str):
            match = re.search(r'([\w-]+-SINV-[\d-]+)', val)
            if match:
                return match.group(1)
    return None
def create_payment_entry(invoice: dict, payment_id: str, amount: float, currency: str) -> object:
    """
    Creates and submits a Payment Entry linked to the Sales Invoice.
    Sets reference_no (Cheque/Reference No) = Razorpay payment_id
    """
    # Get Razorpay bank account from Payment Gateway Account
    payment_account = get_razorpay_payment_account(invoice.company, currency)
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type       = "Receive"
    pe.posting_date       = frappe.utils.today()
    pe.company            = invoice.company
    pe.mode_of_payment    = "Razorpay"
    pe.party_type         = "Customer"
    pe.party              = invoice.customer
    pe.paid_from          = get_receivable_account(invoice.company)
    pe.paid_to            = payment_account
    pe.paid_amount        = amount
    pe.received_amount    = amount
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    # This is the Cheque/Reference No field — where payment_id goes
    pe.reference_no   = payment_id
    pe.reference_date = frappe.utils.today()
    pe.remarks = f"Razorpay Payment | ID: {payment_id} | Invoice: {invoice.name}"
    # Link to Sales Invoice
    pe.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": invoice.name,
        "allocated_amount": invoice.outstanding_amount,
        "total_amount": invoice.outstanding_amount,
        "outstanding_amount": invoice.outstanding_amount,
    })
    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.validate()
    pe.save(ignore_permissions=True)
    pe.submit()
    frappe.db.commit()
    frappe.logger().info(
        f"[Razorpay Webhook] Payment Entry {pe.name} submitted. Invoice {invoice.name} → Paid"
    )
    return pe
def get_razorpay_payment_account(company: str, currency: str) -> str:
    """
    Get the bank/payment account linked to Razorpay Payment Gateway Account.
    Falls back to default bank account.
    """
    account = frappe.db.get_value(
        "Payment Gateway Account",
        {"payment_gateway": "Razorpay", "currency": currency},
        "payment_account"
    )
    if account:
        return account
    # Fallback: try without currency filter
    account = frappe.db.get_value(
        "Payment Gateway Account",
        {"payment_gateway": "Razorpay"},
        "payment_account"
    )
    if account:
        return account
    # Last resort: get default bank account for company
    account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Bank", "is_group": 0},
        "name"
    )
    if not account:
        frappe.throw(f"No payment account found for Razorpay / company {company}")
    return account
def get_receivable_account(company: str) -> str:
    """Get the default receivable account for the company."""
    account = frappe.db.get_value(
        "Company", company, "default_receivable_account"
    )
    if not account:
        account = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Receivable", "is_group": 0},
            "name"
        )
    return account
