"""Streamlit pages for the canteen app."""
import io

import streamlit as st
from PIL import Image

import db
import qr

CUR = "₹"
STAFF_PIN = "1234"  # change this, or set to "" to remove the PIN prompt
GRID_COLS = 3

CSS = """
<style>
.hero{background:linear-gradient(135deg,#ff7a18,#ffb347);padding:22px 22px;
      border-radius:16px;color:#fff;margin-bottom:14px}
.hero h1{margin:0;font-size:1.9rem;color:#fff;padding:0}
.hero p{margin:4px 0 0;opacity:.95}
.emoji-tile{height:150px;border-radius:12px;display:flex;align-items:center;
            justify-content:center;font-size:64px;
            background:linear-gradient(135deg,#fff3e0,#ffe0b2);margin-bottom:8px}
div[data-testid="stImage"] img{height:150px;width:100%;object-fit:cover;border-radius:12px}
.price{color:#e65100;font-weight:700;font-size:1.05rem}
.qty{text-align:center;font-weight:700;font-size:1.1rem;padding-top:6px}
div[data-testid="stButton"] button{width:100%;border-radius:10px}
[data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:.4rem}
[data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] > div{min-width:0 !important}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def _show_qr(token, width=200):
    st.image(qr.make_qr(f"CANTEEN:{token}"), width=width)
    st.markdown(f"Order code: **{token}**")


def _order_details(order):
    for it in db.get_order_items(order["id"]):
        st.write(f"{it['qty']} × {it['name']} — {CUR}{it['price'] * it['qty']:.0f}")
    st.write(f"**Total: {CUR}{order['total']:.0f}**")


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


def _prepare_image(file):
    """Resize an uploaded photo so the database stays small."""
    if file is None:
        return None
    img = Image.open(file).convert("RGB")
    img.thumbnail((600, 600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _item_image(it):
    if it["image"]:
        st.image(it["image"])
    elif it["image_url"]:
        st.image(it["image_url"])
    else:
        st.markdown(f"<div class='emoji-tile'>{it['emoji']}</div>", unsafe_allow_html=True)


# ---------- cart helpers ----------
def _cart():
    if "cart" not in st.session_state:
        st.session_state.cart = {}
    return st.session_state.cart


def _add(item_id):
    cart = _cart()
    cart[item_id] = min(cart.get(item_id, 0) + 1, 20)


def _sub(item_id):
    cart = _cart()
    if cart.get(item_id, 0) > 1:
        cart[item_id] -= 1
    else:
        cart.pop(item_id, None)


def _clear_cart():
    st.session_state.cart = {}


# ---------- customer pages ----------
def _cart_box(items_by_id):
    cart = _cart()
    lines = [(items_by_id[i], q) for i, q in cart.items() if i in items_by_id]
    with st.container(border=True):
        if not lines:
            st.markdown("🛒 **Your cart is empty.** Tap **Add +** on any item below.")
            return
        count = sum(q for _, q in lines)
        total = sum(it["price"] * q for it, q in lines)
        st.markdown(f"### 🛒 Your cart · {count} item{'s' if count != 1 else ''} · {CUR}{total:.0f}")
        for it, q in lines:
            st.write(f"{it['emoji']} {q} × {it['name']} — {CUR}{it['price'] * q:.0f}")
        name = st.text_input("Your name (optional)", key="cust_name")
        c1, c2 = st.columns(2)
        if c1.button("Place order ✅", type="primary"):
            _, token, total = db.create_order(
                name.strip(), {it["id"]: q for it, q in lines}
            )
            st.session_state.last_order = {"token": token, "total": total}
            st.session_state.cart = {}
            st.rerun()
        c2.button("Clear cart", on_click=_clear_cart)


def _item_card(it):
    cart = _cart()
    qty = cart.get(it["id"], 0)
    with st.container(border=True):
        _item_image(it)
        st.markdown(f"**{it['name']}**")
        st.markdown(f"<span class='price'>{CUR}{it['price']:.0f}</span>", unsafe_allow_html=True)
        if qty == 0:
            st.button("Add +", key=f"add_{it['id']}", on_click=_add, args=(it["id"],))
        else:
            c1, c2, c3 = st.columns([1, 1, 1])
            c1.button("−", key=f"sub_{it['id']}", on_click=_sub, args=(it["id"],))
            c2.markdown(f"<div class='qty'>{qty}</div>", unsafe_allow_html=True)
            c3.button("+", key=f"inc_{it['id']}", on_click=_add, args=(it["id"],))


def order_page():
    last = st.session_state.get("last_order")
    if last:
        st.markdown(
            "<div class='hero'><h1>✅ Order placed!</h1>"
            f"<p>Total {CUR}{last['total']:.0f} · show this QR at the counter</p></div>",
            unsafe_allow_html=True,
        )
        _show_qr(last["token"])
        st.caption("Save or screenshot this code. You can check its status on the 'Track my order' page.")
        if st.button("Place another order"):
            st.session_state.last_order = None
            st.rerun()
        return

    st.markdown(
        "<div class='hero'><h1>🍽️ Canteen</h1>"
        "<p>Pick your food, place the order, show the QR at the counter.</p></div>",
        unsafe_allow_html=True,
    )

    items = db.list_menu(only_available=True)
    if not items:
        st.info("No items are available right now.")
        return

    _cart_box({it["id"]: it for it in items})

    by_cat = {}
    for it in items:
        cat = it["category"] if it["category"] in db.CATEGORIES else "Other"
        by_cat.setdefault(cat, []).append(it)
    cats = [c for c in db.CATEGORIES if c in by_cat]

    tabs = st.tabs([f"{db.CATEGORIES[c]} {c}" for c in cats])
    for tab, cat in zip(tabs, cats):
        with tab:
            group = by_cat[cat]
            for start in range(0, len(group), GRID_COLS):
                cols = st.columns(GRID_COLS)
                for col, it in zip(cols, group[start:start + GRID_COLS]):
                    with col:
                        _item_card(it)


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

    cat_names = list(db.CATEGORIES)

    st.subheader("Add a new item")
    with st.form("add_item", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        name = c1.text_input("Item name")
        price = c2.number_input("Price", min_value=0.0, step=5.0, value=0.0)
        c3, c4 = st.columns(2)
        category = c3.selectbox("Category", cat_names)
        emoji = c4.text_input("Emoji (shown when there is no photo)", value="")
        photo = st.file_uploader("Photo (optional)", type=["png", "jpg", "jpeg", "webp"])
        url = st.text_input("...or a photo link (optional)")
        if st.form_submit_button("Add item"):
            if name.strip() and price > 0:
                db.add_menu_item(name.strip(), price, category, emoji.strip(),
                                 _prepare_image(photo), url.strip())
                st.rerun()
            else:
                st.warning("Enter a name and a price above 0.")

    st.divider()
    st.subheader("Existing items")
    items = db.list_menu()
    for cat in cat_names:
        group = [i for i in items if (i["category"] if i["category"] in db.CATEGORIES else "Other") == cat]
        if not group:
            continue
        st.markdown(f"#### {db.CATEGORIES[cat]} {cat}")
        for it in group:
            hidden = "" if it["available"] else " (hidden)"
            with st.expander(f"{it['emoji']} {it['name']} — {CUR}{it['price']:.0f}{hidden}"):
                with st.form(f"edit_{it['id']}"):
                    e1, e2 = st.columns([3, 1])
                    n = e1.text_input("Name", value=it["name"])
                    p = e2.number_input("Price", min_value=0.0, step=5.0, value=float(it["price"]))
                    e3, e4 = st.columns(2)
                    c = e3.selectbox("Category", cat_names, index=cat_names.index(cat))
                    em = e4.text_input("Emoji", value=it["emoji"])
                    ph = st.file_uploader("New photo", type=["png", "jpg", "jpeg", "webp"],
                                          key=f"photo_{it['id']}")
                    u = st.text_input("Photo link", value=it["image_url"] or "")
                    rm = st.checkbox("Remove uploaded photo")
                    if st.form_submit_button("Save changes"):
                        db.update_menu_item(it["id"], n.strip() or it["name"], p, c, em.strip(),
                                            u.strip(), _prepare_image(ph), rm)
                        st.rerun()
                b1, b2 = st.columns(2)
                if b1.button("Hide" if it["available"] else "Show", key=f"toggle_{it['id']}"):
                    db.set_available(it["id"], not it["available"])
                    st.rerun()
                if b2.button("Delete", key=f"del_{it['id']}"):
                    db.delete_menu_item(it["id"])
                    st.rerun()
