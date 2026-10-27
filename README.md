# Digital Canteen Platform

## Status
| Phase | Scope | State |
|---|---|---|
| 1 | Premium mobile UI, menu, QR generation + scan routing, EN/KN, roles/login, availability toggle | Implemented; unit tests cover logic. Streamlit UI **not yet run in a browser** |
| 2–6 | Cart, orders, kitchen, payments, analytics, hardening | Not started |

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export CANTEEN_ADMIN_PASSWORD='choose-a-strong-password'   # else a random one is printed on first run
export CANTEEN_BASE_URL='https://your-host'                # used inside QR codes
streamlit run app.py
```
- Staff sign-in: `/?admin=1` (user `admin`). Generate/download QR codes under **Tables & QR codes**.
- Customers only ever use `/?t=<token>` links from QR stickers.
- Data: SQLite file `canteen.db` (override with `CANTEEN_DB`).

## Tests
`python -m unittest discover -s tests -v` (or `pytest`). The PNG test needs `qrcode` installed.

## Known limits
Demo seed data only; Kannada strings need native-speaker review; no login throttling yet.
