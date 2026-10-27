# Architecture & Database Design

## Layers
- `app.py` – Streamlit routing/UI only. `canteen/routing.py` picks the surface: **a `?t=<token>` customer QR always wins**, so no table QR can open admin.
- `canteen/db.py` – storage + business rules (SQLite now; schema is portable to PostgreSQL). Money = integer paise. Every query takes `business_id`.
- `canteen/auth.py` – scrypt password hashing, roles (`admin`, `staff`), permission checks.
- `canteen/qr.py`, `i18n.py`, `ui.py`, `seed.py` – QR/PNG/ZIP, EN/KN strings, mobile CSS + escaped HTML cards, demo data.
- Planned: `orders.py`, `payments/` (provider interface + demo + UPI gateway adapter), `notifications.py`, `reports.py`.

## Multi-business
Every domain table carries `business_id`; business config (name, Kannada name, WhatsApp, theme) lives in `businesses`. A QR token resolves to exactly one business. Staff sessions are bound to their own `business_id`.

## Tables
| Phase | Table | Key columns |
|---|---|---|
| 1 ✅ | businesses | slug, name, name_kn, whatsapp, theme_color, active |
| 1 ✅ | users | business_id, username, pw_hash, role, active |
| 1 ✅ | categories / menu_items | name(+_kn), price_paise, veg, available, prep_minutes |
| 1 ✅ | dining_tables | business_id, label (unique per business) |
| 1 ✅ | qr_codes | kind (menu/table/counter), table_id, token (unique, revocable) |
| 2 | orders | public_id (random, unique), idempotency_key (unique), channel, table_id, status, total_paise, scheduled_for |
| 2 | order_items | order_id, item_id, name snapshot, unit_price_paise, qty, note |
| 2 | order_events | order_id, status, at, actor (audit trail) |
| 3 | settings | prep-time rules, pickup slots, capacity |
| 4 | payments | order_id, provider, provider_ref (unique), amount_paise, status, verified_at |
| 4 | notifications | business_id, kind, order_id, read_at |
| 5 | offers, loyalty_ledger, customers, feedback | |

## Security decisions (Phase 1)
- QR tokens: 96-bit random, revocable, customer scope only; `resolve_token` returns no user/role data.
- Prices/availability are always read from the DB; Phase 2 will recompute totals server-side.
- Customer-facing HTML is escaped; passwords hashed with scrypt; no payment data stored.
- **Not yet done:** login rate limiting, session expiry, HTTPS/deployment hardening (Phase 6).
