# BeautyFlow → food delivery: the plan

Short answer to both questions:

1. **Yes, the simplest version is exactly that** — each vendor switches on delivery, sets their own rates by zone, and delivers with their own riders. BeautyFlow never runs a fleet.
2. **Yes, IntaSend supports B2C payouts.** Its "Send Money" API pays out to M-Pesa numbers (B2C), bank accounts and IntaSend wallets, and its **Wallets API** lets us keep a separate wallet per vendor so the customer's money is held by a licensed PSP, not by us. That is the whole payments architecture.

Everything below assumes we keep what works today (menu → WhatsApp) and add delivery as a third fulfilment option next to *Collect* and *Dine in*.

---

## 1. What changes for each side

| | Today | With delivery |
|---|---|---|
| **Customer** | Adds items → places order → sends on WhatsApp → pays at the counter | Chooses *Delivery* → drops a pin / picks an area → sees delivery fee → **pays by M-Pesa on the spot** → tracks Received → Preparing → Out for delivery → Delivered |
| **Vendor** | Orders inbox, marks statuses | Switches delivery on, sets zones and fees, gets **paid orders only**, assigns a rider (name + phone), marks *Out for delivery* → *Delivered*; money lands in their IntaSend wallet and they withdraw to M-Pesa / bank |
| **BeautyFlow** | Subscription income | Subscription **plus 5% of the food value** of each paid online order, deducted automatically before payout ("you keep 95%") |

We do **not** build rider matching, live GPS tracking or a rider app in phase 1. That is what killed most Kenyan delivery start-ups; vendors already have a boda guy.

---

## 2. Vendor delivery settings (dashboard → "Delivery")

- **Delivery on/off** (replaces the current "Offers delivery" tick box).
- **Zones** — a simple table the vendor fills in, no maps API needed:

  | Zone | Fee | Min. order | Est. time |
  |---|---|---|---|
  | Within 2 km | KES 100 | KES 300 | 30 min |
  | 2–5 km | KES 200 | KES 500 | 45 min |
  | 5–8 km | KES 350 | KES 800 | 60 min |

  Distance is computed with a plain haversine formula between the vendor's pin and the customer's pin (browser geolocation or a tap on a map tile) — **no paid Google Distance API**. Vendors who prefer it can instead list **named areas** ("Ruaka KES 100, Banana KES 200, Runda KES 250") and the customer picks from a dropdown.
- **Free delivery above KES X** (optional).
- **Delivery hours** (default: same as opening hours).
- **Payout details**: M-Pesa number or bank account (used for withdrawals), and the vendor's KYC bits IntaSend requires for a wallet.

The vendor keeps 100% of the delivery fee; it's their rider.

---

## 3. Customer checkout flow

1. Menu → *Add to order* (unchanged).
2. Checkout → fulfilment: **Collect / Dine in / Delivery**.
3. Delivery: name, phone, **location** (use my location → pin, or pick area), landmark / house note.
4. Fee shown live: *Delivery KES 200 · Total KES 1,450*. If outside every zone: "Sorry, we don't deliver there yet — collect instead?"
5. **Pay now (M-Pesa)** → STK push to the phone (same `stk_push` we already use for subscriptions) → wait for callback → order becomes *Paid* and appears in the vendor's inbox with a sound.
6. Tracking page (already exists) gains *Out for delivery* (with rider name + phone → tap to call) and *Delivered*.
7. Status shown on the tracking page; WhatsApp status pings (Cloud API, ~KES 1 each) are a phase-2 option — no SMS to customers.

Unpaid delivery orders are **never** sent to the kitchen. This removes the "order and disappear" problem that makes vendors hate delivery.

---

## 4. Money flow with IntaSend

```
Customer phone ──STK──► BeautyFlow IntaSend account
                              │  (webhook: order paid)
                              ▼
                    Wallet transfer (API, instant)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  Vendor wallet         BeautyFlow fee            (rider is paid
  95% food + 100%       5% of food             by the vendor)
  delivery fee
        │
        ▼  vendor taps "Withdraw" (or auto daily)
  M-Pesa B2C / bank payout ── IntaSend "Send Money"
```

**Why wallets and not "pay us, we pay them later":** with per-vendor wallets the vendor's money is legally theirs inside a regulated PSP from the moment of payment; we only move the fee. That keeps BeautyFlow out of "holding client funds" territory and makes reconciliation trivial (one wallet = one vendor).

**IntaSend pieces we need** (all REST, same API key we already hold):

| Need | IntaSend feature | Notes |
|---|---|---|
| Customer pays | Collections — M-Pesa STK, card | Already integrated (`payments/intasend.py`) |
| Per-vendor balance | **Wallets API** (`/wallets/`) | Create one *working* wallet per vendor at onboarding |
| Move money into vendor wallet | Wallet-to-wallet transfer / or collect *directly* into the vendor wallet with `wallet_id` on the STK request, then transfer our fee out | Second option = one API call per order |
| Vendor withdraws | **Send Money / Payouts** — M-Pesa B2C, bank (Pesalink), IntaSend wallet | Needs the "Send Money" approval on our IntaSend account (business KYC) |
| Refund a cancelled order | Payout back to customer's M-Pesa from the vendor wallet | Rules in §6 |
| Statement | Wallet transactions endpoint | Feeds the vendor's "Wallet" page and our P&L |

