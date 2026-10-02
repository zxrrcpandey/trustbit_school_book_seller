# Copyright (c) 2026, Trustbit Software and contributors
# Longer sessions for the KGS Staff app (/staff) — owner decision 2026-10-02.
#
# splashbox.in has ONE global idle window (System Settings session_expiry =
# 01:00), so staff on the phone app would sign in (password + OTP) every idle
# hour. This module gives sessions that were SIGNED IN THROUGH THE STAFF APP
# (the PWA's login call carries staff_app=1) an N-day idle window, for users
# holding a staff-app role. Desk logins keep the global hour.
# Ported from the Betul exec PWA (trustbit_ethanol ts_session_extend.py, v2.50),
# where the same three mechanisms were verified against frappe v15:
#
#   sid cookie (auth.py init_cookies, max_age = global) ....... after_request
#       hook re-issues the cookie with the longer max_age (after_request runs
#       before process_response() flushes cookies, so the later write wins).
#   cache resume (sessions.py get_session_data_from_cache honours the
#       PER-SESSION session_expiry stamped into session data) ...... login hook
#       stamps "<days*24>:00:00" + staff_app=1 and persists it with
#       session_obj.update(force=True).
#   DB resume + daily reaper (both use the GLOBAL threshold against
#       tabSessions.lastupdate — and a Redis FLUSHALL on deploy forces the DB
#       path) ...................................................... cron job
#       every 10 minutes slides lastupdate, bounded per row by that session's
#       OWN real activity (sessiondata last_updated, never written here).
#       10 minutes, not Betul's hourly: the global window here is 1 hour.
#
# OFF unless site_config carries kgs_staff_session_days >= 1 (fail-closed —
# this weakens auth, it must never arm itself). Switching it off stops new
# extensions; already-stamped sessions live until they expire or are cleared
# (full rollback = key off + clear_sessions for the staff accounts).
# Every entry point is fail-soft: after_request runs on EVERY request and
# on_session_creation has no exception net — a raise there is a site-wide
# login outage.
#
# HARD INVARIANTS (copied from Betul, do not "improve" away):
#   * never write the frappe.cache "session"/"last_db_session_update" hashes
#     and never call Session.update() for touched rows — racing a logout
#     would resurrect a session whose DB row is already deleted;
#   * never write tabUser.last_active;
#   * never log a sid — it is a bearer credential.

import re

import frappe
from frappe.utils import add_to_date, cint, now, time_diff_in_seconds

from trustbit_school_book_seller.staff_app.api import STAFF_ROLES

_CONF_KEY = "kgs_staff_session_days"
_MAX_DAYS = 30
_STAMP_RE = re.compile(r"^\d{1,4}:\d{2}:\d{2}$")
_SID_RE = re.compile(r"^[a-f0-9]{16,}\Z")
_LOG_THROTTLE_SEC = 3600


def _extended_days():
	try:
		days = cint(frappe.conf.get(_CONF_KEY))
	except Exception:
		return 0
	if days < 1:
		return 0
	return min(days, _MAX_DAYS)


def _expiry_stamp(days):
	stamp = "%d:00:00" % (days * 24)
	return stamp if _STAMP_RE.match(stamp) else None


def _is_staff(user):
	try:
		return bool(set(frappe.get_roles(user)) & set(STAFF_ROLES))
	except Exception:
		return False


def _throttled_log(title, message):
	try:
		key = "kgs_staff_session:" + title
		if frappe.cache.get_value(key):
			return
		frappe.cache.set_value(key, 1, expires_in_sec=_LOG_THROTTLE_SEC)
		frappe.log_error(title=title, message=message)
	except Exception:
		pass


def _session_is_staff_app(session, stamp):
	data = session.get("data") or {}
	return cint(data.get("staff_app")) == 1 and data.get("session_expiry") == stamp


