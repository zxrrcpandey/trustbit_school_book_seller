// School Book Dashboard: the book season for one school (a Customer Group) or all schools.
// Data comes from trustbit_school_book_seller.school_book_dashboard.get_dashboard_data
// (cached 10 minutes on the server); every book row and alert opens the School Book Sales
// Report for that book with the same filters.

// bump ?v= whenever the CSS changes: browsers keep /assets files cached
const SBD_CSS = "/assets/trustbit_school_book_seller/css/school_book_dashboard.css?v=20260929-2";
const SBD_METHOD = "trustbit_school_book_seller.school_book_dashboard.get_dashboard_data";
const SBD_REPORT = "School Book Sales Report";
const SBD_FIRST_BOOKS = 15;

frappe.pages["school-book-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("School Book Dashboard"),
		single_column: true,
	});
	wrapper.school_book_dashboard = new SchoolBookDashboard(page);
};

const sbd_esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
const sbd_num = (value) => format_number(Math.round(flt(value)), null, 0);
const sbd_pct = (ratio) => (ratio == null ? "—" : (flt(ratio) * 100).toFixed(1) + "%");

function sbd_inr(value) {
	// compact rupees for tiles: ₹32.13 L, ₹3.21 Cr
	const n = flt(value);
	const abs = Math.abs(n);
	if (abs >= 1e7) return "₹" + (n / 1e7).toFixed(2) + " Cr";
	if (abs >= 1e5) return "₹" + (n / 1e5).toFixed(2) + " L";
	return "₹" + sbd_num(n);
}

class SchoolBookDashboard {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.tips = [];
		this.sort = { key: "nett", dir: -1 };
		this.query = "";
		this.show_all_books = false;
		this.show_trend_table = false;

		if (!document.querySelector(`link[href="${SBD_CSS}"]`)) {
			$("head").append(`<link rel="stylesheet" href="${SBD_CSS}">`);
		}
		this.$root = $('<div class="sbd"><div class="sbd-content"></div></div>').appendTo(page.main);
		this.$content = this.$root.find(".sbd-content");
		this.$tip = $('<div class="sbd-tip" role="tooltip"></div>').appendTo(document.body);
		frappe.router.on("change", () => this.$tip.hide());

