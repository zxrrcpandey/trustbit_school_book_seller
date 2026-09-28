"""Purchase Order approval by the Shop Owners.

The workflow itself ("Purchase Order Approval": Draft -> Pending Approval ->
Approved / Rejected, Approved -> Cancelled) is shipped as a fixture. A Frappe
workflow submits the PO the moment a Shop Owner clicks Approve and emails the
Shop Owners an Approve button. This module adds what the workflow cannot do:

- only a Shop Owner may submit (= approve) or cancel a PO, even through the API.
  Without this, a direct submit slips past the workflow and is silently
  stamped "Approved" (frappe's set_workflow_state_on_action).
- Reject needs a reason, so it is a form button backed by reject_purchase_order().
  The Reject transition's condition (`doc.custom_rejection_reason`) keeps it out
  of the Actions menu and out of the approval email, which has no way to ask.
- a bell notification to the Shop Owners when a PO is sent for approval, and a
  bell + email to the creator when it is approved or rejected.
- the approved PO is emailed to the supplier with its PDF.
- the Approve button in the owners' email works without logging in (apply_action /
  confirm_action below). frappe >= 15.1xx made the email's confirm step login-only,
  and on this site a login means password + authenticator code with a 1-hour session.

Every hook is a no-op unless this workflow is the active one on Purchase Order,
so deactivating the workflow switches the whole feature off.
"""

from email.utils import formataddr
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_workflow_name
from frappe.utils import (
	add_days,
	escape_html,
	fmt_money,
	formatdate,
	get_datetime,
	get_fullname,
	get_url_to_form,
	today,
	validate_email_address,
)
from frappe.utils.verified_command import verify_request

WORKFLOW = "Purchase Order Approval"
SHOP_OWNER = "Shop Owner"
PENDING = "Pending Approval"
APPROVED = "Approved"
REJECTED = "Rejected"


def _approval_active():
	return get_workflow_name("Purchase Order") == WORKFLOW


def _quiet():
	"""Imports, patches and installs must never notify anyone."""
	f = frappe.flags
	return f.in_import or f.in_install or f.in_patch or f.in_migrate


# --------------------------------------------------------------------------
# doc_events
# --------------------------------------------------------------------------


def only_shop_owner(doc, method=None):
	"""before_submit / before_cancel: approving (submitting) and cancelling are Shop Owner only."""
	if not _approval_active() or SHOP_OWNER in frappe.get_roles():
		return
	if method == "before_cancel":
		frappe.throw(_("Only a Shop Owner can cancel a Purchase Order."), frappe.PermissionError)
	frappe.throw(
		_("Only a Shop Owner can approve a Purchase Order. Use Actions → Send for Approval instead."),
		frappe.PermissionError,
	)


def clear_stale_rejection_reason(doc, method=None):
	"""validate: the reason belongs to the current rejection only, so sending the PO
	for approval again clears it (the timeline comment keeps the history)."""
	if doc.get("custom_rejection_reason") and doc.get("workflow_state") != REJECTED:
		doc.custom_rejection_reason = None


def notify_on_state_change(doc, method=None):
	"""on_update (runs on Save AND on Submit): tell the right people when the state moves."""
	if _quiet() or not _approval_active() or not doc.has_value_changed("workflow_state"):
		return

	if doc.workflow_state == PENDING:
		_notify_shop_owners(doc)
	elif doc.workflow_state == REJECTED:
		_notify_creator(doc, rejected=True)
	elif doc.workflow_state == APPROVED and doc.docstatus == 1:
		_notify_creator(doc, rejected=False)
		send_to_supplier(doc)


# --------------------------------------------------------------------------
# Reject with a reason
# --------------------------------------------------------------------------


@frappe.whitelist()
def reject_purchase_order(name, reason):
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Please give a reason for rejecting."))
	if SHOP_OWNER not in frappe.get_roles():
		frappe.throw(_("Only a Shop Owner can reject a Purchase Order."), frappe.PermissionError)

	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("write")
	if doc.workflow_state != PENDING:
		frappe.throw(_("{0} is not waiting for approval (it is {1}).").format(name, doc.workflow_state))

	# apply_workflow reloads the doc from the database, and the Reject transition
	# is only offered once a reason is stored, so store it first (same transaction).
	doc.db_set("custom_rejection_reason", reason, update_modified=False)
	doc = apply_workflow(doc.as_dict(), "Reject")
	doc.add_comment("Comment", _("Rejected: {0}").format(escape_html(reason)))
	return doc.as_dict()


