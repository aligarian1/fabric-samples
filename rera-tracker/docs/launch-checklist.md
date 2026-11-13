# Launch checklist

Nothing below is done by the code. Each item needs you or an account only you can open.

## Permission and law

- [ ] Send the permission request (`permission-request-haryana-rera.md`) and keep the reply.
- [ ] Set `RERA_TRACKER_CONTACT` to a real address you read, so the site's owners can reach you.
- [ ] Decide the business form (individual, proprietorship, company), and whether GST applies at your turnover. Ask an accountant.
- [ ] Write a privacy notice and a consent screen (DPDP Act, 2023): what you collect (name, phone or email, the project followed), why, how long you keep it, and how a person can ask you to delete it. Build the delete path.
- [ ] Write terms for the paid service: information only, not legal advice, no guarantee of completeness, refund rule.

## Accounts

- [ ] A server or small VPS in India that stays on, with a disk for the SQLite file, and a daily backup of that file.
- [ ] An email-sending service (any SMTP provider). Set the `RERA_TRACKER_SMTP_*` variables. Use a sending domain you own, and set SPF and DKIM.
- [ ] A payment gateway account (for example Razorpay) for UPI or card payments with automatic renewal. This needs your business details and bank account.
- [ ] Optional, for WhatsApp: a Meta Business account and approved message templates. Until it exists, the WhatsApp channel refuses to send.

## Still to build (in this order)

1. A public page for each project (`/p/RERA-GRG-1817-2024`) generated from the stored data, so a buyer searching the project's name can find it. No sign-up needed to read it.
2. A sign-up form on that page: name, email or phone, language, consent tick-box.
3. Payment and renewal: take the payment, then call `subscribe`; stop sending when a subscription lapses.
4. A one-click unsubscribe link in every message.
5. A small dashboard for you: projects tracked, messages sent today, failures, pages that could not be read.
6. Alerts to you when a page layout changes (the tracker prints "could not read" lines; send them to your own email).

## Before the first paying customer

- [ ] Run for two weeks on 10 to 20 projects with friends as subscribers. Read every message the tracker sends. Fix wording that could be read as a judgement on a builder.
- [ ] Check each kind of message against the live site by hand at least once.
- [ ] Ask HRERA, or a lawyer, whether charging for these summaries is acceptable under the portal's terms.