def extend_staff_session_cookie(response=None, request=None):
	"""after_request: re-issue the sid cookie with the long max_age, only for a
	session that the login hook stamped. Cheapest checks first."""
	try:
		days = _extended_days()
		if not days:
			return
		cookie_manager = getattr(frappe.local, "cookie_manager", None)
		if cookie_manager is None:
			return
		session = getattr(frappe.local, "session", None) or {}
		user = session.get("user")
		sid = session.get("sid")
		if not user or user in ("Guest", "Administrator") or not sid or sid == "Guest":
			return
		# frappe.set_user() mid-request overwrites session.sid with the username;
		# re-issuing that would log the phone out. Only real session hashes.
		if sid == user or not _SID_RE.match(sid):
			return
		if "sid" in getattr(cookie_manager, "to_delete", ()):
			return  # logout response
		if not _session_is_staff_app(session, _expiry_stamp(days)):
			return
		if not _is_staff(user):
			return
		cookie_manager.set_cookie("sid", sid, max_age=days * 86400, httponly=True)
	except Exception as exc:
		try:
			_throttled_log(
				"staff app session cookie hook failed",
				"user=%s error=%s: %s"
				% (getattr(frappe.session, "user", "?"), type(exc).__name__, str(exc)[:300]),
			)
		except Exception:
			pass


def stamp_staff_session_expiry(login_manager=None):
	"""on_session_creation: stamp the long expiry when the login came from the
	staff app (form_dict staff_app=1, sent with both the password and the OTP
	call) and the user holds a staff-app role."""
	try:
		days = _extended_days()
		if not days:
			return
		if cint((frappe.form_dict or {}).get("staff_app")) != 1:
			return
		user = getattr(frappe.session, "user", None)
		if not user or user in ("Guest", "Administrator"):
			return
		if not _is_staff(user):
			return
		stamp = _expiry_stamp(days)
		session_obj = getattr(frappe.local, "session_obj", None)
		if not stamp or session_obj is None:
			return
		frappe.session.data.session_expiry = stamp
		frappe.session.data.staff_app = 1
		session_obj.update(force=True)
	except Exception as exc:
		try:
			_throttled_log(
				"staff app session stamp failed",
				"user=%s error=%s: %s"
				% (getattr(frappe.session, "user", "?"), type(exc).__name__, str(exc)[:300]),
			)
		except Exception:
			pass


def touch_staff_sessions():
	"""Every 10 minutes: keep stamped staff-app session rows above the GLOBAL
	1-hour DB-resume/reaper threshold, bounded by each session's own last real
	activity. Writes ONLY tabSessions.lastupdate, with Python timestamps
	(site-local IST, like lastupdate — the server clock is UTC, Rule 11)."""
	try:
		days = _extended_days()
		stamp = _expiry_stamp(days) if days else None
		if not stamp:
			return
		rows = frappe.db.sql(
			"""select sid, user, sessiondata from tabSessions
			where sessiondata like %s order by lastupdate desc limit 500""",
			("%'staff_app': 1%",),
			as_dict=True,
		)
		bound_seconds = days * 86400
		base_now = now()
		touched = 0
		for i, row in enumerate(rows):
			try:
				data = frappe._dict(frappe.safe_eval(row.sessiondata or "{}"))
				if cint(data.get("staff_app")) != 1 or data.get("session_expiry") != stamp:
					continue
				if not _is_staff(row.user):
					continue
				last_real = data.get("last_updated")
				if not last_real or time_diff_in_seconds(base_now, last_real) > bound_seconds:
					continue
				# stagger one second per row so lastupdate never ties
				touch_ts = add_to_date(base_now, seconds=-i, as_string=True, as_datetime=True)
				frappe.db.sql("update tabSessions set lastupdate=%s where sid=%s", (touch_ts, row.sid))
				touched += 1
			except Exception:
				continue
		if touched:
			frappe.db.commit()
	except Exception as exc:
		try:
			_throttled_log(
				"staff app session touch job failed", "error=%s: %s" % (type(exc).__name__, str(exc)[:300])
			)
		except Exception:
			pass
