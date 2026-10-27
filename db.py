"""SQLite database layer for the canteen app (no user accounts)."""
import os
import secrets
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canteen_v2.db")

SEED_MENU = [
    ("Veg Sandwich", 40.0),
    ("Masala Dosa", 60.0),
    ("Samosa (2 pcs)", 30.0),
    ("Veg Fried Rice", 80.0),
    ("Chai", 15.0),
    ("Cold Coffee", 50.0),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                available INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                total REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                qty INTEGER NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM menu").fetchone()[0] == 0:
            conn.executemany("INSERT INTO menu (name, price) VALUES (?, ?)", SEED_MENU)


# ---------- menu ----------
def list_menu(only_available=False):
    q = "SELECT * FROM menu"
    if only_available:
        q += " WHERE available = 1"
    q += " ORDER BY id"
    with get_conn() as conn:
        return conn.execute(q).fetchall()


def add_menu_item(name, price):
    with get_conn() as conn:
        conn.execute("INSERT INTO menu (name, price) VALUES (?, ?)", (name, price))


def set_available(item_id, available):
    with get_conn() as conn:
        conn.execute("UPDATE menu SET available = ? WHERE id = ?", (1 if available else 0, item_id))


def delete_menu_item(item_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM menu WHERE id = ?", (item_id,))


# ---------- orders ----------
def create_order(customer_name, cart):
    """cart: {menu_id: qty}. Prices come from the DB, never from the client."""
    with get_conn() as conn:
        lines, total = [], 0.0
        for menu_id, qty in cart.items():
            row = conn.execute(
                "SELECT * FROM menu WHERE id = ? AND available = 1", (menu_id,)
            ).fetchone()
            if row is None or qty <= 0:
                continue
            lines.append((row["name"], row["price"], qty))
            total += row["price"] * qty
        if not lines:
            raise ValueError("No valid items in cart.")

        token = secrets.token_hex(3).upper()
        while conn.execute("SELECT 1 FROM orders WHERE token = ?", (token,)).fetchone():
            token = secrets.token_hex(3).upper()

        cur = conn.execute(
            "INSERT INTO orders (customer_name, token, status, total, created_at) VALUES (?, ?, 'pending', ?, ?)",
            (customer_name or "Guest", token, total, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items (order_id, name, price, qty) VALUES (?, ?, ?, ?)",
            [(order_id, n, p, q) for n, p, q in lines],
        )
        return order_id, token, total


def get_order_items(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()


def get_order_by_token(token):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE token = ?", (token,)).fetchone()


def get_orders_by_status(status):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY id", (status,)
        ).fetchall()


def set_order_status(order_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