		this.make_filters();
		page.set_primary_action(__("Refresh"), () => this.refresh(true), "refresh");
		page.set_secondary_action(__("Detailed report"), () => this.open_report());
		this.bind_events();
		this.schedule_refresh();
	}

	make_filters() {
		const today = frappe.datetime.get_today();
		const add = (df) => this.page.add_field({ ...df, change: () => this.schedule_refresh() });
		this.filters = {
			company: add({
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_user_default("Company"),
			}),
			// season purchases are dated Jan-Mar, before sales start in April
			from_date: add({
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				default: today.slice(0, 4) + "-01-01",
			}),
			to_date: add({ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: today }),
			school: add({
				fieldname: "school",
				label: __("School (Customer Group)"),
				fieldtype: "Link",
				options: "Customer Group",
			}),
			item_group: add({
				fieldname: "item_group",
				label: __("Item Group"),
				fieldtype: "Link",
				options: "Item Group",
				default: "Books",
			}),
			product_bundle: add({
				fieldname: "product_bundle",
				label: __("Product Bundle"),
				fieldtype: "Link",
				options: "Product Bundle",
			}),
		};
	}

	args() {
		const args = {};
		for (const [key, control] of Object.entries(this.filters)) {
			args[key] = control.get_value() || "";
		}
		return args;
	}

	schedule_refresh() {
		clearTimeout(this.refresh_timer);
		this.refresh_timer = setTimeout(() => this.refresh(), 250);
	}

	refresh(force) {
		const args = this.args();
		if (!args.company) return;
		const token = (this.token = (this.token || 0) + 1);
		// keep the previous render on screen, dimmed, while the new one loads
		this.$root.addClass("sbd-loading");
		if (!this.data) {
			this.$content.html(`<div class="sbd-state">${__("Loading the book season…")}</div>`);
		}
		frappe
			.xcall(SBD_METHOD, { ...args, refresh: force ? 1 : 0 })
			.then((data) => {
				if (token !== this.token) return;
				this.data = data;
				this.render();
			})
			.catch(() => {
				if (token === this.token && !this.data) {
					this.$content.html(
						`<div class="sbd-state"><b>${__("Could not load the dashboard")}</b>${__(
							"Check the filters and press Refresh."
						)}</div>`
					);
				}
			})
			.finally(() => {
				if (token === this.token) this.$root.removeClass("sbd-loading");
			});
	}

	render() {
		const d = this.data;
		this.tips = [];
		this.$tip.hide();
		if (!d.totals.titles) {
			this.$content.html(
				`<div class="sbd-card sbd-state"><b>${__("No sales in this selection")}</b>${__(
					"Try a wider date range, another school, or clear the Item Group."
				)}</div>`
			);
			return;
		}
		this.$content.html(`
			<div class="sbd-top">
				${this.hero_html(d)}
				<div class="sbd-tiles">${this.tiles_html(d)}</div>
			</div>
			<div class="sbd-grid-2">
				<section class="sbd-card">${this.breakdown_html(d)}</section>
				<div class="sbd-stack">
					<section class="sbd-card">${this.mix_html(d)}</section>
					<section class="sbd-card">${this.subjects_html(d)}</section>
				</div>
			</div>
			<section class="sbd-card sbd-trend">${this.trend_html(d)}</section>
			<section class="sbd-card sbd-books">${this.books_html(d)}</section>
			<div class="sbd-alerts">${this.alerts_html(d)}</div>
			<div class="sbd-foot">${__("Updated at {0}. Figures are kept for 10 minutes; Refresh recalculates.", [
				moment(d.generated_at).format("HH:mm"),
			])}</div>`);
		this.draw_trend(d);
	}

	// ---------- sections ----------

	hero_html(d) {
		const t = d.totals;
		const f = d.filters;
		const scope = [d.school_label, f.item_group || __("All items"), f.product_bundle]
			.filter(Boolean)
			.map(sbd_esc)
			.join(" · ");
		const range = `${moment(f.from_date).format("D MMM YYYY")} – ${moment(f.to_date).format("D MMM YYYY")}`;
		return `<section class="sbd-card sbd-hero">
			<div>
				<div class="sbd-eyebrow">${scope}</div>
				<div class="sbd-hero-label">${__("Books sold, nett of returns")}</div>
				<div class="sbd-hero-value">${sbd_num(t.nett)}</div>
				<div class="sbd-hero-sub">${__("{0} sold · {1} returned · {2} titles", [
					sbd_num(t.sold),
					sbd_num(t.returned),
					sbd_num(t.titles),
				])}</div>
			</div>
			<div class="sbd-hero-range">${frappe.utils.icon("calendar", "sm")} ${sbd_esc(range)}</div>
		</section>`;
	}

	tiles_html(d) {
		const t = d.totals;
		const school = !!d.filters.school;
		const past = d.filters.to_date < frappe.datetime.get_today();
		const tile = (icon, label, value, note, extra = "", title = "") => `
			<section class="sbd-card sbd-tile"${title ? ` title="${sbd_esc(title)}"` : ""}>
				<div class="sbd-tile-label"><span class="sbd-tile-icon">${icon}</span>${label}</div>
				<div class="sbd-tile-value">${value}</div>
				${extra}
				<div class="sbd-tile-note">${note}</div>
			</section>`;
		const sell_through = t.sell_through == null ? null : Math.min(1, Math.max(0, t.sell_through));
		const stock_note = t.negative_titles
			? `<span class="sbd-status critical"><i>✕</i>${__("{0} titles below zero", [
					sbd_num(t.negative_titles),
			  ])}</span>`
			: past
			? __("on {0}", [moment(d.filters.to_date).format("D MMM YYYY")])
			: __("in the company's warehouses now");
		return [
			tile(
				"₹",
				__("Net sales"),
				sbd_inr(t.value),
				__("after discount, before GST"),
				"",
				format_currency(t.value, "INR", 0)
			),
			tile(
				"#",
				__("Counter bills"),
				sbd_num(t.counter_bills),
				school ? __("students billed at the counter") : __("POS bills, mostly one per student")
			),
			tile(
				"↩",
				__("Returned"),
				sbd_num(t.returned),
				t.return_rate == null ? "" : __("{0} of books sold", [sbd_pct(t.return_rate)])
			),
			tile(
				"↓",
				__("Bought"),
				sbd_num(t.purchased),
				school ? __("these titles, after debit notes") : __("after debit notes to publishers")
			),
			tile(
				"%",
				__("Sell-through"),
				sbd_pct(t.sell_through),
				school ? __("sold to all buyers ÷ bought") : __("sold ÷ bought"),
				sell_through == null
					? ""
					: `<div class="sbd-meter"><span style="width:${(sell_through * 100).toFixed(1)}%"></span></div>`
			),
			tile("▦", __("Stock left"), sbd_num(t.stock), stock_note),
		].join("");
	}

	breakdown_html(d) {
		const school = !!d.filters.school;
		const rows = d.breakdown;
		const max = Math.max(1, ...rows.map((r) => r.nett));
		const head = school
			? [
					__("Class-wise sales · {0}", [sbd_esc(d.school_label)]),
					__("Nett books per customer: class accounts first, then shops and bulk buyers"),
			  ]
			: [__("Sales by customer group"), __("Nett books per customer group. Click a school to see its classes.")];
		let html = `<div class="sbd-card-head"><div><h3 class="sbd-title">${head[0]}</h3>
			<div class="sbd-sub">${head[1]}</div></div></div><div class="sbd-bars">`;
		let shops_started = false;
		for (const r of rows) {
			if (school && r.kind === "bulk" && !shops_started) {
				shops_started = true;
				html += `<div class="sbd-divider">${__("Shops and bulk buyers")}</div>`;
			}
			const sub =
				r.kind !== "class"
					? ""
					: r.counter_bills === 1
					? __("1 student")
					: __("{0} students", [sbd_num(r.counter_bills)]);
			const tip = this.tip(r.label, r.nett, __("books nett"), [
				[__("Sold"), sbd_num(r.sold)],
				[__("Returned"), sbd_num(r.returned)],
				[__("Net sales"), sbd_inr(r.value)],
				[__("Counter bills"), sbd_num(r.counter_bills)],
			]);
			html += this.bar_row(r.label, sub, r.nett, max, tip, r.drill ? r.label : null, r.muted);
		}
		return html + "</div>";
	}

	bar_row(label, sub, value, max, tip, drill, muted) {
		// "Other" / "No group" / "No subject" rows get the grey de-emphasis bar
		const share = Math.max(0, flt(value) / max);
		const bar =
			share > 0
				? `<div class="sbd-bar${muted ? " muted" : ""}" style="width:calc((100% - 72px) * ${share.toFixed(4)})"></div>`
				: "";
		return `<div class="sbd-bar-row${drill ? " sbd-drill" : ""}" tabindex="0" data-tip="${tip}"${
			drill ? ` data-drill="${sbd_esc(drill)}"` : ""
		}>
			<div class="sbd-bar-label" title="${sbd_esc(label)}">${sbd_esc(label)}${sub ? `<small>${sub}</small>` : ""}</div>
			<div class="sbd-bar-track">${bar}<span class="sbd-bar-value">${sbd_num(value)}</span></div>
		</div>`;
	}

	mix_html(d) {
		const parts = d.mix;
		const total = parts.reduce((sum, p) => sum + flt(p.qty), 0) || 1;
		const colors = ["var(--sbd-series-1)", "var(--sbd-series-2)", "var(--sbd-series-3)"];
		const segments = parts
			.map((p, i) =>
				p.qty > 0
					? `<div class="sbd-seg" tabindex="0" style="flex:${flt(p.qty)} 1 0;background:${colors[i]}" data-tip="${this.tip(
							p.label,
							p.qty,
							__("books nett"),
							[[__("Share"), sbd_pct(p.qty / total)]]
					  )}"></div>`
					: ""
			)
			.join("");
		const legend = parts
			.map(
				(p, i) => `<div class="sbd-legend-row">
					<span class="sbd-swatch" style="background:${colors[i]}"></span>
					<span>${sbd_esc(p.label)}</span>
					<span class="num">${sbd_num(p.qty)}</span>
					<span class="pct">${sbd_pct(p.qty / total)}</span>
				</div>`
			)
			.join("");
		return `<div class="sbd-card-head"><div><h3 class="sbd-title">${__("Who bought these books")}</h3>
			<div class="sbd-sub">${
				d.filters.school
					? __("Nett books of these titles, including other schools, shops and walk-ins buying the same titles")
					: __("Nett books by kind of customer account")
			}</div></div></div>
			<div class="sbd-stackbar">${segments}</div>
			<div class="sbd-legend">${legend}</div>`;
	}

	subjects_html(d) {
		const rows = d.subjects;
		const max = Math.max(1, ...rows.map((r) => r.nett));
		return `<div class="sbd-card-head"><div><h3 class="sbd-title">${__("Sales by subject")}</h3>
			<div class="sbd-sub">${__("Nett books, from the Subject on each book")}</div></div></div>
			<div class="sbd-bars">${rows
				.map((r) =>
					this.bar_row(r.label, "", r.nett, max, this.tip(r.label, r.nett, __("books nett"), []), null, r.muted)
				)
				.join("")}</div>`;
	}

	trend_html(d) {
		const weekly = d.trend.granularity === "week";
		let body = '<div class="sbd-chart" id="sbd-trend"></div>';
		if (this.show_trend_table) {
			const rows = d.trend.labels
				.map((label, i) =>
					d.trend.sold[i] || d.trend.returned[i]
						? `<tr class="static"><td>${sbd_esc(moment(label).format("D MMM YYYY"))}</td>
							<td class="num">${sbd_num(d.trend.sold[i])}</td><td class="num">${sbd_num(d.trend.returned[i])}</td></tr>`
						: ""
				)
				.join("");
			body = `<div class="sbd-table-wrap"><table class="sbd-table"><thead><tr>
				<th>${weekly ? __("Week of") : __("Day")}</th><th class="num">${__("Sold")}</th><th class="num">${__(
				"Returned"
			)}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
		}
		return `<div class="sbd-card-head"><div><h3 class="sbd-title">${__("Season trend")}</h3>
			<div class="sbd-sub">${weekly ? __("Books sold and returned per week") : __("Books sold and returned per day")}</div></div>
			<button class="sbd-link" data-action="trend-table">${
				this.show_trend_table ? __("Show chart") : __("Show as table")
			}</button></div>${body}`;
	}

	draw_trend(d) {
		const el = this.$content.find("#sbd-trend")[0];
		if (!el || this.show_trend_table || typeof frappe.Chart === "undefined") return;
		const css = getComputedStyle(this.$root[0]);
		const color = (name) => css.getPropertyValue(name).trim();
		this.chart = new frappe.Chart(el, {
			type: "line",
			height: 260,
			data: {
				labels: d.trend.labels.map((label) => moment(label).format("D MMM")),
				datasets: [
					{ name: __("Sold"), values: d.trend.sold },
					{ name: __("Returned"), values: d.trend.returned },
				],
			},
			colors: [color("--sbd-series-1"), color("--sbd-series-2")],
			lineOptions: { regionFill: 1, hideDots: 1 },
			axisOptions: { xIsSeries: 1, xAxisMode: "tick", yAxisMode: "span", shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (value) => sbd_num(value) },
		});
	}

	books_html(d) {
		const school = !!d.filters.school;
		const columns = [
			["item_name", __("Book"), ""],
			["sold", __("Sold"), "num"],
			["returned", __("Returned"), "num"],
			["nett", __("Nett"), "num"],
			...(school ? [["nett_all", __("All buyers"), "num"]] : []),
			["purchased", __("Bought"), "num"],
			["stock", __("Stock"), "num"],
			["sell_through", __("Sell-through"), ""],
			["status", __("Status"), ""],
		];

		let rows = d.books.slice();
		const query = this.query.trim().toLowerCase();
		if (query) {
			rows = rows.filter((b) =>
				[b.item_name, b.item_code, b.subject, b.book_class].join(" ").toLowerCase().includes(query)
			);
		}
		const { key, dir } = this.sort;
		rows.sort((a, b) => {
			const x = a[key];
			const y = b[key];
			if (typeof x === "string" || typeof y === "string") return dir * String(x || "").localeCompare(String(y || ""));
			return dir * ((x == null ? -Infinity : x) - (y == null ? -Infinity : y));
		});
		const shown = this.show_all_books || query ? rows : rows.slice(0, SBD_FIRST_BOOKS);

		const head = columns
			.map(([k, label, cls]) => {
				const arrow = k === key ? `<span class="dir">${dir > 0 ? "▲" : "▼"}</span>` : "";
				return `<th class="sortable ${cls}" data-key="${k}">${label}${arrow}</th>`;
			})
			.join("");
		const body = shown
			.map((b) => {
				// "." and "-" are placeholders in the Class and Subject fields of many books
				const real = (value) => (value && String(value).replace(/[\s.\-_/]/g, "") ? String(value).trim() : "");
				const book_class = real(b.book_class);
				const meta = [
					book_class ? (/^\d+$/.test(book_class) ? __("Class {0}", [book_class]) : book_class) : "",
					real(b.subject),
				]
					.filter(Boolean)
					.map(sbd_esc)
					.join(" · ");
				const st = b.sell_through == null ? null : Math.min(1, Math.max(0, b.sell_through));
				return `<tr data-item="${sbd_esc(b.item_code)}" title="${__("Open in the School Book Sales Report")}">
					<td class="book" title="${sbd_esc(b.item_name)}">${sbd_esc(b.item_name)}${meta ? `<small>${meta}</small>` : ""}</td>
					<td class="num">${sbd_num(b.sold)}</td>
					<td class="num">${sbd_num(b.returned)}</td>
					<td class="num"><b>${sbd_num(b.nett)}</b></td>
					${school ? `<td class="num">${sbd_num(b.nett_all)}</td>` : ""}
					<td class="num">${sbd_num(b.purchased)}</td>
					<td class="num">${sbd_num(b.stock)}</td>
					<td>${
						st == null
							? '<span class="sbd-sub">—</span>'
							: `<div class="sbd-st"><div class="sbd-meter"><span style="width:${(st * 100).toFixed(1)}%"></span></div><span class="v">${sbd_pct(
									b.sell_through
							  )}</span></div>`
					}</td>
					<td>${this.status_html(b.status)}</td>
				</tr>`;
			})
			.join("");

		const more =
			!query && rows.length > SBD_FIRST_BOOKS
				? `<div class="sbd-more"><button class="btn btn-default btn-sm" data-action="more">${
						this.show_all_books ? __("Show fewer") : __("Show all {0}", [rows.length])
				  }</button></div>`
				: "";
		const note =
			d.totals.titles > d.books.length
				? __("Top {0} of {1} titles by nett sold. Click a book to open it in the report.", [
						d.books.length,
						sbd_num(d.totals.titles),
				  ])
				: __("Click a book to open it in the report.");
		return `<div class="sbd-card-head"><div><h3 class="sbd-title">${__("Books")}</h3>
			<div class="sbd-sub">${note}</div></div>
			<input class="sbd-search" type="search" placeholder="${__("Search books")}" value="${sbd_esc(this.query)}"></div>
			<div class="sbd-table-wrap"><table class="sbd-table"><thead><tr>${head}</tr></thead><tbody>${
				body || `<tr class="static"><td colspan="${columns.length}" class="sbd-sub">${__("No book matches.")}</td></tr>`
			}</tbody></table></div>${more}`;
	}

	status_html(status) {
		const statuses = {
			ok: ["good", "✓", __("OK"), __("Stock in line with sales")],
			excess: [
				"warning",
				"▲",
				__("Excess"),
				__("At least 10 books and 20% of what was bought are still in stock: return to the publisher?"),
			],
			not_bought: ["serious", "!", __("Not bought"), __("Sold, but no purchase invoice in this period")],
			negative: [
				"critical",
				"✕",
				__("Below zero"),
				__("More went out than came in: usually a missing purchase entry or a bill on the wrong item"),
			],
		};
		const [cls, icon, label, title] = statuses[status] || statuses.ok;
		return `<span class="sbd-status ${cls}" title="${sbd_esc(title)}"><i>${icon}</i>${label}</span>`;
	}

	alerts_html(d) {
		const a = d.alerts;
		const card = (cls, icon, title, count, hint, items, qty) => `<section class="sbd-card">
			<div class="sbd-alert-head"><span class="sbd-status ${cls}"><i>${icon}</i></span><h3 class="sbd-title">${title}</h3></div>
			<div class="sbd-alert-count">${sbd_num(count)}</div>
			<div class="sbd-sub">${hint}</div>
			${
				items.length
					? `<ul class="sbd-alert-list">${items
							.map(
								(x) => `<li data-item="${sbd_esc(x.item_code)}"><span class="n" title="${sbd_esc(
									x.item_name
								)}">${sbd_esc(x.item_name)}</span><span class="q">${qty(x)}</span></li>`
							)
							.join("")}</ul>`
					: `<div class="sbd-empty-note">${__("Nothing to check.")}</div>`
			}
		</section>`;
		return [
			card(
				"critical",
				"✕",
				__("Stock below zero"),
				a.negative_count,
				__("More went out than came in: usually a missing purchase or a bill on the wrong item"),
				a.negative,
				(x) => sbd_num(x.stock)
			),
			card(
				"warning",
				"▲",
				__("Excess stock"),
				a.excess_count,
				__("Still on the shelf from this period's purchases: return to publishers?"),
				a.excess,
				(x) => __("{0} of {1} left", [sbd_num(x.stock), sbd_num(x.purchased)])
			),
			card(
				"serious",
				"!",
				__("High returns"),
				a.returns_count,
				__("Titles with 10% or more of their sales returned"),
				a.returns,
				(x) => sbd_pct(x.rate)
			),
		].join("");
	}

	// ---------- behaviour ----------

	bind_events() {
		const $c = this.$content;
		$c.on("click", "[data-drill]", (e) => this.filters.school.set_value($(e.currentTarget).attr("data-drill")));
		$c.on("keydown", "[data-drill]", (e) => {
			if (e.key === "Enter") $(e.currentTarget).trigger("click");
		});
		$c.on("click", "tr[data-item], li[data-item]", (e) => this.open_report($(e.currentTarget).attr("data-item")));
		$c.on("click", "th.sortable", (e) => {
			const key = $(e.currentTarget).attr("data-key");
			const first = key === "item_name" || key === "status" ? 1 : -1;
			this.sort = { key, dir: this.sort.key === key ? -this.sort.dir : first };
			this.render_books();
		});
		$c.on("input", ".sbd-search", (e) => {
			this.query = e.target.value;
			this.render_books(true);
		});
		$c.on("click", "[data-action=more]", () => {
			this.show_all_books = !this.show_all_books;
			this.render_books();
		});
		$c.on("click", "[data-action=trend-table]", () => {
			this.show_trend_table = !this.show_trend_table;
			this.$content.find(".sbd-trend").html(this.trend_html(this.data));
			this.draw_trend(this.data);
		});
		$c.on("pointermove focusin", "[data-tip]", (e) => this.show_tip(e));
		$c.on("pointerleave focusout", "[data-tip]", () => this.$tip.hide());
	}

	render_books(keep_focus) {
		const $card = this.$content.find(".sbd-books");
		const caret = keep_focus ? $card.find(".sbd-search")[0]?.selectionStart : null;
		$card.html(this.books_html(this.data));
		if (keep_focus) {
			const input = $card.find(".sbd-search")[0];
			input.focus();
			input.setSelectionRange(caret, caret);
		}
	}

	tip(title, value, unit, rows) {
		this.tips.push({ title, value, unit, rows });
		return this.tips.length - 1;
	}

	show_tip(e) {
		const tip = this.tips[+e.currentTarget.getAttribute("data-tip")];
		if (!tip) return;
		// labels are data: build the tooltip with textContent, never innerHTML
		const el = this.$tip[0];
		const line = (cls, text) => {
			const node = document.createElement("div");
			node.className = cls;
			node.textContent = text;
			el.appendChild(node);
			return node;
		};
		el.replaceChildren();
		line("t", tip.title);
		line("big", `${sbd_num(tip.value)} ${tip.unit}`);
		for (const [label, value] of tip.rows) {
			const row = line("r", "");
			const name = document.createElement("span");
			name.textContent = label;
			const strong = document.createElement("b");
			strong.textContent = value;
			row.append(name, strong);
		}
		el.style.display = "block";
		let x;
		let y;
		if (e.type === "focusin") {
			const rect = e.currentTarget.getBoundingClientRect();
			x = rect.left + 24;
			y = rect.bottom + 6;
		} else {
			x = e.clientX + 14;
			y = e.clientY + 16;
		}
		if (x + el.offsetWidth > window.innerWidth - 8) x = window.innerWidth - el.offsetWidth - 8;
		if (y + el.offsetHeight > window.innerHeight - 8) y -= el.offsetHeight + 30;
		el.style.left = `${x}px`;
		el.style.top = `${y}px`;
	}

	open_report(item_code) {
		const args = this.args();
		const options = { company: args.company, from_date: args.from_date, to_date: args.to_date };
		if (args.school) options.school = [args.school];
		if (args.item_group) options.item_group = [args.item_group];
		if (args.product_bundle) options.product_bundle = [args.product_bundle];
		if (item_code) options.item_code = [item_code];
		frappe.set_route("query-report", SBD_REPORT, options);
	}
}
