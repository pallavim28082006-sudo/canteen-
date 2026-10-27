import unittest
from canteen import auth, db, qr
from canteen.i18n import S, t, pick
from canteen.routing import route
from canteen.seed import seed_demo
from canteen import ui

try:
    import qrcode  # noqa
    HAVE_QR = True
except ImportError:
    HAVE_QR = False

class Base(unittest.TestCase):
    def setUp(self):
        self.cm = db.connect(":memory:"); self.c = self.cm.__enter__(); db.init_db(self.c)
        self.b1 = db.create_business(self.c, "a", "A"); self.b2 = db.create_business(self.c, "b", "B")
        self.cat = db.add_category(self.c, self.b1, "Snacks")
        self.t1 = db.add_table(self.c, self.b1, "T1"); self.t2 = db.add_table(self.c, self.b2, "T1")
    def tearDown(self): self.cm.__exit__(None, None, None)

class MenuTests(Base):
    def test_menu_and_availability_update_immediately(self):
        i = db.add_item(self.c, self.b1, self.cat, "Dosa", 6000)
        self.assertTrue(db.menu_tree(self.c, self.b1)[0]["items"][0]["available"])
        self.assertTrue(db.set_available(self.c, self.b1, i, False))
        self.assertFalse(db.menu_tree(self.c, self.b1)[0]["items"][0]["available"])
    def test_other_business_cannot_toggle_item(self):
        i = db.add_item(self.c, self.b1, self.cat, "Dosa", 6000)
        self.assertFalse(db.set_available(self.c, self.b2, i, False))
        self.assertTrue(db.menu_tree(self.c, self.b1)[0]["items"][0]["available"])
    def test_menus_are_isolated_between_businesses(self):
        db.add_item(self.c, self.b1, self.cat, "Dosa", 6000)
        self.assertEqual(db.menu_tree(self.c, self.b2), [])
    def test_validation(self):
        with self.assertRaises(ValueError): db.add_item(self.c, self.b1, self.cat, "X", -1)
        with self.assertRaises(ValueError): db.add_item(self.c, self.b1, self.cat, "X", 10.5)
        with self.assertRaises(ValueError): db.add_item(self.c, self.b1, self.cat, " ", 10)
        with self.assertRaises(ValueError): db.add_item(self.c, self.b2, self.cat, "X", 10)  # foreign category
    def test_price_format(self):
        self.assertEqual(db.format_price(6000), "₹60"); self.assertEqual(db.format_price(6050), "₹60.50")

class QRTests(Base):
    def test_tokens_unique_and_idempotent(self):
        a = db.create_qr(self.c, self.b1, "table", self.t1)
        self.assertEqual(a, db.create_qr(self.c, self.b1, "table", self.t1))
        self.assertNotEqual(a, db.create_qr(self.c, self.b1, "menu"))
        self.assertNotEqual(db.create_qr(self.c, self.b1, "menu"), db.create_qr(self.c, self.b1, "counter"))
    def test_scan_resolves_correct_context(self):
        tt = db.create_qr(self.c, self.b1, "table", self.t1)
        ctx = db.resolve_token(self.c, tt)
        self.assertEqual((ctx["kind"], ctx["table_label"], ctx["business_id"]), ("table", "T1", self.b1))
        self.assertEqual(db.resolve_token(self.c, db.create_qr(self.c, self.b1, "counter"))["kind"], "counter")
        self.assertEqual(db.resolve_token(self.c, db.create_qr(self.c, self.b1, "menu"))["kind"], "menu")
    def test_unknown_or_malformed_tokens_rejected(self):
        for bad in (None, "", "nope", "x" * 100, "' OR 1=1 --"):
            self.assertIsNone(db.resolve_token(self.c, bad))
    def test_rotation_revokes_old_token(self):
        old = db.create_qr(self.c, self.b1, "table", self.t1)
        new = db.rotate_qr(self.c, self.b1, "table", self.t1)
        self.assertNotEqual(old, new); self.assertIsNone(db.resolve_token(self.c, old))
        self.assertIsNotNone(db.resolve_token(self.c, new))
    def test_cannot_make_qr_for_other_business_table(self):
        with self.assertRaises(ValueError): db.create_qr(self.c, self.b1, "table", self.t2)
        with self.assertRaises(ValueError): db.create_qr(self.c, self.b1, "menu", self.t1)
        with self.assertRaises(ValueError): db.create_qr(self.c, self.b1, "admin")
    def test_context_has_no_admin_data(self):
        ctx = db.resolve_token(self.c, db.create_qr(self.c, self.b1, "table", self.t1))
        self.assertFalse({"role", "user", "pw_hash", "username"} & set(ctx))
    def test_inactive_business_token_rejected(self):
        tok = db.create_qr(self.c, self.b1, "menu")
        self.c.execute("UPDATE businesses SET active=0 WHERE id=?", (self.b1,))
        self.assertIsNone(db.resolve_token(self.c, tok))
    def test_build_url_validation(self):
        self.assertEqual(qr.build_url("https://x.io/", "abc"), "https://x.io/?t=abc")
        for bad in ("javascript:alert(1)", "x.io", ""):
            with self.assertRaises(ValueError): qr.build_url(bad, "abc")
    def test_url_never_contains_admin_param(self):
        self.assertNotIn("admin", qr.build_url("https://x.io", db.create_qr(self.c, self.b1, "menu")))
    @unittest.skipUnless(HAVE_QR, "qrcode not installed")
    def test_png_generation(self):
        png = qr.make_qr_png("https://x.io/?t=abc", "Table T1")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertTrue(qr.qr_zip([("a.png", png)]).startswith(b"PK"))

