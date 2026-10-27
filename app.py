import streamlit as st

import db
import ui

st.set_page_config(page_title="Canteen", page_icon="🍽️")

db.init_db()

PAGES = {
    "Order food": ui.order_page,
    "Track my order": ui.track_page,
    "Staff counter": ui.verify_page,
    "Manage menu": ui.manage_menu_page,
}

with st.sidebar:
    choice = st.radio("Go to", list(PAGES.keys()))

PAGES[choice]()
