"""Cloud admission and atomic, process-shared usage reservations.

Units limit application operations, not billed currency. Provider-side spending
limits remain necessary because SDK retries and model prices can vary.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
import sqlite3
import time
import uuid

from rag.runtime_data import runtime_root


def reserve(session_id, units, database=None, now=None):
    now = time.time() if now is None else now
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    database = database or runtime_root() / "usage.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = uuid.uuid4().hex
    with sqlite3.connect(str(database), timeout=15, isolation_level=None) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS usage (
                token TEXT PRIMARY KEY, session TEXT, day TEXT,
                created REAL, units INTEGER, active_until REAL
            );
        """)
        db.execute("BEGIN IMMEDIATE")
        global_used = db.execute("SELECT COALESCE(SUM(units),0) FROM usage WHERE day=?", (day,)).fetchone()[0]
        session_used = db.execute("SELECT COALESCE(SUM(units),0) FROM usage WHERE day=? AND session=?", (day, session_id)).fetchone()[0]
        last = db.execute("SELECT MAX(created) FROM usage WHERE session=?", (session_id,)).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM usage WHERE active_until>?", (now,)).fetchone()[0]
        if global_used + units > int(os.getenv("API_GLOBAL_DAILY_UNITS", "160")):
            raise RuntimeError("今日应用额度已用完，请稍后再试。")
        if session_used + units > int(os.getenv("API_SESSION_DAILY_UNITS", "24")):
            raise RuntimeError("本次会话今日额度已用完。")
        if last is not None and now - last < int(os.getenv("API_COOLDOWN_SECONDS", "30")):
            raise RuntimeError("请求过于频繁，请稍后再试。")
        if active >= int(os.getenv("API_MAX_CONCURRENT", "2")):
            raise RuntimeError("当前解读人数较多，请稍后再试。")
        db.execute("INSERT INTO usage VALUES (?,?,?,?,?,?)", (token, session_id, day, now, units, now + 1800))
        db.commit()
    return token, database


@contextmanager
def operation_budget(session_id, units):
    token, database = reserve(session_id, units)
    try:
        yield
    finally:
        with sqlite3.connect(str(database), timeout=15) as db:
            db.execute("UPDATE usage SET active_until=0 WHERE token=?", (token,))


def require_cloud_access(st):
    """A shared invite password gates every session before private data loads."""
    if os.getenv("APP_MODE", "local") != "cloud":
        return
    import hmac
    password = os.getenv("APP_ACCESS_PASSWORD", "")
    if len(password) < 20:
        st.error("部署配置缺少有效的访问口令，请联系管理员。")
        st.stop()
    if st.session_state.get("_authorized"):
        return
    with st.form("private_access"):
        supplied = st.text_input("访问口令", type="password")
        submitted = st.form_submit_button("进入")
    if submitted:
        if hmac.compare_digest(supplied.encode(), password.encode()):
            st.session_state["_authorized"] = True
            st.rerun()
        st.error("口令不正确。")
    st.stop()