# --------------------------------------------------------------------------
# One-tap Approve from the owners' email (hooks: override_whitelisted_methods)
# --------------------------------------------------------------------------


def _one_tap(doctype, action, user):
	"""A Shop Owner's Approve link for a Purchase Order. Anything else — other
	doctypes, Reject/Cancel, other users — keeps frappe's own login-only flow."""
	return (
		doctype == "Purchase Order"
		and action == "Approve"
		and _approval_active()
		and bool(user)
		and bool(frappe.db.get_value("User", user, "enabled"))
		and SHOP_OWNER in frappe.get_roles(user)
	)


@frappe.whitelist(allow_guest=True)
def apply_action(action, doctype, docname, current_state, user=None, last_modified=None):
	"""The page the email's Approve button opens. For a one-tap link its button
	confirms directly (no login) and "View document" opens the CURRENT PO as a PDF
	through a share key, so an owner can check a PO edited after the email."""
	from frappe.workflow.doctype.workflow_action import workflow_action as wa

	if not _one_tap(doctype, action, user):
		return wa.apply_action(action, doctype, docname, current_state, user=user, last_modified=last_modified)
	if not verify_request():
		return

	doc = frappe.get_doc(doctype, docname)
	state = wa.get_doc_workflow_state(doc)
	if state != current_state:
		return wa.return_link_expired_page(doc, state)

	key = doc.get_document_share_key(expires_on=add_days(today(), 7))
	frappe.db.commit()  # a GET request is rolled back at the end, and the key must exist
	frappe.respond_as_web_page(
		title=None,
		html=None,
		indicator_color="blue",
		template="confirm_workflow_action",
		context={
			"title": doc.name,
			"doctype": doctype,
			"docname": doc.name,
			"action": action,
			"action_link": wa.get_confirm_workflow_action_url(doc, action, user),
			# edits made after the email are allowed; the page just says so
			"alert_doc_change": bool(last_modified) and get_datetime(doc.modified) != get_datetime(last_modified),
			"is_guest": False,  # button goes straight to confirm_action, which lets the owner through
			"pdf_link": "/api/method/frappe.utils.print_format.download_pdf?"
			+ urlencode(
				{
					"doctype": doctype,
					"name": doc.name,
					"format": doc.meta.default_print_format or "Standard",
					"no_letterhead": 0,
					"key": key,
				}
			),
		},
	)


@frappe.whitelist(allow_guest=True)
def confirm_action(doctype, docname, user, action):
	"""Approve from a signed one-tap link without a login session, acting as the
	Shop Owner named in the link (signature checked by verify_request)."""
	from frappe.workflow.doctype.workflow_action import workflow_action as wa

	if frappe.session.user != "Guest" or not _one_tap(doctype, action, user):
		if frappe.session.user == "Guest":
			raise frappe.PermissionError  # frappe's own confirm_action is login-only
		return wa.confirm_action(doctype, docname, user, action)
	if not verify_request():
		return

	frappe.set_user(user)
	try:
		doc = frappe.get_doc(doctype, docname)
		state = wa.get_doc_workflow_state(doc)
		if state != PENDING:
			return wa.return_link_expired_page(doc, state)
		try:
			doc = apply_workflow(doc, action)
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(f"Purchase Order email approval failed: {docname}")
			frappe.db.commit()  # keep the Error Log: a GET request is rolled back at the end
			frappe.respond_as_web_page(
				_("Not approved"),
				_("{0} could not be approved: {1}<br><br>Please open it in ERPNext.").format(
					frappe.bold(docname), escape_html(frappe.utils.strip_html(str(e)))
				),
				indicator_color="red",
			)
			return
		frappe.db.commit()
		wa.return_success_page(doc)
	finally:
		frappe.set_user("Guest")


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


def _summary(doc):
	return "{0} ({1}, {2})".format(
		doc.name, doc.supplier_name or doc.supplier, fmt_money(doc.grand_total, currency=doc.currency)
	)


def _bell(users, doc, subject, message=""):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	users = [u for u in users if u and u not in ("Guest", "Administrator")]
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"document_type": doc.doctype,
			"document_name": doc.name,
			"subject": subject,
			"email_content": message,
			"from_user": frappe.session.user,
		},
	)


