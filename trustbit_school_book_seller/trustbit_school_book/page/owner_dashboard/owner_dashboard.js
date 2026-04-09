frappe.pages["owner-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Owner Dashboard",
		single_column: true,
	});

	// Date range controls
	page.from_date = frappe.ui.form.make_control({
		parent: page.wrapper.find(".page-actions"),
		df: { fieldtype: "Date", fieldname: "from_date", default: frappe.datetime.get_today() },
		render_input: true,
	});
	page.to_date = frappe.ui.form.make_control({
		parent: page.wrapper.find(".page-actions"),
		df: { fieldtype: "Date", fieldname: "to_date", default: frappe.datetime.get_today() },
		render_input: true,
	});

	page.add_button(__("Refresh"), () => render_dashboard(page), "refresh");

	page.$dashboard = $('<div class="owner-dashboard-container"></div>').appendTo(page.body);

	// Load CSS
	$("head").append(`<link rel="stylesheet" href="/assets/trustbit_school_book_seller/css/owner_dashboard.css">`);

	render_dashboard(page);
};

function render_dashboard(page) {
	var $d = page.$dashboard;
	var from_date = page.from_date?.get_value() || frappe.datetime.get_today();
	var to_date = page.to_date?.get_value() || frappe.datetime.get_today();

	$d.html('<div class="text-center" style="padding:60px;"><i class="fa fa-spinner fa-spin fa-3x"></i><br><br>Loading dashboard...</div>');

	// Fetch all data in parallel
	Promise.all([
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_dashboard_kpis", { from_date, to_date }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_bundle_stock_report"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_short_items"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_po_status"),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_employee_performance", { date: from_date }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_loose_sales", { date: from_date }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_revenue_trend", { days: 7 }),
		frappe.xcall("trustbit_school_book_seller.dashboard_api.get_payment_breakdown", { date: from_date }),
	]).then(function ([kpis, bundles, short_items, po_status, employees, loose, trend, payments]) {
		var html = "";

		// KPI Cards
		html += render_kpi_cards(kpis);

		// Goal Progress
		html += render_goal_progress(kpis);

		// Bundle Stock Table
		html += render_bundle_stock(bundles);

		// Two Column: Short Items + Revenue Chart
		html += '<div class="two-col">';
		html += render_short_items(short_items);
		html += render_revenue_chart(trend, kpis);
		html += '</div>';

		// Two Column: PO Status + Employee Performance
		html += '<div class="two-col">';
		html += render_po_status(po_status);
		html += render_employee_performance(employees, payments);
		html += '</div>';

		// Loose Sales
		html += render_loose_sales(loose);

		$d.html(html);

		// Render the chart
		render_trend_chart(trend);
	}).catch(function (err) {
		$d.html('<div class="text-danger text-center" style="padding:40px;">Error loading dashboard: ' + (err.message || err) + '</div>');
		console.error(err);
	});
}

function fmt(n) { return (n || 0).toLocaleString("en-IN"); }
function fmtc(n) { return "₹" + fmt(Math.round(n || 0)); }

function render_kpi_cards(kpis) {
	var cards = [
		{ icon: "💰", label: "Revenue", value: fmtc(kpis.revenue), trend: kpis.revenue_change, unit: "vs yesterday" },
		{ icon: "📦", label: "Orders", value: kpis.order_count, trend: kpis.order_change, unit: "vs yesterday" },
		{ icon: "📚", label: "Bundles Sold", value: kpis.bundles_sold, trend: null },
		{ icon: "🛒", label: "Loose Items", value: kpis.loose_items, trend: null },
	];

	var html = '<div class="kpi-row">';
	cards.forEach(function (c) {
		var trend_html = "";
		if (c.trend !== null && c.trend !== undefined) {
			var cls = c.trend >= 0 ? "trend-up" : "trend-down";
			var arrow = c.trend >= 0 ? "▲" : "▼";
			trend_html = '<div class="kpi-trend ' + cls + '">' + arrow + " " + Math.abs(c.trend) + '% ' + (c.unit || "") + '</div>';
		}
		html += '<div class="kpi-card"><div class="kpi-icon">' + c.icon + '</div>'
			+ '<div class="kpi-label">' + c.label + '</div>'
			+ '<div class="kpi-value">' + c.value + '</div>'
			+ trend_html + '</div>';
	});
	html += '</div>';
	return html;
}

function render_goal_progress(kpis) {
	var goal = 100000; // TODO: make configurable
	var pct = Math.min(100, Math.round((kpis.revenue / goal) * 100));
	var remaining = Math.max(0, goal - kpis.revenue);

	return '<div class="section goal-section">'
		+ '<div class="section-title">DAILY REVENUE GOAL</div>'
		+ '<div class="goal-bar-bg"><div class="goal-bar-fill" style="width:' + pct + '%;">' + pct + '%</div></div>'
		+ '<div class="goal-text"><span>' + fmtc(kpis.revenue) + ' earned</span><span>' + fmtc(remaining) + ' remaining</span><span>Goal: ' + fmtc(goal) + '</span></div>'
		+ '</div>';
}

