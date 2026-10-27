"""Streamlit entry point:  streamlit run app.py"""
import html, os
from urllib.parse import quote
import streamlit as st
from canteen import auth, db, qr, ui
from canteen.i18n import LANGS, t, pick
from canteen.routing import route
from canteen.seed import seed_demo

st.set_page_config(page_title="Digital Canteen", page_icon="🍽️", layout="centered")

@st.cache_resource
def _bootstrap():
    with db.connect() as c:
        db.init_db(c)
        res = seed_demo(c)
    if res and res[1]:
        print(f"[canteen] demo admin created -> username: admin  password: {res[1]}")
_bootstrap()

def lang_picker(key="lang"):
    return st.segmented_control(t("language"), list(LANGS), format_func=LANGS.get, default="en",
                                key=key, label_visibility="collapsed") or "en"

def customer(token):
    with db.connect() as c:
        ctx = db.resolve_token(c, token)
        lang = lang_picker()
        if not ctx:
            st.warning(t("bad_qr", lang)); return
        st.markdown(ui.css(ctx["theme_color"]), unsafe_allow_html=True)
        st.markdown(ui.hero(ctx, lang), unsafe_allow_html=True)
        tree = db.menu_tree(c, ctx["business_id"])  # live read: availability changes show on next rerun
    st.info(t("browse_only", lang))
    if not tree:
        st.write(t("empty_menu", lang))
    else:
        for tab, cat in zip(st.tabs([pick(x["name"], x["name_kn"], lang) for x in tree]), tree):
            with tab:
                for it in cat["items"]:
                    st.markdown(ui.item_card(it, lang), unsafe_allow_html=True)
    if ctx["whatsapp"].isdigit():
        st.link_button(t("whatsapp", lang), f"https://wa.me/{ctx['whatsapp']}")

def landing():
    st.markdown(ui.css("#E8590C"), unsafe_allow_html=True)
    lang = lang_picker()
    st.markdown('<div class="hero"><h1>🍽️ Digital Canteen</h1></div>', unsafe_allow_html=True)
    st.write(t("scan_prompt", lang))

def admin():
    user = st.session_state.get("user")
    if not user:
        st.title("Staff sign-in")
        with st.form("login"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in"):
                with db.connect() as c:
                    biz = c.execute("SELECT id FROM businesses WHERE active=1 ORDER BY id LIMIT 1").fetchone()
                    user = auth.authenticate(c, biz["id"], u, p) if biz else None
                if user:
                    st.session_state["user"] = user; st.rerun()
                else:
                    st.error("Invalid credentials")
        return
    bid = user["business_id"]  # every query below is scoped to the signed-in user's business
    st.caption(f'{user["username"]} · {user["role"]}')
    if st.button("Sign out"):
        st.session_state.pop("user"); st.rerun()
    tabs = st.tabs(["Menu", "Tables & QR codes"] if auth.can(user, "qr.manage") else ["Menu"])
    with tabs[0], db.connect() as c:
        for cat in db.menu_tree(c, bid):
            st.subheader(cat["name"])
            for it in cat["items"]:
                on = st.toggle(f'{it["name"]} · {db.format_price(it["price_paise"])}', bool(it["available"]),
                               key=f'av{it["id"]}', disabled=not auth.can(user, "menu.availability"))
                if on != bool(it["available"]):
                    db.set_available(c, bid, it["id"], on); st.rerun()
        if auth.can(user, "menu.edit"):
            with st.expander("Add item"), st.form("additem", clear_on_submit=True):
                cats = c.execute("SELECT id,name FROM categories WHERE business_id=?", (bid,)).fetchall()
                cid = st.selectbox("Category", [r["id"] for r in cats], format_func=lambda i: next(r["name"] for r in cats if r["id"] == i)) if cats else None
                name = st.text_input("Name"); name_kn = st.text_input("Name (Kannada)")
                price = st.number_input("Price (₹)", min_value=0.0, step=1.0)
                prep = st.number_input("Estimated prep (min)", 0, 120, 10); veg = st.checkbox("Vegetarian", True)
                if st.form_submit_button("Add") and cid:
                    try:
                        db.add_item(c, bid, cid, name, round(price * 100), name_kn=name_kn, prep_minutes=int(prep), veg=veg)
                        st.success("Added"); st.rerun()
                    except ValueError as e:
                        st.error(str(e))
    if len(tabs) > 1:
        with tabs[1], db.connect() as c:
            label = st.text_input("New table label")
            if st.button("Add table") and label:
                try:
                    db.add_table(c, bid, label); st.rerun()
                except Exception:
                    st.error("Table label already exists or is invalid")
            base = st.text_input("Public app URL", os.environ.get("CANTEEN_BASE_URL", "http://localhost:8501"))
            if st.button("Generate / show QR codes"):
                db.create_qr(c, bid, "menu"); db.create_qr(c, bid, "counter")
                for tb in db.list_tables(c, bid):
                    db.create_qr(c, bid, "table", tb["id"])
            files = []
            for q in db.list_qrs(c, bid):
                cap = {"menu": "Main menu", "counter": "Counter pickup"}.get(q["kind"], f'Table {q["table_label"]}')
                try:
                    png = qr.make_qr_png(qr.build_url(base, q["token"]), cap)
                except ValueError as e:
                    st.error(str(e)); break
                files.append((cap.replace(" ", "_") + ".png", png))
                st.image(png, caption=cap, width=200)
                st.download_button(f"Download {cap}", png, cap.replace(" ", "_") + ".png", "image/png", key="d" + q["token"])
            if files:
                st.download_button("Download all (ZIP)", qr.qr_zip(files), "qr_codes.zip", "application/zip")

page = route(st.query_params)
if page == "customer":
    customer(st.query_params["t"])
elif page == "admin":
    admin()
else:
    landing()
