import streamlit as st

import auth
import db
import ui

st.set_page_config(page_title="Canteen", page_icon="🍽️")

db.init_db()
auth.ensure_default_admin()

if "user" not in st.session_state:
    st.session_state.user = None

user = st.session_state.user

if user is None:
    ui.login_page()
else:
    PAGES = {
        "student": {
            "Menu": lambda: ui.menu_page(user),
            "My orders": lambda: ui.my_orders_page(user),
        },
        "staff": {
            "Verify orders": ui.verify_page,
        },
        "admin": {
            "Verify orders": ui.verify_page,
            "Manage menu": ui.manage_menu_page,
            "Create staff": ui.create_staff_page,
        },
    }
    pages = PAGES.get(user["role"], PAGES["student"])

    with st.sidebar:
        st.write(f"Logged in as **{user['username']}** ({user['role']})")
        choice = st.radio("Go to", list(pages.keys()))
        if st.button("Log out"):
            st.session_state.user = None
            st.session_state.pop("last_order", None)
            st.rerun()

    pages[choice]()
