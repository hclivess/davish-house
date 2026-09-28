# Davish's House — apartments with hourly precision

An apartments-only marketplace in the spirit of Airbnb / Booking.com, but priced and booked **by the hour**: a shower between flights, a quiet afternoon to work, a place to rest before a late train.

## Production (this server)

Live at **http://208.87.242.141**. Brand name and default language come from `DAVISH_SITE_NAME` / `DAVISH_DEFAULT_LANG` in the env file. Runs as the `hourly` systemd service from `/srv/davish`, database in `/var/lib/davish/davish.db`, config in `/etc/davish/env`, nginx site `/etc/nginx/sites-enabled/davish.conf`.

```bash
deploy/deploy.sh                 # redeploy after code changes
systemctl status davish          # service
journalctl -u davish -f          # logs (password-reset emails land here until SMTP is set)
```

**Enable HTTPS** once a domain points at this IP (DNS-only / grey cloud if using Cloudflare):
1. Add the domain to `server_name` in `/etc/nginx/sites-available/davish.conf`, `nginx -t && systemctl reload nginx`.
2. `certbot --nginx -d yourdomain.com`
3. Set `DAVISH_BASE_URL=https://yourdomain.com` in `/etc/davish/env`, `systemctl restart davish` (turns on secure cookies).

**Enable email** (booking notifications, password resets, welcome mail): fill the `SMTP_*` values in `/etc/davish/env` and restart.

**Enable Stripe payments**
1. In the Stripe dashboard copy the secret key (`sk_live_…` or `sk_test_…`) into `STRIPE_SECRET_KEY` in `/etc/davish/env`.
2. Developers → Webhooks → add endpoint `http://208.87.242.141/stripe/webhook` (or your https domain) with events `checkout.session.completed`, `checkout.session.expired`, `charge.refunded`, `charge.dispute.created`; copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
3. `systemctl restart davish`. Until the key is set the site runs in simulated-payment mode and says so on every booking page.

How money moves: instant-book listings are charged when Stripe Checkout completes. Request-to-book listings only authorize the card; the charge is captured when the host accepts and released when they decline. The slot is held for 30 minutes while the guest pays, then released. Cancellations 24h+ before start (or by the host) refund in full through Stripe. Payments land in the platform's Stripe account; host payouts are tracked per booking (`host_payout_cents`) and paid out manually until Stripe Connect is added.

**Languages**: English and Spanish. The switch is in the header (`?lang=es` sets a one-year cookie); first visit follows the browser's Accept-Language. Strings live in `app/i18n.py`; add a language by adding a dict there.

## Run it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py          # optional demo data for local development only
.venv/bin/python -m uvicorn app.main:app --reload
```

Then open http://localhost:8000. `./run.sh` does the same in one step. API docs live at `/docs`.

Tests: `.venv/bin/python -m pytest`.

## What's in it

**The model: hourly precision, any length of stay.** A stay is a check-in and a check-out, each to the hour, on any dates: two hours this afternoon or two weeks starting Friday at 19:00. Availability is continuous; hosts shape it with check-in/check-out hour windows, blocked time, cleaning buffers, advance notice and a booking window.

**Guests**
- Search by city, check-in and check-out (date + hour), guests, size, price range, amenities, instant book; sort by price, rating or newest. Only apartments free for the whole stay are shown.
- Listing page: photo gallery, host profile, stay details, house rules, amenities, a 62-day availability/price strip, category ratings, reviews with host replies, and a check-in/check-out picker with a live itemised quote.
- Instant booking or request-to-book. Trips page, cancellation under the listing's policy (flexible / moderate / strict with partial refunds), messaging with the host, category reviews after a completed stay, saved favourites, public profiles.

**Hosts**
- Dashboard with earnings, hours booked and pending requests; accept/decline requests; review guests.
- Listing editor: bedrooms, bathrooms, beds, size, floor, description, address and check-in instructions (private until booked), house rules, amenities, photos (uploaded, resized, cover selection), timezone.
- Pricing: hourly rate, optional daily rate (applied automatically per 24h when cheaper), Friday/Saturday rate, long-stay discount, cleaning fee.
- Availability rules: min/max stay, check-in and check-out hour windows, cleaning buffer, advance notice, booking window, cancellation policy, instant book.
- **Calendar & pricing page**: month grid showing each day's state (free / partially booked / full), the hourly rate that applies that day, bookings and blocks; price rules for date ranges optionally limited to weekdays and hours of the day (nights, weekends, high season); blocked time.

**Accounts**: sign up, log in, password reset by email, account page (name, email, phone, bio, avatar, password), delete account. PBKDF2 hashing, signed HttpOnly cookies, nginx rate limits on auth endpoints, suspended accounts blocked at login.

**Admin** (`python manage.py make-admin EMAIL`): overview (users, listings, bookings, gross and platform revenue), user search + suspend/reinstate, listing pause/activate, booking cancel with refund.

**Payments**: Stripe Checkout; authorise-then-capture for requests; refunds per policy; webhooks; 30-minute payment hold on the slot. Simulated mode until keys are set.

**Notifications**: email on booking confirmed / requested / accepted / declined / cancelled and on new messages (host and guest), password reset, welcome. Logged to the journal until SMTP is configured.

**Languages**: Spanish (default) and English, switchable in the header; every string, message and email is translated (enforced by a test).

**Pricing engine** (`app/pricing.py`): each hour priced by the newest matching rule → weekend rate → base rate; full 24h blocks capped at the daily rate in force; long-stay discount from 7 days; 12% guest fee, 3% host fee.

## Stack

FastAPI + SQLite (stdlib `sqlite3`, WAL mode) + Jinja2 templates + one vanilla JS file. No build step. Passwords are PBKDF2‑hashed; sessions are signed cookies.

## Layout

```
app/
  main.py          app factory, error handling
  db.py            schema + connection helpers
  auth.py          password hashing, session cookies
  availability.py  slots, opening hours, conflict detection
  bookings.py      create / accept / decline / cancel / complete
  pricing.py       quotes and fees
  payments.py      Stripe Checkout / capture / refund / webhooks
  i18n.py          English + Spanish catalog
  queries.py       read models for pages and API
  routes/api.py    JSON API   (/api/…)
  routes/pages.py  HTML pages
  templates/, static/
seed.py            demo data
tests/             availability rules, booking lifecycle, HTTP flows
```

## Not yet real (next steps)

- **Stripe Connect** for automatic host payouts (today the platform account collects and hosts are paid manually).
- **Email verification / ID verification** and **maps / geosearch** are not built yet.
- **Stripe Connect** for automatic host payouts.
- **Photos** are stored on local disk under `/var/lib/davish/uploads`; move to S3 when you scale to several servers.
- **Maps / geosearch**: `lat`/`lng` columns exist but search is by city/neighborhood text.
- **Email / push notifications** for requests, confirmations and reminders.
- Swap SQLite for Postgres via the same SQL when you need multiple app servers.