class RoutingTests(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(route({}), "landing"); self.assertEqual(route({"admin": "1"}), "admin")
        self.assertEqual(route({"t": "abc"}), "customer")
    def test_table_token_cannot_reach_admin(self):
        self.assertEqual(route({"t": "abc", "admin": "1"}), "customer")

class AuthTests(Base):
    def test_hash_verify(self):
        h = auth.hash_password("correct-horse")
        self.assertTrue(auth.verify_password("correct-horse", h)); self.assertFalse(auth.verify_password("wrong-pass!", h))
        self.assertNotEqual(h, auth.hash_password("correct-horse"))
        self.assertNotIn("correct-horse", h); self.assertFalse(auth.verify_password("x", "garbage"))
    def test_short_password_rejected(self):
        with self.assertRaises(ValueError): auth.hash_password("short")
    def test_login_and_roles(self):
        auth.create_user(self.c, self.b1, "Owner", "password-1", "admin"); auth.create_user(self.c, self.b1, "cook", "password-2", "staff")
        a = auth.authenticate(self.c, self.b1, "owner", "password-1"); s = auth.authenticate(self.c, self.b1, "cook", "password-2")
        self.assertTrue(auth.can(a, "qr.manage")); self.assertFalse(auth.can(s, "qr.manage"))
        self.assertFalse(auth.can(s, "menu.edit")); self.assertTrue(auth.can(s, "menu.availability"))
        self.assertFalse(auth.can(None, "menu.availability"))
    def test_bad_login(self):
        auth.create_user(self.c, self.b1, "owner", "password-1", "admin")
        self.assertIsNone(auth.authenticate(self.c, self.b1, "owner", "nope-nope"))
        self.assertIsNone(auth.authenticate(self.c, self.b1, "ghost", "password-1"))
        self.assertIsNone(auth.authenticate(self.c, self.b2, "owner", "password-1"))  # other business
    def test_invalid_role(self):
        with self.assertRaises(ValueError): auth.create_user(self.c, self.b1, "x", "password-1", "root")

class I18nUITests(Base):
    def test_all_strings_have_both_languages(self):
        for k, v in S.items(): self.assertTrue(v["en"] and v["kn"], k)
    def test_fallback_and_format(self):
        self.assertEqual(pick("Dosa", "", "kn"), "Dosa"); self.assertIn("10", t("est_prep", "kn", m=10))
    def test_estimate_label_and_escaping(self):
        item = {"veg": 1, "available": 1, "name": "<script>x</script>", "name_kn": "", "description": "",
                "description_kn": "", "prep_minutes": 10, "price_paise": 5000}
        h = ui.item_card(item, "en")
        self.assertNotIn("<script>", h); self.assertIn("estimate only", h)
    def test_sold_out_rendered(self):
        item = {"veg": 0, "available": 0, "name": "A", "name_kn": "", "description": "", "description_kn": "",
                "prep_minutes": 5, "price_paise": 100}
        self.assertIn("Sold out", ui.item_card(item, "en"))
    def test_seed_is_idempotent(self):
        c2cm = db.connect(":memory:"); c2 = c2cm.__enter__(); db.init_db(c2)
        self.assertIsNotNone(seed_demo(c2)); self.assertIsNone(seed_demo(c2)); c2cm.__exit__(None, None, None)

if __name__ == "__main__":
    unittest.main()
