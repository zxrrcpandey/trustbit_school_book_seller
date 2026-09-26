// Purchase Order approval (workflow "Purchase Order Approval", server side in po_approval.py).
// Reject needs a reason, so a Shop Owner rejects with this button, never from the
// approval email; the workflow's own Reject action stays hidden until a reason exists.
frappe.ui.form.on("Purchase Order", {
	refresh: function (frm) {
		const state = frm.doc.workflow_state;
		if (frm.is_new() || !state) return;

		if (state === "Pending Approval") {
			frm.dashboard.set_headline_alert(
				__("Waiting for a Shop Owner to approve this Purchase Order."),
				"orange"
			);
			if (frappe.user.has_role("Shop Owner")) {
				frm.add_custom_button(__("Reject"), () => reject_with_reason(frm)).addClass(
					"btn-danger"
				);
			}
		} else if (state === "Rejected" && frm.doc.custom_rejection_reason) {
			frm.dashboard.set_headline_alert(
				__("Rejected: {0} — correct it, then use Actions → Send for Approval.", [
					frappe.utils.escape_html(frm.doc.custom_rejection_reason),
				]),
				"red"
			);
		}
	},
});

function reject_with_reason(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Please save your changes first."));
		return;
	}
	frappe.prompt(
		{
			fieldname: "reason",
			fieldtype: "Small Text",
			label: __("Why is this Purchase Order rejected?"),
			reqd: 1,
		},
		(values) => {
			frappe
				.call({
					method: "trustbit_school_book_seller.po_approval.reject_purchase_order",
					args: { name: frm.doc.name, reason: values.reason },
					freeze: true,
					freeze_message: __("Rejecting..."),
				})
				.then(() => frm.reload_doc());
		},
		__("Reject {0}", [frm.doc.name]),
		__("Reject")
	);
}