function render_bundle_stock(bundles) {
	var html = '<div class="section"><h2>📚 Product Bundle Stock & Goals</h2><table><thead><tr>'
		+ '<th>Bundle</th><th class="tc">Sellable</th><th class="tc">Goal</th><th class="tc">Sold</th>'
		+ '<th class="tc">Gap</th><th class="tc">N/A</th><th class="tc">Status</th><th>Blocking Item</th></tr></thead><tbody>';

	(bundles || []).forEach(function (b) {
		var status_badge = b.status === "out" ? '<span class="badge-red">Out</span>'
			: b.status === "low" ? '<span class="badge-yellow">Low</span>'
			: '<span class="badge-green">OK</span>';
		var val_cls = b.status === "out" ? "text-red" : b.status === "low" ? "text-orange" : "text-green";
		var row_cls = b.status === "out" ? ' class="row-danger"' : "";
		var gap_cls = b.gap < 0 ? "text-red" : b.gap > 0 ? "text-green" : "";

		html += '<tr' + row_cls + '><td><strong>' + (b.description || b.bundle) + '</strong></td>'
			+ '<td class="tc bold ' + val_cls + '">' + b.sellable_sets + '</td>'
			+ '<td class="tc">' + (b.goal || "—") + '</td>'
			+ '<td class="tc">' + b.sold + '</td>'
			+ '<td class="tc ' + gap_cls + '">' + (b.gap > 0 ? "+" : "") + b.gap + '</td>'
			+ '<td class="tc">' + (b.na_count || 0) + '</td>'
			+ '<td class="tc">' + status_badge + '</td>'
			+ '<td class="small-text">' + (b.blocking_item || "—") + '</td></tr>';
	});

	html += '</tbody></table></div>';
	return html;
}

function render_short_items(items) {
	var html = '<div class="section"><h2>🔴 Short Items (Need Purchase)</h2>'
		+ '<p class="subtitle">Items blocking bundle completion</p>'
		+ '<table><thead><tr><th>Item</th><th class="tr">Stock</th><th class="tr">Need</th><th class="tr">Gap</th></tr></thead><tbody>';

	(items || []).slice(0, 10).forEach(function (i) {
		html += '<tr><td>' + i.item_name + '</td>'
			+ '<td class="tr">' + i.stock + '</td>'
			+ '<td class="tr">' + i.need + '</td>'
			+ '<td class="tr text-red bold">' + i.gap + '</td></tr>';
	});

	html += '</tbody></table>';
	if (items && items.length > 10) html += '<p class="subtitle">' + items.length + ' total short items</p>';
	html += '</div>';
	return html;
}

function render_revenue_chart(trend, kpis) {
	var bundle_pct = kpis.revenue > 0 ? Math.round((kpis.bundle_revenue / kpis.revenue) * 100) : 0;
	var loose_pct = 100 - bundle_pct;

	var html = '<div class="section">'
		+ '<h2>📊 Revenue Trend (7 Days)</h2>'
		+ '<div id="revenue-chart" style="height:160px;margin-bottom:20px;"></div>'
		+ '<h2>📈 Bundle vs Loose Sales</h2>'
		+ '<div class="ratio-bar"><div class="ratio-bundle" style="width:' + bundle_pct + '%;">📚 ' + bundle_pct + '%</div>'
		+ '<div class="ratio-loose" style="width:' + loose_pct + '%;">🛒 ' + loose_pct + '%</div></div>'
		+ '<div class="ratio-labels"><span>Bundle: ' + fmtc(kpis.bundle_revenue) + '</span><span>Loose: ' + fmtc(kpis.loose_revenue) + '</span></div>'
		+ '</div>';
	return html;
}

function render_trend_chart(trend) {
	if (!trend || !trend.length) return;
	var labels = trend.map(d => {
		var dt = new Date(d.date);
		return ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][dt.getDay()];
	});
	var values = trend.map(d => d.revenue);

	if (typeof frappe.Chart !== "undefined") {
		new frappe.Chart("#revenue-chart", {
			data: { labels: labels, datasets: [{ values: values }] },
			type: "bar",
			height: 150,
			colors: ["#5e64ff"],
			barOptions: { spaceRatio: 0.4 },
			tooltipOptions: { formatTooltipY: d => fmtc(d) },
		});
	} else {
		// Fallback: simple bars
		var max = Math.max(...values, 1);
		var barsHtml = '<div style="display:flex;align-items:flex-end;justify-content:space-around;height:140px;">';
		trend.forEach(function (d, i) {
			var h = Math.round((d.revenue / max) * 120);
			var isToday = d.date === frappe.datetime.get_today();
			var color = isToday ? "linear-gradient(to top, #28a745, #5e64ff)" : "linear-gradient(to top, #5e64ff, #8b5cf6)";
			barsHtml += '<div style="text-align:center;"><div style="font-size:10px;color:#5e64ff;margin-bottom:2px;">' + Math.round(d.revenue / 1000) + 'K</div>'
				+ '<div style="width:30px;height:' + h + 'px;background:' + color + ';border-radius:4px 4px 0 0;margin:0 auto;"></div>'
				+ '<div style="font-size:10px;color:#888;margin-top:4px;">' + labels[i] + '</div></div>';
		});
		barsHtml += '</div>';
		$("#revenue-chart").html(barsHtml);
	}
}

