frappe.pages["wall-display"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Wall Display",
		single_column: true,
	});

	// Force fullscreen
	$("head").append('<link rel="stylesheet" href="/assets/trustbit_school_book_seller/css/wall_display.css">');
	$(".navbar, .page-head, footer, .page-head-wrapper").hide();
	$("body").attr("data-route", "wall-display").css({ overflow: "hidden", background: "#060612" });
	$(".layout-main-section, .container, .page-body, .page-content, .layout-main, .layout-main-section-wrapper, .main-section").css({ margin: 0, padding: 0, "max-width": "100vw", width: "100vw", overflow: "hidden" });
	$(wrapper).css({ margin: 0, padding: 0 });
	$(wrapper).closest(".page-container").css({ "margin-left": 0, "max-width": "100vw", overflow: "hidden" });

	page.$wall = $('<div class="wall-display"></div>').appendTo(page.body);

	refresh_wall(page);
	page._refresh_interval = setInterval(function () { refresh_wall(page); }, 30000);
};

frappe.pages["wall-display"].on_page_hide = function () {
	$(".navbar").show();
	$("body").css("overflow", "").removeAttr("data-route");
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
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_recent_invoices", { limit: 6 }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_revenue_trend", { days: 7 }),
	]).then(function ([kpis, employees, bundles, po, invoices, trend]) {
		var now = new Date();
		var time_str = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
		var date_str = now.toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

		var html = "";

		// === HEADER ===
		html += '<div class="wall-header">'
			+ '<div class="wall-title">⭐ <span>KHANDELWAL GENERAL STORES</span> — LIVE</div>'
			+ '<div class="wall-live"><div class="live-dot"></div> LIVE</div>'
			+ '<div class="wall-datetime">' + date_str + " │ " + time_str + "</div></div>";

		// === KPI ROW ===
		var goal = 1000000; // 10 lakh
		var pct = Math.min(100, Math.round((kpis.revenue / goal) * 100));
		var remaining = Math.max(0, goal - kpis.revenue);

		html += '<div class="wall-kpis">'
			+ wall_kpi("💰", "TODAY'S REVENUE", wfmt(kpis.revenue), (kpis.revenue_change >= 0 ? "▲ " : "▼ ") + Math.abs(kpis.revenue_change) + "% vs yesterday")
			+ wall_kpi("📦", "TODAY'S ORDERS", kpis.order_count, "📚 " + kpis.bundles_sold + " Bundles │ 🛒 " + kpis.loose_items + " Loose")
			+ '<div class="wall-kpi"><div class="wk-label">🎯 DAILY GOAL — ' + wfmt(goal) + '</div>'
			+ '<div class="wall-goal-bg"><div class="wall-goal-fill" style="width:' + pct + '%;">' + pct + "%</div></div>"
			+ '<div class="wall-goal-text"><span>' + wfmt(kpis.revenue) + '</span><span>' + wfmt(remaining) + " to go</span></div></div>"
			+ "</div>";

		// === EMPLOYEE COUNTERS ===
		html += '<div class="wall-counters">';
		(employees || []).slice(0, 4).forEach(function (e) {
			// Fix user names — use full_name, fallback to email prefix
			var name = e.full_name || e.user.split("@")[0];
			var emp_goal = 200000; // per employee goal
			var emp_pct = Math.min(100, Math.round((e.revenue / emp_goal) * 100));
			var color = emp_pct >= 70 ? "#22c55e" : emp_pct >= 40 ? "#f59e0b" : "#ef4444";
			html += '<div class="wall-counter">'
				+ '<div class="wc-name">👤 ' + name + "</div>"
				+ '<div class="wc-profile">' + (e.pos_profile || "") + " │ " + e.orders + " orders</div>"
				+ '<div class="wc-stats"><span class="wc-revenue">' + wfmt(e.revenue) + "</span>"
				+ '<span class="wc-orders">' + emp_pct + "%</span></div>"
				+ '<div class="wc-bar-bg"><div class="wc-bar-fill" style="width:' + emp_pct + "%;background:" + color + ';"></div></div></div>';
		});
		html += "</div>";

		// === TWO PANELS: PO + Bundle Stock ===
		html += '<div class="wall-panels">';

		// PO Alerts
		html += '<div class="wall-panel"><h3>⚠️ URGENT — ACTION NEEDED</h3>';
		if (po.stuck && po.stuck.length) {
			html += '<div class="wp-title text-red">STUCK PURCHASE ORDERS</div>';
			po.stuck.slice(0, 4).forEach(function (p) {
				html += '<div class="wall-alert red"><div class="wa-title">' + p.name + " — " + p.supplier + "</div>"
					+ '<div class="wa-detail">' + p.age + " days │ " + p.followups + " follow-ups</div></div>";
			});
		}
		if (po.need_followup && po.need_followup.length) {
			html += '<div class="wp-title text-orange">NEED FOLLOW-UP</div>';
			po.need_followup.slice(0, 3).forEach(function (p) {
				html += '<div class="wall-alert yellow"><div class="wa-title">' + p.name + " — " + p.supplier + "</div>"
					+ '<div class="wa-detail">Due: ' + p.next_date + "</div></div>";
			});
		}
		if (po.on_the_way && po.on_the_way.length) {
			html += '<div class="wp-title text-green">🚚 ON THE WAY (' + po.on_the_way.length + ")</div>";
			po.on_the_way.slice(0, 2).forEach(function (p) {
				html += '<div class="wall-alert green"><div class="wa-title">' + p.name + " — " + p.supplier + "</div></div>";
			});
		}
		if (!po.stuck.length && !po.need_followup.length && !po.on_the_way.length) {
			html += '<div class="wall-alert green"><div class="wa-title">✅ All Purchase Orders on track</div></div>';
		}
		html += "</div>";

		// Bundle Stock Alerts
		var out_b = (bundles || []).filter(function (b) { return b.status === "out"; });
		var low_b = (bundles || []).filter(function (b) { return b.status === "low"; });
		var ok_b = (bundles || []).filter(function (b) { return b.status === "ok"; });

		html += '<div class="wall-panel"><h3>📚 BUNDLE STOCK ALERTS</h3>';
		if (out_b.length) {
			html += '<div class="wp-title text-red">🔴 OUT OF STOCK (' + out_b.length + ")</div>";
			out_b.slice(0, 3).forEach(function (b) {
				html += '<div class="wall-alert red"><div class="wa-title">' + (b.description || b.bundle) + " — 0 sets</div>"
					+ '<div class="wa-detail">Blocking: ' + (b.blocking_item || "—") + "</div></div>";
			});
		}
		if (low_b.length) {
			html += '<div class="wp-title text-orange">🟡 LOW STOCK (' + low_b.length + ")</div>";
			low_b.slice(0, 3).forEach(function (b) {
				html += '<div class="wall-alert yellow"><div class="wa-title">' + (b.description || b.bundle) + " — " + b.sellable_sets + " sets</div>"
					+ '<div class="wa-detail">Goal: ' + (b.goal || "—") + " │ Sold: " + b.sold + "</div></div>";
			});
		}
		html += '<div class="wp-title text-green">🟢 GOOD STOCK: ' + ok_b.length + " bundles</div>";
		html += "</div>";
		html += "</div>";

		// === BOTTOM ROW: Chart + Bundle Summary + Ratio ===
		html += '<div class="wall-bottom-row">';

		// Revenue chart
		html += '<div class="wall-chart"><h3>📊 Revenue — Last 7 Days</h3><div class="wall-bars">';
		var max_rev = 0;
		(trend || []).forEach(function (d) { if (d.revenue > max_rev) max_rev = d.revenue; });
		if (max_rev === 0) max_rev = 1;

		(trend || []).forEach(function (d) {
			var h = Math.max(4, Math.round((d.revenue / max_rev) * 120));
			var isToday = d.date === today;
			var dt = new Date(d.date);
			var label = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getDay()];
			var color = isToday ? "linear-gradient(to top, #22c55e, #5e64ff)" : "linear-gradient(to top, #5e64ff, #8b5cf6)";
			html += '<div class="wb-col"><div class="wb-val">' + Math.round(d.revenue / 1000) + "K</div>"
				+ '<div class="wb-bar" style="height:' + h + "px;background:" + color + ';"></div>'
				+ '<div class="wb-label' + (isToday ? " wb-today" : "") + '">' + label + "</div></div>";
		});
		html += "</div></div>";

		// Bundle Sales Summary
		var total_bundles = (bundles || []).length;
		var total_sold = 0;
		var top_bundle = { description: "—", sold: 0 };
		(bundles || []).forEach(function (b) {
			total_sold += b.sold;
			if (b.sold > top_bundle.sold) top_bundle = b;
		});

		html += '<div class="wall-bundle-summary"><h3>📚 Product Bundle Summary</h3>'
			+ '<div class="wbs-grid">'
			+ '<div class="wbs-item"><div class="wbs-val">' + total_bundles + '</div><div class="wbs-label">Total Bundles</div></div>'
			+ '<div class="wbs-item"><div class="wbs-val">' + kpis.bundles_sold + '</div><div class="wbs-label">Sold Today</div></div>'
			+ '<div class="wbs-item"><div class="wbs-val text-red">' + out_b.length + '</div><div class="wbs-label">Out of Stock</div></div>'
			+ '<div class="wbs-item"><div class="wbs-val text-orange">' + low_b.length + '</div><div class="wbs-label">Low Stock</div></div>'
			+ "</div>"
			+ '<div class="wbs-top">🏆 Most Sold: <strong>' + (top_bundle.description || top_bundle.bundle || "—") + "</strong> (" + top_bundle.sold + " sets)</div>"
			+ "</div>";

		// Ratio
		var bundle_pct = kpis.revenue > 0 ? Math.round((kpis.bundle_revenue / kpis.revenue) * 100) : 0;
		var loose_pct = 100 - bundle_pct;
		html += '<div class="wall-ratio"><h3>📈 Bundle vs Loose</h3>'
			+ '<div class="wall-ratio-bar"><div class="wrb-bundle" style="width:' + bundle_pct + '%;">' + bundle_pct + "%</div>"
			+ '<div class="wrb-loose" style="width:' + loose_pct + '%;">' + loose_pct + "%</div></div>"
			+ '<div class="wall-ratio-labels"><span>📚 ' + wfmt(kpis.bundle_revenue) + "</span><span>🛒 " + wfmt(kpis.loose_revenue) + "</span></div>"
			+ '<div class="wall-week-total">' + wfmt(kpis.revenue) + "</div>"
			+ '<div class="wall-week-label">Today\'s Total</div></div>';

		html += "</div>";

		// === FOOTER TICKER ===
		html += '<div class="wall-footer"><div class="wall-ticker">';
		(invoices || []).forEach(function (inv) {
			var name = inv.user_name || inv.owner.split("@")[0];
			html += '<span class="wt-item"><span class="wt-time">' + (inv.time || "") + "</span> "
				+ inv.name + " " + inv.customer_name + " " + wfmt(inv.grand_total) + " — " + name + "</span>";
		});
		html += '</div><div class="wall-refresh">🔄 Auto-refreshes every 30s</div></div>';

		$w.html(html);
	});
}

function wfmt(n) { return "₹" + (Math.round(n) || 0).toLocaleString("en-IN"); }

function wall_kpi(icon, label, value, sub) {
	return '<div class="wall-kpi"><div class="wk-label">' + icon + " " + label + "</div>"
		+ '<div class="wk-value">' + value + "</div>"
		+ '<div class="wk-sub">' + (sub || "") + "</div></div>";
}
