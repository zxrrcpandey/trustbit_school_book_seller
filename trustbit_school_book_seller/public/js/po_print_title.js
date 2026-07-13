// When the desk Print page shows a Purchase Order, set the browser tab
// title to "<PO ID> - <Supplier Name>". The system print dialog
// (Ctrl+P / Print button -> Save as PDF) suggests the tab title as the
// filename; frappe's print.js titles the tab with the docname only.
(function () {
	function fix_po_print_title() {
		const route = frappe.get_route ? frappe.get_route() : [];
		if (route[0] !== "print" || route[1] !== "Purchase Order" || !route[2]) return;
		const po = route[2];
		frappe.db.get_value("Purchase Order", po, "supplier_name").then((r) => {
			const supplier = r && r.message && r.message.supplier_name;
			const cur = frappe.get_route();
			if (!supplier || cur[0] !== "print" || cur[2] !== po) return;
			document.title = po + " - " + supplier;
		});
	}

	function schedule_fix() {
		// print.js re-sets the title asynchronously once the doc loads —
		// re-apply a few times to win the race without patching core
		[400, 1200, 2500].forEach((ms) => setTimeout(fix_po_print_title, ms));
	}

	$(document).on("page-change", schedule_fix);
	if (frappe.router && frappe.router.on) frappe.router.on("change", schedule_fix);
})();
