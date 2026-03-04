// Privilege Card integration for Sales Order and Sales Invoice
// Allows scanning/selecting a Privilege Card to apply discount to all items
(function () {
	var TARGET_DOCTYPES = ["Sales Order", "Sales Invoice"];

	TARGET_DOCTYPES.forEach(function (dt) {
		frappe.ui.form.on(dt, {
			refresh: function (frm) {
				if (frm.doc.docstatus === 0) {
					frm.add_custom_button(
						__("Apply Privilege Card"),
						function () {
							open_privilege_card_dialog(frm);
						},
						__("Actions")
					);
				}

				if (frm.doc.custom_privilege_card) {
					show_card_banner(frm);
				}
			},

			custom_privilege_card: function (frm) {
				if (frm.doc.custom_privilege_card) {
					validate_and_apply_card(
						frm,
						frm.doc.custom_privilege_card
					);
				} else {
					clear_card_discounts(frm);
				}
			},
		});
	});

	function open_privilege_card_dialog(frm) {
		var d = new frappe.ui.Dialog({
			title: __("Apply Privilege Card"),
			fields: [
				{
					fieldname: "card",
					fieldtype: "Link",
					label: __("Privilege Card"),
					options: "Privilege Card",
					reqd: 1,
					get_query: function () {
						return {
							filters: { status: "Active" },
						};
					},
					description: __(
						"Scan barcode or type card number (e.g. PC-00001)"
					),
				},
			],
			size: "small",
			primary_action_label: __("Apply"),
			primary_action: function () {
				var card = d.get_value("card");
				d.hide();
				validate_and_apply_card(frm, card);
			},
		});
		d.show();
		// Auto-focus the card field for quick scanning
		setTimeout(function () {
			d.fields_dict.card.$input.focus();
		}, 300);
	}

	function validate_and_apply_card(frm, card_name) {
		frappe.call({
			method: "trustbit_school_book_seller.api.validate_privilege_card",
			args: { card_name: card_name },
			freeze: true,
			freeze_message: __("Validating privilege card..."),
			callback: function (r) {
				if (!r.message) return;

				var info = r.message;
				frm.set_value("custom_privilege_card", card_name);
				frm.set_value(
					"custom_privilege_card_discount",
					info.discount_percent
				);

				// Apply discount to each item row
				(frm.doc.items || []).forEach(function (item) {
					frappe.model.set_value(
						item.doctype,
						item.name,
						"discount_percentage",
						info.discount_percent
					);
				});

				// Recalculate rates and totals after applying discount
				frm.cscript.calculate_taxes_and_totals();
				frm.refresh_fields();
				frm.dirty();

				frappe.show_alert(
					{
						message: __(
							"Privilege Card applied: {0}% discount for {1} ({2})",
							[
								info.discount_percent,
								info.holder_name,
								info.card_type,
							]
						),
						indicator: "green",
					},
					7
				);

				// Auto-fill school name from card if not already set
				if (info.school && !frm.doc.custom_school_name) {
					frm.set_value("custom_school_name", info.school);
				}

				show_card_banner(frm);
			},
		});
	}

	function clear_card_discounts(frm) {
		frm.set_value("custom_privilege_card_discount", 0);
		(frm.doc.items || []).forEach(function (item) {
			frappe.model.set_value(
				item.doctype,
				item.name,
				"discount_percentage",
				0
			);
		});
		frm.cscript.calculate_taxes_and_totals();
		frm.refresh_fields();
		frm.dirty();
		frm.dashboard.set_headline("");

		frappe.show_alert(
			{
				message: __("Privilege Card removed. Discounts cleared."),
				indicator: "orange",
			},
			5
		);
	}

	function show_card_banner(frm) {
		if (!frm.doc.custom_privilege_card) return;

		var discount = frm.doc.custom_privilege_card_discount || 0;
		var msg = __(
			'<strong>Privilege Card</strong> {0} applied &mdash; <strong>{1}%</strong> discount on all items',
			[frm.doc.custom_privilege_card, discount]
		);
		frm.dashboard.set_headline(msg);
	}
})();