def _shop_owners():
	from frappe.utils.user import get_users_with_role

	return get_users_with_role(SHOP_OWNER)


def _notify_shop_owners(doc):
	"""Bell only: the workflow's own email (with the Approve button and the PDF)
	already goes to every Shop Owner except the PO's creator."""
	others = [u for u in _shop_owners() if u != frappe.session.user]
	_bell(
		others,
		doc,
		_("{0} sent Purchase Order {1} for your approval").format(
			get_fullname(frappe.session.user), _summary(doc)
		),
	)


def _notify_creator(doc, rejected):
	creator = doc.owner
	if creator == frappe.session.user or creator in ("Guest", "Administrator"):
		return  # a Shop Owner approving their own PO needs no message
	user = frappe.db.get_value("User", creator, ["enabled", "email"], as_dict=True)
	if not user or not user.enabled:
		return  # never mail a disabled account (the April 2026 bounce loop came from one)

	by = get_fullname(frappe.session.user)
	link = get_url_to_form(doc.doctype, doc.name)
	if rejected:
		reason = escape_html(doc.custom_rejection_reason or "")
		subject = _("Purchase Order {0} was REJECTED by {1}").format(_summary(doc), by)
		body = _(
			"<p><b>{0}</b> rejected Purchase Order <b>{1}</b>.</p>"
			"<p><b>Reason:</b> {2}</p>"
			"<p>Correct the Purchase Order, then use <b>Actions → Send for Approval</b> to send it again.</p>"
			'<p><a href="{3}">Open {1}</a></p>'
		).format(by, doc.name, reason, link)
		bell_message = _("Reason: {0}").format(reason)
	else:
		subject = _("Purchase Order {0} was approved by {1}").format(_summary(doc), by)
		body = _(
			"<p><b>{0}</b> approved Purchase Order <b>{1}</b>. It is now submitted.</p>"
			'<p><a href="{2}">Open {1}</a></p>'
		).format(by, doc.name, link)
		bell_message = ""

	_bell([creator], doc, subject, bell_message)
	if user.email and validate_email_address(user.email):
		frappe.sendmail(
			recipients=[user.email],
			subject=subject,
			message=body,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)


# --------------------------------------------------------------------------
# Email the approved PO to the supplier
# --------------------------------------------------------------------------


def _supplier_email(doc):
	for email in (doc.get("contact_email"), frappe.db.get_value("Supplier", doc.supplier, "email_id")):
		email = validate_email_address((email or "").strip())
		if email:
			return email


def _supplier_message(doc):
	"""The shop's own "Purchase Order" Email Template (the one staff pick when they
	email a PO by hand), so suppliers see the wording they already know."""
	if frappe.db.exists("Email Template", "Purchase Order"):
		try:
			return frappe.get_doc("Email Template", "Purchase Order").get_formatted_email(doc.as_dict())["message"]
		except Exception:
			frappe.log_error(f"Purchase Order approval: Email Template failed for {doc.name}")
	return _(
		"<p>Dear Sir/Madam,</p>"
		"<p>Please find attached our Purchase Order <b>{0}</b> dated {1}.</p>"
		"<p>Kindly process the order and share your confirmation for the same.</p>"
	).format(doc.name, formatdate(doc.transaction_date))


def send_to_supplier(doc):
	email = _supplier_email(doc)
	if not email:
		note = _(
			"Not emailed to the supplier: there is no email address on this Purchase Order or on Supplier {0}."
		).format(doc.supplier)
		doc.add_comment("Comment", note)
		_bell([doc.owner], doc, _("{0}: {1}").format(doc.name, note))
		return

	from frappe.core.doctype.communication.email import _make

	# Send as the shop's mailbox, not as the approver: _make() would otherwise use
	# the approver's own yahoo/gmail address, which Zoho cannot send for.
	account = frappe.db.get_value(
		"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, ["email_id"], as_dict=True
	)
	sender = formataddr((doc.company, account.email_id)) if account and account.email_id else None
	revised = _("Revised ") if doc.amended_from else ""

	_make(
		doctype=doc.doctype,
		name=doc.name,
		subject=_("{0}Purchase Order {1} from {2}").format(revised, doc.name, doc.company),
		content=_supplier_message(doc),
		recipients=email,
		sender=sender,
		send_email=True,
		print_format=doc.meta.default_print_format or "Standard",
		print_letterhead=True,
	)
