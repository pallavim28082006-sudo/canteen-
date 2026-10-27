"""Persistent storage (SQLite). Money is stored as integer paise. Every row is business-scoped."""
from __future__ import annotations
import os, secrets, sqlite3
from contextlib import contextmanager

DEFAULT_PATH = os.environ.get("CANTEEN_DB", "canteen.db")
QR_KINDS = ("menu", "table", "counter")

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses(
 id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, name_kn TEXT NOT NULL DEFAULT '',
 whatsapp TEXT NOT NULL DEFAULT '', theme_color TEXT NOT NULL DEFAULT '#E8590C',
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
 username TEXT NOT NULL, pw_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff')),
 active INTEGER NOT NULL DEFAULT 1, UNIQUE(business_id, username));
CREATE TABLE IF NOT EXISTS categories(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
 name TEXT NOT NULL, name_kn TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS menu_items(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
 category_id INTEGER NOT NULL REFERENCES categories(id),
 name TEXT NOT NULL, name_kn TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
 description_kn TEXT NOT NULL DEFAULT '', price_paise INTEGER NOT NULL CHECK(price_paise >= 0),
 veg INTEGER NOT NULL DEFAULT 1, available INTEGER NOT NULL DEFAULT 1,
 prep_minutes INTEGER NOT NULL DEFAULT 10 CHECK(prep_minutes >= 0), sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dining_tables(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
 label TEXT NOT NULL, UNIQUE(business_id, label));
CREATE TABLE IF NOT EXISTS qr_codes(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
 kind TEXT NOT NULL CHECK(kind IN ('menu','table','counter')),
 table_id INTEGER REFERENCES dining_tables(id), token TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

@contextmanager
def connect(path: str | None = None):
    conn = sqlite3.connect(path or DEFAULT_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    except BaseException:  # Streamlit's st.rerun() is a BaseException; keep writes made before it
        conn.commit()
        raise
    finally:
        conn.close()

def init_db(conn) -> None:
    conn.executescript(SCHEMA)

def create_business(conn, slug, name, name_kn="", whatsapp="", theme_color="#E8590C") -> int:
    if not slug.strip() or not name.strip():
        raise ValueError("slug and name are required")
    return conn.execute(
        "INSERT INTO businesses(slug,name,name_kn,whatsapp,theme_color) VALUES(?,?,?,?,?)",
        (slug.strip(), name.strip(), name_kn, whatsapp, theme_color)).lastrowid

def get_business(conn, business_id):
    return conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()

def add_category(conn, business_id, name, name_kn="", sort=0) -> int:
    if not name.strip():
        raise ValueError("category name required")
    return conn.execute("INSERT INTO categories(business_id,name,name_kn,sort) VALUES(?,?,?,?)",
                        (business_id, name.strip(), name_kn, sort)).lastrowid

def add_item(conn, business_id, category_id, name, price_paise, *, name_kn="", description="",
             description_kn="", veg=True, prep_minutes=10, available=True, sort=0) -> int:
    if not name.strip():
        raise ValueError("item name required")
    if not isinstance(price_paise, int) or price_paise < 0:
        raise ValueError("price must be a non-negative integer (paise)")
    if not conn.execute("SELECT 1 FROM categories WHERE id=? AND business_id=?",
                        (category_id, business_id)).fetchone():
        raise ValueError("category does not belong to this business")
    return conn.execute(
        """INSERT INTO menu_items(business_id,category_id,name,name_kn,description,description_kn,
           price_paise,veg,available,prep_minutes,sort) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (business_id, category_id, name.strip(), name_kn, description, description_kn,
         price_paise, int(veg), int(available), prep_minutes, sort)).lastrowid

def set_available(conn, business_id, item_id, available: bool) -> bool:
    cur = conn.execute("UPDATE menu_items SET available=? WHERE id=? AND business_id=?",
                       (int(available), item_id, business_id))
    return cur.rowcount == 1

def menu_tree(conn, business_id):
    """Categories (sorted) each with their items; empty categories omitted. Always reads live data."""
    out = []
    for c in conn.execute("SELECT * FROM categories WHERE business_id=? ORDER BY sort,id", (business_id,)).fetchall():
        items = [dict(i) for i in conn.execute(
            "SELECT * FROM menu_items WHERE category_id=? AND business_id=? ORDER BY sort,id",
            (c["id"], business_id))]
        if items:
            out.append({**dict(c), "items": items})
    return out

def add_table(conn, business_id, label) -> int:
    if not label.strip():
        raise ValueError("table label required")
    return conn.execute("INSERT INTO dining_tables(business_id,label) VALUES(?,?)",
                        (business_id, label.strip())).lastrowid

def list_tables(conn, business_id):
    return conn.execute("SELECT * FROM dining_tables WHERE business_id=? ORDER BY id", (business_id,)).fetchall()

def _find_active_qr(conn, business_id, kind, table_id):
    if table_id is None:
        return conn.execute("SELECT * FROM qr_codes WHERE business_id=? AND kind=? AND table_id IS NULL AND active=1",
                            (business_id, kind)).fetchone()
    return conn.execute("SELECT * FROM qr_codes WHERE business_id=? AND kind=? AND table_id=? AND active=1",
                        (business_id, kind, table_id)).fetchone()

def create_qr(conn, business_id, kind, table_id=None) -> str:
    """Idempotent: returns the active token for the target, creating one if needed."""
    if kind not in QR_KINDS:
        raise ValueError("invalid QR kind")
    if kind == "table":
        if table_id is None or not conn.execute("SELECT 1 FROM dining_tables WHERE id=? AND business_id=?",
                                                (table_id, business_id)).fetchone():
            raise ValueError("table does not belong to this business")
    elif table_id is not None:
        raise ValueError("only table QR codes take a table_id")
    row = _find_active_qr(conn, business_id, kind, table_id)
    if row:
        return row["token"]
    token = secrets.token_urlsafe(12)  # ~96 bits, unguessable
    conn.execute("INSERT INTO qr_codes(business_id,kind,table_id,token) VALUES(?,?,?,?)",
                 (business_id, kind, table_id, token))
    return token

def rotate_qr(conn, business_id, kind, table_id=None) -> str:
    """Revoke the current token (e.g. a leaked/defaced sticker) and issue a new one."""
    row = _find_active_qr(conn, business_id, kind, table_id)
    if row:
        conn.execute("UPDATE qr_codes SET active=0 WHERE id=?", (row["id"],))
    return create_qr(conn, business_id, kind, table_id)

def resolve_token(conn, token):
    """Map a scanned token to a *customer-scope* context. Never returns anything admin-related."""
    if not token or len(token) > 64:
        return None
    r = conn.execute(
        """SELECT q.kind, q.business_id, b.slug, b.name, b.name_kn, b.whatsapp, b.theme_color, t.label AS table_label
           FROM qr_codes q JOIN businesses b ON b.id=q.business_id
           LEFT JOIN dining_tables t ON t.id=q.table_id
           WHERE q.token=? AND q.active=1 AND b.active=1""", (token,)).fetchone()
    return dict(r) if r else None

def list_qrs(conn, business_id):
    return conn.execute(
        """SELECT q.kind, q.token, t.label AS table_label FROM qr_codes q
           LEFT JOIN dining_tables t ON t.id=q.table_id
           WHERE q.business_id=? AND q.active=1 ORDER BY q.id""", (business_id,)).fetchall()

def format_price(paise: int) -> str:
    return f"₹{paise // 100:,}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"
