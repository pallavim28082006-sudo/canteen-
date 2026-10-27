"""Streamlit pages for the canteen app."""
import streamlit as st

import db
import qr

CUR = "₹"
STAFF_PIN = "1234"  # change this, or set to "" to remove the PIN prompt


def _show_qr(token, width=200):
    st.image(qr.make_qr(f"CANTEEN:{token}"), width=width)
    st.markdown(f"Order code: **{token}**")


def _order_details(order):
    for it in db.get_order_items(order["id"]):
        st.write(f"{it['qty']} × {it['name']} — {CUR}{it['price'] * it['qty']:.2f}")
    st.write(f"**Total: {CUR}{order['total']:.2f}**")


def _pin_gate():
    """Returns True if the staff area may be shown."""
    if not STAFF_PIN or st.session_state.get("staff_ok"):
        return True
    with st.form("pin_form"):
        pin = st.text_input("Staff PIN", type="password")
        ok = st.form_submit_button("Enter")
    if ok:
        if pin == STAFF_PIN:
            st.session_state.staff_ok = True
            st.rerun()
        else:
            st.error("Wrong PIN.")
    return False


# ---------- customer pages ----------
def order_page():
    st.title("🍽️ Canteen")

    last = st.session_state.get("last_order")
    if last:
        st.success(f"Order placed! Total {CUR}{last['total']:.2f}. Show this QR at the counter.")
        _show_qr(last["token"])
        st.caption("Save or screenshot this code. You can check its status on the 'Track my order' page.")
        if st.button("Place another order"):
            st.session_state.last_order = None
            st.rerun()
        return

    items = db.list_menu(only_available=True)
    if not items:
        st.info("No items are available right now.")
        return

    with st.form("order_form", clear_on_submit=True):
        name = st.text_input("Your name (optional)")
        st.subheader("Menu")
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
            _, token, total = db.create_order(name.strip(), cart)
            st.session_state.last_order = {"token": token, "total": total}
            st.rerun()


def track_page():
    st.header("Track my order")
    code = st.text_input("Enter your order code")
    code = code.strip().upper().replace("CANTEEN:", "")
    if not code:
        return
    order = db.get_order_by_token(code)
    if order is None:
        st.error("No order found with that code.")
        return
    if order["status"] == "pending":
        st.warning("Status: being prepared / waiting for pickup")
    else:
        st.success("Status: served")
    _order_details(order)
    if order["status"] == "pending":
        _show_qr(order["token"], width=160)


# ---------- staff pages ----------
def verify_page():
    st.header("Staff counter")
    if not _pin_gate():
        return

    code = st.text_input("Enter order code (6 characters under the QR)")
    code = code.strip().upper().replace("CANTEEN:", "")
    if code:
        order = db.get_order_by_token(code)
        if order is None:
            st.error("No order found with that code.")
        else:
            st.write(f"Order **#{order['id']}** for **{order['customer_name']}** · {order['created_at']}")
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
        with st.expander(f"#{o['id']} · {o['customer_name']} · code {o['token']}"):
            _order_details(o)
            if st.button("Mark as served", key=f"serve_{o['id']}"):
                db.set_order_status(o["id"], "served")
                st.rerun()


def manage_menu_page():
    st.header("Manage menu")
    if not _pin_gate():
        return

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
        if c2.button("Hide" if it["available"] else "Show", key=f"toggle_{it['id']}"):
            db.set_available(it["id"], not it["available"])
            st.rerun()
        if c3.button("Delete", key=f"del_{it['id']}"):
            db.delete_menu_item(it["id"])
            st.rerun()
