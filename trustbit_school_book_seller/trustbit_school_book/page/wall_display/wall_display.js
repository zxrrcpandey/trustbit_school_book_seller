frappe.pages["wall-display"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Wall Display",
		single_column: true,
	});

	// Hide Frappe UI for fullscreen
	$(".navbar").hide();
	$(".page-head").hide();
	$('[data-page-container="true"]').css("margin-left", 0);
	$("body").css("overflow", "hidden");

	page.$wall = $('<div class="wall-display"></div>').appendTo(page.body);

	// Load wall display CSS
	$("head").append('<link rel="stylesheet" href="/assets/trustbit_school_book_seller/css/wall_display.css">');

	refresh_wall(page);

	// Auto-refresh every 30 seconds
	page._refresh_interval = setInterval(function () {
		refresh_wall(page);
	}, 30000);
};

frappe.pages["wall-display"].on_page_hide = function () {
	// Restore Frappe UI
	$(".navbar").show();
	$(".page-head").show();
	$("body").css("overflow", "");
	if (this._refresh_interval) clearInterval(this._refresh_interval);
};

function refresh_wall(page) {
	var $w = page.$wall;
	var today = frappe.datetime.get_today();

	Promise.all([
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_dashboard_kpis", { from_date: today, to_date: today }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_employee_performance", { date: today }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_bundle_stock_report"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_po_status"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_recent_invoices", { limit: 5 }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_revenue_trend", { days: 7 }),
	]).then(function ([kpis, employees, bundles, po, invoices, trend]) {
		var now = new Date();
		var time_str = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
		var date_str = now.toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

		var html = '';

		// Header
		html += '<div class="wall-header">'
			+ '<div class="wall-title">⭐ <span>KHANDELWAL GENERAL STORES</span> — LIVE</div>'
			+ '<div class="wall-live"><div class="live-dot"></div> LIVE</div>'
			+ '<div class="wall-datetime">' + date_str + ' │ ' + time_str + '</div></div>';

		// Big KPIs
		var goal = 100000;
		var pct = Math.min(100, Math.round((kpis.revenue / goal) * 100));
		html += '<div class="wall-kpis">'
			+ wall_kpi("💰", "TODAY's REVENUE", wfmt(kpis.revenue), "▲ " + Math.abs(kpis.revenue_change) + "% vs yesterday")
			+ wall_kpi("📦", "TODAY's ORDERS", kpis.order_count, "📚 " + kpis.bundles_sold + " Bundles │ 🛒 " + kpis.loose_items + " Loose")
			+ '<div class="wall-kpi"><div class="wk-label">🎯 DAILY GOAL</div>'
			+ '<div class="wall-goal-bg"><div class="wall-goal-fill" style="width:' + pct + '%;">' + pct + '%</div></div>'
			+ '<div class="wall-goal-text"><span>' + wfmt(kpis.revenue) + '</span><span>' + wfmt(Math.max(0, goal - kpis.revenue)) + ' to go</span></div></div>'
			+ '</div>';

		// Employee Counters
		html += '<div class="wall-counters">';
		(employees || []).slice(0, 4).forEach(function (e) {
			var emp_pct = Math.min(100, Math.round((e.revenue / 35000) * 100));
			var color = emp_pct >= 70 ? "#28a745" : emp_pct >= 40 ? "#f57c00" : "#dc3545";
			html += '<div class="wall-counter">'
				+ '<div class="wc-name">👤 ' + e.full_name + '</div>'
				+ '<div class="wc-profile">' + (e.pos_profile || "") + '</div>'
				+ '<div class="wc-stats"><span class="wc-revenue">' + wfmt(e.revenue) + '</span><span class="wc-orders">' + e.orders + ' orders</span></div>'
				+ '<div class="wc-bar-bg"><div class="wc-bar-fill" style="width:' + emp_pct + '%;background:' + color + ';"></div></div>'
				+ '<div class="wc-pct" style="color:' + color + ';">' + emp_pct + '% of goal</div></div>';
		});
		html += '</div>';

		// Two panels: PO Alerts + Bundle Stock
		html += '<div class="wall-panels">';

		// PO Alerts
		html += '<div class="wall-panel"><h3>⚠️ URGENT — ACTION NEEDED</h3>';
		if (po.stuck && po.stuck.length) {
			html += '<div class="wp-title text-red">STUCK PURCHASE ORDERS</div>';
			po.stuck.slice(0, 3).forEach(function (p) {
				html += '<div class="wall-alert red"><div class="wa-title">' + p.name + ' — ' + p.supplier + '</div>'
					+ '<div class="wa-detail">' + p.age + ' days │ ' + p.followups + ' follow-ups</div></div>';
			});
		}
		if (po.need_followup && po.need_followup.length) {
			html += '<div class="wp-title text-orange">NEED FOLLOW-UP</div>';
			po.need_followup.slice(0, 2).forEach(function (p) {
				html += '<div class="wall-alert yellow"><div class="wa-title">' + p.name + ' — ' + p.supplier + '</div>'
					+ '<div class="wa-detail">Due: ' + p.next_date + '</div></div>';
			});
		}
		if (po.on_the_way && po.on_the_way.length) {
			html += '<div class="wp-title text-green">🚚 ON THE WAY</div>';
			po.on_the_way.slice(0, 2).forEach(function (p) {
				html += '<div class="wall-alert green"><div class="wa-title">' + p.name + ' — ' + p.supplier + '</div></div>';
			});
		}
		html += '</div>';

		// Bundle Stock Alerts
		html += '<div class="wall-panel"><h3>📚 BUNDLE STOCK ALERTS</h3>';
		var out_bundles = (bundles || []).filter(b => b.status === "out");
		var low_bundles = (bundles || []).filter(b => b.status === "low");
		var ok_bundles = (bundles || []).filter(b => b.status === "ok");

		if (out_bundles.length) {
			html += '<div class="wp-title text-red">🔴 OUT OF STOCK</div>';
			out_bundles.slice(0, 3).forEach(function (b) {
				html += '<div class="wall-alert red"><div class="wa-title">' + (b.description || b.bundle) + ' — 0 sets</div>'
					+ '<div class="wa-detail">Blocking: ' + (b.blocking_item || "—") + '</div></div>';
			});
		}
		if (low_bundles.length) {
			html += '<div class="wp-title text-orange">🟡 LOW STOCK (&lt;5 sets)</div>';
			low_bundles.slice(0, 3).forEach(function (b) {
				html += '<div class="wall-alert yellow"><div class="wa-title">' + (b.description || b.bundle) + ' — ' + b.sellable_sets + ' sets</div>'
					+ '<div class="wa-detail">Goal: ' + (b.goal || "—") + ' │ Sold: ' + b.sold + '</div></div>';
			});
		}
		if (ok_bundles.length) {
			html += '<div class="wp-title text-green">🟢 GOOD STOCK: ' + ok_bundles.length + ' bundles</div>';
		}
		html += '</div>';
		html += '</div>';

		// Revenue chart + ratio
		var bundle_pct = kpis.revenue > 0 ? Math.round((kpis.bundle_revenue / kpis.revenue) * 100) : 0;
		html += '<div class="wall-chart-row">';
		html += '<div class="wall-chart"><h3>📊 Revenue — Last 7 Days</h3><div class="wall-bars">';
		var max = Math.max(...(trend || []).map(d => d.revenue), 1);
		(trend || []).forEach(function (d) {
			var h = Math.round((d.revenue / max) * 80);
			var isToday = d.date === today;
			var dt = new Date(d.date);
			var label = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][dt.getDay()];
			var color = isToday ? "linear-gradient(to top, #28a745, #5e64ff)" : "linear-gradient(to top, #5e64ff, #8b5cf6)";
			html += '<div class="wb-col"><div class="wb-val">' + Math.round(d.revenue / 1000) + 'K</div>'
				+ '<div class="wb-bar" style="height:' + h + 'px;background:' + color + ';"></div>'
				+ '<div class="wb-label' + (isToday ? " wb-today" : "") + '">' + label + '</div></div>';
		});
		html += '</div></div>';

		html += '<div class="wall-ratio"><h3>📈 Bundle vs Loose</h3>'
			+ '<div class="wall-ratio-bar"><div class="wrb-bundle" style="width:' + bundle_pct + '%;">' + bundle_pct + '%</div>'
			+ '<div class="wrb-loose" style="width:' + (100 - bundle_pct) + '%;">' + (100 - bundle_pct) + '%</div></div>'
			+ '<div class="wall-ratio-labels"><span>📚 ' + wfmt(kpis.bundle_revenue) + '</span><span>🛒 ' + wfmt(kpis.loose_revenue) + '</span></div>'
			+ '<div class="wall-week-total">' + wfmt(kpis.revenue) + '</div>'
			+ '<div class="wall-week-label">Today\'s Total</div></div>';
		html += '</div>';

		// Footer ticker
		html += '<div class="wall-footer"><div class="wall-ticker">';
		(invoices || []).forEach(function (inv) {
			html += '<span class="wt-item"><span class="wt-time">' + (inv.time || "") + '</span> '
				+ inv.name + ' ' + inv.customer_name + ' ' + wfmt(inv.grand_total) + ' — ' + (inv.user_name || "") + '</span>';
		});
		html += '</div><div class="wall-refresh">🔄 Auto-refreshes every 30s</div></div>';

		$w.html(html);
	});
}

function wfmt(n) { return "₹" + (Math.round(n) || 0).toLocaleString("en-IN"); }

function wall_kpi(icon, label, value, sub) {
	return '<div class="wall-kpi"><div class="wk-label">' + icon + ' ' + label + '</div>'
		+ '<div class="wk-value">' + value + '</div>'
		+ '<div class="wk-sub">' + (sub || "") + '</div></div>';
}
