# BeautyFlow — How the new features work (test guide)

Use your vendor account (e.g. **beautyflow** at https://beautyflow.co.ke/restaurant/beautyflow/) and a second phone/browser as the "customer".
Vendor dashboard: https://beautyflow.co.ke/dashboard/

---

## 1. Two doors: QR menu vs public website

- **QR code (in the restaurant)** → `/m/<unguessable-link>/` → menu with **Add to order** → checkout with **Name** and **Waiter code** (both required) → the order lands on that waiter's dashboard. Only people who scanned the QR can reach this. The old `/restaurant/<name>/menu/` link now just redirects to the public page.
- **Public website** (beautyflow.co.ke) → vendor page → **Add to order** builds a selection → **Send inquiry** → name, phone, message, delivery area (with the vendor's fee shown) and address → lands in Dashboard → **Inquiries**. No order is created until the vendor promotes it.
- Dashboard → **QR code & link** shows the live QR link; **Link leaked? Create a new one** rotates it (every printed QR must then be reprinted).

## 1. Orders inbox

**Customer side**
1. Open the vendor page → tap **Add to order** on a few dishes (the "Your order" card in the sidebar fills up).
2. Tap **Checkout** → the checkout page opens: order summary (change quantities there), **name only** — no phone asked, *Collect* / *Dine in* / *Delivery*, note, "I want it later".
   *Delivery* (only if it's on in Dashboard → Delivery): pick your **area** from the vendor's list — the fee appears in the totals — type street/house/landmark, optionally tap **Use my exact location**. Minimum order and "free above" are enforced. You pay the rider on delivery.
3. Tap **Place order** → you land straight on the **tracking page**. Nothing opens WhatsApp by itself.
4. On the tracking page, **Message <business> on WhatsApp** asks for your WhatsApp number first, saves it to the order (so they can call you back), then hands you the pre-written message to send. Skip it and the order still goes through — the vendor sees it in their inbox either way.
5. The **Track order** page shows the status bar: Received → Preparing → Ready → Collected. It refreshes by itself. Once the vendor takes payment, a green **Paid** panel appears with **View receipt** and **Download receipt (PDF)**.

**Vendor side**
1. Dashboard → **Orders**. The sidebar shows a red badge with the number of new orders.
2. Each order card shows items, customer name/phone (WhatsApp + call links), source (Online / Pre-order), the scheduled time if any, and for deliveries the address with an **Open map** link.
3. Pick the **waiter** on the card (and the **table** if it is dine in) — an order can't move on until it's attached to someone. With no waiter accounts yet, the owner is set automatically.
4. Tap **Mark preparing → Mark ready → Mark collected** (deliveries: **Mark on the way → Mark delivered**). The card stays put and gets a red ring so you can see what you just changed — even under the Open filter it hangs around for 5 minutes. The list refreshes itself every 10 seconds.
5. Once an order is **served but not paid**, an orange "Waiting for payment" line appears on the card, the count shows at the top of the page, and the POS → Orders link in the sidebar carries an orange badge. Take the payment there.
4. Search by order number, name, phone or item; filter Open / Received / Completed etc.

*What to check:* order appears within seconds; tracking page updates when you change status.

---

## 0. What is free and what is paid

- **Free**: your listing, menu (up to the free item cap), **Inquiries** (bookings + quote requests), reviews, QR code, marketing kit.
- **Premium (monthly)**: unlimited menu items and photos, offers on the public Deals page, menu PDF without the watermark.
- **POS (monthly)**: the POS screen, Kitchen board, **Orders inbox**, **Delivery zones**, **Customers**, **Wallet**, Sales, Reports, Insights, Expenses, waiter accounts and Tables. Without it those pages show the upgrade screen.

## 1a. Staff roles: waiter, kitchen, cashier

POS → **Staff** (was Accounts) → **+ Add staff** → pick a role:

| Role | Logs in to | Sees | Can |
|---|---|---|---|
| **Waiter** | their own page | only orders attached to them (via their 5-digit code) | POS, mark their orders, set the table, take payment |
| **Kitchen** | `/pos/kitchen/` — a cooking screen | **every** order for the business, all waiters | **Start cooking → Ready** (and Undo). Nothing about money, no sales, no POS |
| **Cashier** | Orders & payments board | every order | take payments, sell at the counter, Sales, Reports (no profit & loss) |
| **Owner** | dashboard | everything | everything, incl. the kitchen screen and staff |

Kitchen screen: three columns — **New** (red, "Start cooking"), **Cooking** (orange, "Ready" / "Undo"), **Ready — waiting for the waiter** (green). Refreshes every 10 s and the moment anyone changes an order. Put it on a tablet in the kitchen. Kitchen and cashier accounts have no waiter code; each role's sidebar only shows what it needs, and any other POS page sends them back to their own screen.

## 1a-2. Tables & waiters

1. POS → **Accounts**: add waiters (each gets a **5-digit code**; **New code** issues a fresh one and kills the old immediately) and, at the bottom, **Tables** — type a name (Table 7, Garden 2) with optional seats, or **Quick add 10 tables**.
2. On the POS screen the order panel has a table dropdown; picking a table marks the order dine in.
3. A waiter signs in and lands on their own page: **My open orders** lists what is assigned to them with the same Mark buttons, a **Table** dropdown (they can seat the order themselves) and a **Take payment** link. It refreshes every 15 seconds, and a red badge on their Dashboard/Orders links counts orders not yet started.
4. The kitchen board has the same **Table** dropdown on every card. A waiter can only change their own orders — someone else's returns 404; the owner can change any.

*What to check:* an order assigned to a waiter shows on their page only; the owner sees all of them.

## 1b. Delivery zones (vendor)

1. Dashboard → **Delivery** → tick *Offer delivery*, set minimum order / free-above / typical time.
2. **Areas & fees**: the suburbs of your county are listed (Nairobi, Kiambu, Kajiado, Machakos, Mombasa, Kilifi, Kwale, Kisumu, Nakuru, Uasin Gishu, Nyeri, Meru). Search, tick an area, type your fee. Anything missing → **Add another area**. One **Save delivery**.
3. Your areas and fees then show in the **Delivery** card on your public page, in the checkout dropdown, and in the "Questions?" chat answers.

*What to check:* a ticked area with a fee appears at checkout; the fee is added to the total; orders under the minimum are refused; the order card in Orders shows the area, the fee and the grand total.

## 2. Customers + WhatsApp broadcast

1. Every order, reservation or inquiry adds the person to Dashboard → **Customers** (name, phone, orders, spend, last seen).
2. **WhatsApp** button per customer opens a chat.
3. Open **Send an offer to your customers** → edit the message → **Copy message**.
4. **Download CSV** → import the numbers to your phone contacts → WhatsApp Business → *New broadcast* → paste the message.

*What to check:* after placing an order as the customer, they appear in the list with the right total.

---

## 5. Pre-orders (order for later)

1. In checkout tick **Order for later** → choose date & time (must be in the future).
2. The order arrives in the inbox marked **Pre-order · for Mon 12 Sep 12:30** (orange).
3. Status flow is the same as normal orders.

*Not built:* a shared group-order link for offices.

---

## 6. Inquiries (menu inquiries, table bookings & quote requests)

**Menu inquiries** (from the public website) show at the top with the items, estimate, delivery area + fee and the message. Buttons: **Mark contacted**, **Promote to order** (pick the waiter, and if the customer already paid choose M-Pesa / cash / card and enter the code) → an order is created in Orders with the same items, address and fee, paid if you said so → **Close**. Tabs: Open / All. The sidebar badge counts new inquiries + bookings to confirm.



**Customer:** vendor page → **Send an inquiry** card → name, phone, date, time, people, note → **Send inquiry** → "Reservation requested".
**Vendor:** Dashboard → **Inquiries** (badge shows how many to confirm) → **Confirm** → the **Send confirmation** button opens a pre-written WhatsApp message to the customer. Then **Seated** or **Cancel**.
Switch off in Business profile → *Accept table reservations*. Quote requests from dishes marked **price on request** land here too, tagged *Quote request*.

*What to check:* the tab filters (Upcoming / To confirm / Confirmed / Seated / Cancelled) work.

---

## 7. Marketing kit

Dashboard → **Marketing kit** → download:
- **A4 menu poster** (2480×3508) — wall/door
- **WhatsApp status / IG story** (1080×1920) — uses your cover photo
- **Square social post** (1080×1080)

All include your logo, tagline, menu QR and "Powered by BeautyFlow". Add a tagline and cover photo in Business profile first.

---

## 9. Savings calculator

Open https://beautyflow.co.ke/for-business/list-your-restaurant/ → scroll to **"How much are you paying delivery apps?"** → move the two sliders (monthly sales, commission %) → see *Commission you pay* vs *BeautyFlow Premium* vs *You keep*.

---

## SMS notes
- One SMS only: the **welcome SMS** to a vendor after they verify their email (Advanta, shortcode **isoftke**). Customers are not sent SMS — they use the tracking page and WhatsApp.
- Best-effort: if Advanta is down nothing breaks — the action still completes, the SMS is just skipped and logged.

## Quick end-to-end test (5 minutes)
1. Phone A (customer): open the vendor page, add 2 items, checkout with your phone number, send on WhatsApp.
2. Laptop (vendor): Orders → mark Preparing → Ready → Collected.
3. Phone A: open Track link — shows Collected. Book a table for tomorrow.
4. Laptop: Inquiries → Confirm → Send confirmation (WhatsApp). Customers → phone A is listed.
