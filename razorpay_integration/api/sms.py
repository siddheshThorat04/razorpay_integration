import frappe
from frappe import _


@frappe.whitelist()
def is_sms_enabled():
	return bool(frappe.db.get_single_value("SMS Settings", "sms_gateway_url"))


@frappe.whitelist()
def get_sms_messages(reference_doctype, reference_name):
	return frappe.get_all(
		"SMS Message",
		filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
		fields=["name", "mobile_no", "direction", "status", "message", "error", "creation", "owner"],
		order_by="creation asc",
	)


@frappe.whitelist()
def send_sms(reference_doctype, reference_name, to, message):
	from frappe.core.doctype.sms_settings.sms_settings import send_sms as core_send_sms

	if not to or not message:
		frappe.throw(_("Mobile number and message are required"))

	core_send_sms([to], message)

	return frappe.get_all(
		"SMS Message",
		filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
		fields=["name", "mobile_no", "direction", "status", "message", "error", "creation", "owner"],
		order_by="creation desc",
		limit_page_length=1,
	)
