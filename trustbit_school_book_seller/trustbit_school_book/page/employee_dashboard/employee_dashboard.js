frappe.pages["employee-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "My Dashboard",
		single_column: true,
	});

	page.add_button(__("Refresh"), () => render_employee_dashboard(page), "refresh");
	page.$dashboard = $('<div class="employee-dashboard-container"></div>').appendTo(page.body);
	$("head").append('<link rel="stylesheet" href="/assets/trustbit_school_book_seller/css/owner_dashboard.css">');

	render_employee_dashboard(page);
};

function render_employee_dashboard(page) {
	var $d = page.$dashboard;
	var today = frappe.datetime.get_today();
	var user = frappe.session.user;

	$d.html('<div class="text-center" style="padding:60px;"><i class="fa fa-spinner fa-spin fa-3x"></i></div>');

	Promise.all([
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_dashboard_kpis", { from_date: today, to_date: today, user: user }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_recent_invoices", { limit: 10, user: user }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_bundle_stock_report"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_payment_breakdown", { date: today }),
	]).then(function ([kpis, invoices, bundles, payments]) {
		var html = "";

		// Header
		html += '<div style="margin-bottom:16px;"><h2 style="font-size:16px;">👤 Welcome, ' + frappe.session.user_fullname + '</h2>'
			+ '<div style="font-size:12px;color:#888;">Shift: Today | ' + frappe.datetime.get_today() + '</div></div>';

		// KPI Cards
		html += '<div class="kpi-row">';
		html += kpi_card("💰", "My Revenue", fmtc(kpis.revenue));
		html += kpi_card("📦", "My Orders", kpis.order_count);
		html += kpi_card("📚", "Bundles Sold", kpis.bundles_sold);
		html += kpi_card("🏷️", "Items Total", kpis.total_qty);
		html += '</div>';

		// Goal
		var goal = 35000;
		var pct = Math.min(100, Math.round((kpis.revenue / goal) * 100));
		html += '<div class="section goal-section">'
			+ '<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
			+ '<span style="font-size:12px;font-weight:600;">My Shift Goal</span>'
			+ '<span style="font-size:12px;color:#888;">' + fmtc(Math.max(0, goal - kpis.revenue)) + ' more to target</span></div>'
			+ '<div class="goal-bar-bg"><div class="goal-bar-fill" style="width:' + pct + '%;">' + pct + '%</div></div>'
			+ '<div class="goal-text"><span>' + fmtc(kpis.revenue) + '</span><span>Goal: ' + fmtc(goal) + '</span></div></div>';

		// Recent Invoices
		html += '<div class="section"><h2>📋 My Recent Invoices</h2>'
			+ '<table><thead><tr><th>Invoice</th><th>Customer</th><th class="tc">Items</th><th class="tr">Amount</th><th class="tc">Time</th><th class="tc">Type</th></tr></thead><tbody>';
		(invoices || []).forEach(function (inv) {
			var type_badge = inv.type === "bundle"
				? '<span class="badge-green" style="background:#e3f2fd;color:#1976d2;">📚 Bundle</span>'
				: '<span class="badge-yellow">🛒 Loose</span>';
			html += '<tr><td><strong>' + inv.name + '</strong></td>'
				+ '<td>' + inv.customer_name + '</td>'
				+ '<td class="tc">' + inv.total_qty + '</td>'
				+ '<td class="tr bold">' + fmtc(inv.grand_total) + '</td>'
				+ '<td class="tc">' + (inv.time || "") + '</td>'
				+ '<td class="tc">' + type_badge + '</td></tr>';
		});
		html += '</tbody></table></div>';

		// Two Column: Bundle Stock + Payments
		html += '<div class="two-col">';

		// Bundle stock
		html += '<div class="section"><h2>📚 Bundle Stock Check</h2>';
		(bundles || []).slice(0, 10).forEach(function (b) {
			var color = b.status === "out" ? "#dc3545" : b.status === "low" ? "#f57c00" : "#28a745";
			var badge = b.status === "out" ? '<span class="badge-red">Out</span>'
				: b.status === "low" ? '<span class="badge-yellow">Low</span>'
				: '<span class="badge-green">OK</span>';
			html += '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f2f5;">'
				+ '<span style="font-weight:500;font-size:13px;">' + (b.description || b.bundle) + '</span>'
				+ '<span style="font-weight:700;color:' + color + ';">' + b.sellable_sets + ' sets ' + badge + '</span></div>';
		});
		html += '</div>';

		// Payments
		html += '<div class="section"><h2>💰 My Payment Collection</h2><div class="payment-grid">';
		var colors = { "Cash": "#28a745", "UPI": "#1976d2", "Card": "#f57c00", "Credit Sale": "#7b1fa2" };
		(payments || []).forEach(function (p) {
			var c = colors[p.mode_of_payment] || "#666";
			html += '<div class="payment-card" style="border-left:3px solid ' + c + ';">'
				+ '<div class="payment-label">' + p.mode_of_payment + '</div>'
				+ '<div class="payment-value" style="color:' + c + ';">' + fmtc(p.amount) + '</div></div>';
		});
		html += '</div></div>';

		html += '</div>';

		$d.html(html);
	});
}

function fmtc(n) { return "₹" + (n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 }); }
function kpi_card(icon, label, value) {
	return '<div class="kpi-card"><div class="kpi-icon">' + icon + '</div>'
		+ '<div class="kpi-label">' + label + '</div>'
		+ '<div class="kpi-value">' + value + '</div></div>';
}
