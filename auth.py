"""Registration and login with salted PBKDF2 password hashes."""
import hashlib
import hmac
import secrets

import db


def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000
    ).hex()


def register(username, password, role="student"):
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if db.get_user(username):
        return False, "That username is already taken."
    salt = secrets.token_hex(16)
    db.add_user(username, _hash(password, salt), salt, role)
    return True, "Account created."


def login(username, password):
    user = db.get_user(username.strip().lower())
    if user is None:
        return None
    if hmac.compare_digest(_hash(password, user["salt"]), user["password_hash"]):
        return dict(user)
    return None


def ensure_default_admin():
    """Creates admin / admin123 on first run. Change this password after deploying."""
    if db.get_user("admin") is None:
        register("admin", "admin123", role="admin")