**IntaSend fees (intasend.com/pricing, checked Sept 2026 — re-check before launch):** M-Pesa collections **3%**, local cards 3.5%, international cards 4.5%; M-Pesa payout **flat KES 100** per transfer; no setup or monthly fee; bank payout and wallet fees not listed — confirm with IntaSend when applying for Send Money.

### Pricing — "You keep 95%"

Decided: **BeautyFlow takes 5% of the food value of every paid online order; the vendor keeps 95%.** The delivery charge the vendor sets is passed through 100% — it is their rider's money.

Per KES 1,000 order (IntaSend fees from intasend.com/pricing, Sept 2026: M-Pesa collection 3%, M-Pesa payout flat KES 100):

| | KES |
|---|---|
| Customer pays | 1,000 (+ delivery fee, untouched) |
| Vendor's wallet receives | **950** |
| IntaSend collection (3%) | 30 — paid out of BeautyFlow's 5% |
| BeautyFlow nets | **20** (2%) |
| Withdrawal to M-Pesa | KES 100 per payout, paid by the vendor; auto-batched daily with a KES 2,000 minimum so it's a few shillings per order |

Vendor-facing copy: *"Online orders: you keep 95% of every order and 100% of your delivery charge. No monthly fee. Withdraw to M-Pesa any time — KES 100 per withdrawal, batched daily."*

Later lever, without touching the vendor's 95%: show the 3% M-Pesa fee to the customer as a checkout line (BeautyFlow then nets the full 5%). Compare Glovo / Uber Eats at 20–30%.

---

## 5. Data model changes (small)

- `Vendor`: `delivery_enabled`, `lat`, `lng`, `free_delivery_over`, `wallet_id`, `payout_msisdn`, `payout_bank_*`, `kyc_status`.
- `DeliveryZone` (vendor, label, max_km *or* area name, fee, min_order, eta_minutes).
- `Order`: `Fulfilment.DELIVERY`, `delivery_fee`, `address`, `lat`, `lng`, `rider_name`, `rider_phone`, statuses `OUT_FOR_DELIVERY`, `DELIVERED`; `payment_status` paid/unpaid/refunded, `intasend_invoice_id`.
- `Payment.product` gains `"order"` so the existing webhook, reconciler and receipts cover order payments too.
- `Payout` (vendor, amount, msisdn/bank, intasend_tracking_id, status).

Everything else (customers, orders inbox, tracking page, SMS, POS board) is reused.

---

## 6. Cancellations, refunds, disputes

- Vendor cancels before *Preparing* → automatic full refund to the customer's M-Pesa from the vendor wallet (API payout); BeautyFlow fee not charged.
- Vendor cancels after *Preparing* → refund is the vendor's call in the dashboard; we log it.
- Customer no-show / wrong address → vendor keeps the money; that is the point of pay-first.
- Every refund/payout is written to the audit log that already exists in the admin panel.

---

## 7. Roll-out phases

**Phase 1 — Pay-first delivery, vendor's own riders (4–6 weeks)**
Delivery settings + zones, checkout with fee + M-Pesa STK, paid-only inbox, statuses, wallet per vendor, manual "Withdraw" button. Launch with 5–10 vendors in one area (Ruaka / Westlands) who already deliver.

**Phase 2 — Money ops (2–3 weeks)**
Auto daily payouts, wallet statements in the dashboard, refunds from the inbox, admin reconciliation screen, fee invoicing.

**Phase 3 — Discovery (2 weeks)**
"Delivers to you" filter on directory pages using the customer's location, "Order delivery" badge on cards, a `/delivery/<area>/` SEO page per area.

**Phase 4 — only if vendors ask: shared riders**
A rider pool per area that vendors can request from the inbox. Rider accounts reuse the *waiter* role. Still no GPS tracking — rider's phone number is the tracking.

---

## 8. Risks and how we handle them

| Risk | Answer |
|---|---|
| IntaSend refuses Send Money / wallets for our account | Apply now with the business docs; fallback is settling vendors from our own IntaSend balance by daily B2C batches (works, less clean). |
| Holding customer money = CBK licensing | Wallets keep funds inside IntaSend (licensed). We never touch cash; we only instruct transfers. Get a short legal opinion before launch anyway. |
| Vendor doesn't deliver after being paid | Refund from their wallet + strike system in admin; three strikes → delivery switched off. |
| Chargebacks on cards | M-Pesa only in phase 1. |
| Delivery quality / cold food | Not our rider, not our promise — the page says "Delivered by the restaurant". |
| Rider cost makes small orders unprofitable | Min. order per zone is set by the vendor. |

---

## 9. Open questions before building

1. ~~Fee model~~ — decided: 5% of food value, delivery charge passed through.
2. Does IntaSend approve our account for **wallets + Send Money** — apply this week, it gates everything.
3. Do we allow card payments for delivery at all in phase 1?
4. Auto-payout daily, or vendor-triggered withdrawal? (Recommend daily auto with a manual button too.)
5. Which pilot area and which 5 vendors?

Answer these and phase 1 can start immediately; nothing in it needs a paid third-party API beyond the IntaSend fees already listed.
