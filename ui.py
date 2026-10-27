"""Streamlit pages for the canteen app."""
import streamlit as st

import auth
import db
import qr

CUR = "₹"


def _show_qr(token, width=200):
    st.image(qr.make_qr(f"CANTEEN:{token}"), width=width)
    st.markdown(f"Order code: **{token}**")


def _order_details(order):
    for it in db.get_order_items(order["id"]):
        st.write(f"{it['qty']} × {it['name']} — {CUR}{it['price'] * it['qty']:.2f}")
    st.write(f"**Total: {CUR}{order['total']:.2f}**")


# ---------- login / register ----------
def login_page():
    st.title("🍽️ Canteen")
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Login")
        if ok:
            user = auth.login(u, p)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab_register:
        with st.form("register_form"):
            u = st.text_input("Choose a username")
            p = st.text_input("Choose a password", type="password")
            ok = st.form_submit_button("Create account")
        if ok:
            success, msg = auth.register(u, p, role="student")
            (st.success if success else st.error)(
                msg + (" You can log in now." if success else "")
            )


# ---------- student pages ----------
def menu_page(user):
    st.header("Menu")

    last = st.session_state.get("last_order")
    if last:
        st.success(f"Order placed! Total {CUR}{last['total']:.2f}. Show this QR at the counter.")
        _show_qr(last["token"])
        if st.button("Dismiss"):
            st.session_state.last_order = None
            st.rerun()
        st.divider()

    items = db.list_menu(only_available=True)
    if not items:
        st.info("No items are available right now.")
        return

    with st.form("order_form", clear_on_submit=True):
        qtys = {}
        for it in items:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{it['name']}** — {CUR}{it['price']:.2f}")
            qtys[it["id"]] = c2.number_input(
                "Qty", min_value=0, max_value=20, value=0,
                key=f"qty_{it['id']}", label_visibility="collapsed",
            )
        submit = st.form_submit_button("Place order")

    if submit:
        cart = {i: q for i, q in qtys.items() if q > 0}
        if not cart:
            st.warning("Pick at least one item.")
        else:
            _, token, total = db.create_order(user["id"], cart)
            st.session_state.last_order = {"token": token, "total": total}
            st.rerun()


def my_orders_page(user):
    st.header("My orders")
    orders = db.get_orders_for_user(user["id"])
    if not orders:
        st.info("You haven't placed any orders yet.")
        return
    for o in orders:
        icon = "🟡" if o["status"] == "pending" else "✅"
        with st.expander(f"{icon} #{o['id']} · {o['created_at']} · {o['status']}"):
            _order_details(o)
            if o["status"] == "pending":
                _show_qr(o["token"], width=160)


# ---------- staff pages ----------
def verify_page():
    st.header("Verify orders")

    code = st.text_input("Enter order code (the 6-character code under the QR)")
    code = code.strip().upper().replace("CANTEEN:", "")
    if code:
        order = db.get_order_by_token(code)
        if order is None:
            st.error("No order found with that code.")
        else:
            st.write(f"Order **#{order['id']}** for **{order['username']}** · {order['created_at']}")
            _order_details(order)
            if order["status"] == "pending":
                if st.button("Mark as served"):
                    db.set_order_status(order["id"], "served")
                    st.rerun()
            else:
                st.info("This order has already been served.")

    st.divider()
    st.subheader("Pending orders")
    pending = db.get_orders_by_status("pending")
    if not pending:
        st.write("Nothing pending.")
    for o in pending:
        with st.expander(f"#{o['id']} · {o['username']} · code {o['token']}"):
            _order_details(o)
            if st.button("Mark as served", key=f"serve_{o['id']}"):
                db.set_order_status(o["id"], "served")
                st.rerun()


# ---------- admin pages ----------
def manage_menu_page():
    st.header("Manage menu")

    with st.form("add_item", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        name = c1.text_input("Item name")
        price = c2.number_input("Price", min_value=0.0, step=5.0, value=0.0)
        if st.form_submit_button("Add item"):
            if name.strip() and price > 0:
                db.add_menu_item(name.strip(), price)
                st.rerun()
            else:
                st.warning("Enter a name and a price above 0.")

    st.divider()
    for it in db.list_menu():
        c1, c2, c3 = st.columns([3, 1.2, 1])
        c1.write(f"**{it['name']}** — {CUR}{it['price']:.2f}")
        label = "Hide" if it["available"] else "Show"
        if c2.button(label, key=f"toggle_{it['id']}"):
            db.set_available(it["id"], not it["available"])
            st.rerun()
        if c3.button("Delete", key=f"del_{it['id']}"):
            db.delete_menu_item(it["id"])
            st.rerun()


def create_staff_page():
    st.header("Create staff account")
    with st.form("staff_form", clear_on_submit=True):
        u = st.text_input("Staff username")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Create")
    if ok:
        success, msg = auth.register(u, p, role="staff")
        (st.success if success else st.error)(msg)
