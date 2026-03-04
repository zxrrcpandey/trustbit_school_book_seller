import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def validate_privilege_card_on_doc(doc, method):
    """Validate privilege card on Sales Order / Sales Invoice during validate.

    If custom_privilege_card is set:
    1. Verify card is valid and active
    2. Apply discount to all items
    3. Set custom_privilege_card_discount

    If custom_privilege_card is cleared, remove discounts.
    """
    card_name = doc.get("custom_privilege_card")
    if not card_name:
        if doc.get("custom_privilege_card_discount"):
            doc.custom_privilege_card_discount = 0
        return

    card = frappe.get_doc("Privilege Card", card_name)

    if card.status != "Active":
        frappe.throw(
            _("Privilege Card {0} is {1}. Cannot apply discount.").format(
                card_name, card.status
            )
        )

    if card.expiry_date and getdate(card.expiry_date) < getdate(today()):
        card.db_set("status", "Expired")
        frappe.throw(
            _("Privilege Card {0} expired on {1}").format(card_name, card.expiry_date)
        )

    discount = flt(card.discount_percent)
    doc.custom_privilege_card_discount = discount

    for item in doc.items:
        item.discount_percentage = discount
        # Recalculate rate from price_list_rate and discount
        price_list_rate = flt(item.price_list_rate) or flt(item.rate)
        if price_list_rate:
            item.discount_amount = flt(price_list_rate * discount / 100, item.precision("discount_amount"))
            item.rate = flt(price_list_rate - item.discount_amount, item.precision("rate"))
            item.amount = flt(item.rate * flt(item.qty), item.precision("amount"))


def log_privilege_card_usage(doc, method):
    """Log privilege card usage when SO/SI is submitted.

    Appends a row to the Privilege Card's usage_log child table.
    Updates total_times_used and total_discount_given.
    """
    card_name = doc.get("custom_privilege_card")
    if not card_name:
        return

    card = frappe.get_doc("Privilege Card", card_name)

    total_discount = sum(
        flt(item.price_list_rate or item.rate) * flt(item.qty) * flt(item.discount_percentage) / 100
        for item in doc.items
    )

    card.append("usage_log", {
        "document_type": doc.doctype,
        "document_name": doc.name,
        "posting_date": doc.get("posting_date") or doc.get("transaction_date") or today(),
        "total_discount_amount": total_discount,
        "created_by": frappe.session.user,
    })

    card.total_times_used = len(card.usage_log)
    card.total_discount_given = sum(flt(row.total_discount_amount) for row in card.usage_log)
    card.flags.ignore_permissions = True
    card.save()


def expire_cards_daily():
    """Daily scheduler: Mark active cards past their expiry date as Expired."""
    expired = frappe.get_all(
        "Privilege Card",
        filters={
            "status": "Active",
            "expiry_date": ["<", today()],
            "expiry_date": ["is", "set"],
        },
        pluck="name",
    )

    for card_name in expired:
        frappe.db.set_value("Privilege Card", card_name, "status", "Expired")

    if expired:
        frappe.db.commit()
        frappe.logger().info(f"Expired {len(expired)} privilege cards: {', '.join(expired)}")