function render_po_status(po) {
	var s = po.summary || {};
	var html = '<div class="section"><h2>📋 Purchase Orders</h2>';

	// Stuck
	if (po.stuck && po.stuck.length) {
		html += '<div class="po-section-title text-red">🔴 STUCK (Need Immediate Action)</div>';
		po.stuck.forEach(function (p) {
			html += '<div class="po-card urgent"><div class="po-title">' + p.name + ' — ' + p.supplier + '</div>'
				+ '<div class="po-detail">' + p.age + ' days old • ' + p.followups + ' follow-ups</div></div>';
		});
	}

	// Need followup
	if (po.need_followup && po.need_followup.length) {
		html += '<div class="po-section-title text-orange">🟡 NEED FOLLOW-UP</div>';
		po.need_followup.forEach(function (p) {
			html += '<div class="po-card warning"><div class="po-title">' + p.name + ' — ' + p.supplier + '</div>'
				+ '<div class="po-detail">Due: ' + p.next_date + ' • ' + p.followups + ' follow-ups</div></div>';
		});
	}

	// On the way
	if (po.on_the_way && po.on_the_way.length) {
		html += '<div class="po-section-title text-blue">🚚 ON THE WAY</div>';
		po.on_the_way.forEach(function (p) {
			html += '<div class="po-card on-way"><div class="po-title">' + p.name + ' — ' + p.supplier + '</div>'
				+ '<div class="po-detail">Status: ' + p.status + '</div></div>';
		});
	}

	// Summary
	html += '<div class="po-summary">Total: ' + s.total + ' | Pending: ' + s.pending
		+ ' | <span class="text-red">Stuck: ' + s.stuck + '</span>'
		+ ' | On Way: ' + s.on_the_way + '</div>';

	html += '</div>';
	return html;
}

function render_employee_performance(employees, payments) {
	var html = '<div class="section"><h2>👥 Employee Performance</h2>'
		+ '<table><thead><tr><th>Employee</th><th>Profile</th><th class="tc">Orders</th><th class="tr">Revenue</th></tr></thead><tbody>';

	(employees || []).forEach(function (e) {
		html += '<tr><td><strong>' + e.full_name + '</strong></td>'
			+ '<td class="small-text">' + (e.pos_profile || "—") + '</td>'
			+ '<td class="tc">' + e.orders + '</td>'
			+ '<td class="tr bold">' + fmtc(e.revenue) + '</td></tr>';
	});

	html += '</tbody></table>';

	// Payment breakdown
	html += '<h3 style="margin-top:16px;">💰 Payment Breakdown</h3><div class="payment-grid">';
	var colors = { "Cash": "#28a745", "UPI": "#1976d2", "Card": "#f57c00", "Credit Sale": "#7b1fa2" };
	(payments || []).forEach(function (p) {
		var color = colors[p.mode_of_payment] || "#666";
		html += '<div class="payment-card" style="border-left:3px solid ' + color + ';">'
			+ '<div class="payment-label">' + p.mode_of_payment + '</div>'
			+ '<div class="payment-value" style="color:' + color + ';">' + fmtc(p.amount) + '</div></div>';
	});
	html += '</div></div>';
	return html;
}

function render_loose_sales(loose) {
	var html = '<div class="section"><h2>🛒 Loose Sales (Non-Bundle Items)</h2>'
		+ '<div class="two-col-inner">';

	html += '<div><table><thead><tr><th>Item</th><th class="tc">Qty</th><th class="tr">Amount</th></tr></thead><tbody>';
	(loose.items || []).slice(0, 8).forEach(function (i) {
		html += '<tr><td>' + i.item_name + '</td><td class="tc">' + i.qty + '</td><td class="tr">' + fmtc(i.amount) + '</td></tr>';
	});
	html += '</tbody></table></div>';

	html += '<div class="loose-summary">'
		+ '<div class="loose-value">' + fmtc(loose.total_amount) + '</div>'
		+ '<div class="loose-label">Loose Sales Revenue</div>'
		+ '<div class="loose-sub">' + loose.total_orders + ' items sold</div></div>';

	html += '</div></div>';
	return html;
}
