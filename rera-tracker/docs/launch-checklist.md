# Launch checklist

Items marked **you** need you or an account only you can open. Items marked
**built** are done in the code and tested.

## Built

- [x] **built** A public page for every project (`/p/<authority>/<id>`), generated from the stored data, with a sitemap.
- [x] **built** Sign-up form with a consent tick-box, double opt-in, and a stored record of what was agreed and when.
- [x] **built** A personal stop link in every message, plus the one-click unsubscribe button mail apps show. Stopping erases the person's data at once.
- [x] **built** An uptime page (`/health`) and an emailed problem report when the daily job could not read something.
- [x] **built** Both authorities' lists refreshed daily, so every page stays current even if nobody follows the project.

## Permission and law (you)

- [ ] **you** Send the permission request (`permission-request-haryana-rera.md`) and keep the reply. **The public pages reproduce HRERA's material, so do this before the site goes public.**
- [ ] **you** Set `RERA_TRACKER_CONTACT` to a real address you read, so the site's owners can reach you.
- [ ] **you** Have a lawyer read the privacy notice and consent text (`rera_tracker/web_text.py`). Things they will likely want added: what your host and email provider log and for how long; the name of your grievance contact; how a person can complain; any rule on children's data. The text is a first draft, not legal advice.
- [ ] **you** Have a Hindi speaker read every Hindi string in `web_text.py` and `messages.py`.
- [ ] **you** Decide the business form (individual, proprietorship, company), and whether GST applies at your turnover. Ask an accountant.
- [ ] **you** Write terms for the paid service: information only, not legal advice, no guarantee of completeness, refund rule.

## Accounts and hosting (you)

- [ ] **you** A server in India that stays on, with a disk, and a domain with https. `docs/deploy.md` is the step-by-step.
- [ ] **you** An email-sending service (any SMTP provider). Set the `RERA_TRACKER_SMTP_*` variables. Use a sending domain you own, and set SPF, DKIM and DMARC.
- [ ] **you** A payment-gateway account (for example Razorpay) for UPI or card payments with automatic renewal. This needs your business details and bank account.
- [ ] **you** Optional, for WhatsApp: a Meta Business account and approved message templates. Until it exists, the WhatsApp channel refuses to send.

## Still to build

1. **Payment and renewal.** Take the payment, then subscribe the person; stop sending when a subscription lapses. Needs your gateway account first.
2. **WhatsApp delivery.** Needs the Meta account above.
3. **A friendlier "which project is mine?" step**, for example search by flat or tower name, if early users struggle to find their project.
4. **Other states**, once one of them offers an open data route or a feed.

## Before the first paying customer

- [ ] Run for two weeks on 10 to 20 projects with friends as subscribers. Read every message the tracker sends. Fix wording that could be read as a judgement on a builder.
- [ ] Check each kind of message against the live site by hand at least once.
- [ ] Press every button on the site as a stranger would: sign up, confirm, receive, stop, delete. Check that nothing is left behind.
- [ ] Ask HRERA, or a lawyer, whether charging for these summaries is acceptable under the portal's terms.
