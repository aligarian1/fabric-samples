# RERA tracker

Plain-language alerts for people waiting on a flat, built from the **public**
records of Haryana RERA (`haryanarera.gov.in`).

Every day the tracker re-reads the public pages of each project somebody
follows. When something changes it writes a short message, in English or Hindi,
that says what the public record now shows and links to the official page.
It states facts as filed. It never says a builder is "late", "safe" or a
"fraud".

A small website lets a buyer search for their project, read its record, and
sign up for alerts by email.

## What is built, and what is not

| Part | State |
|---|---|
| Reader for the Haryana RERA list, project page, quarterly report list and quarterly report | Built, tested on the live site |
| Change detection (new quarterly report, registration extended / ending / passed, lapsed, completion certificate, status, hearings, missing report) | Built, tested |
| English and Hindi messages | Built (Hindi should be read by a Hindi speaker) |
| Storage (SQLite), message queue, no duplicate sends, silent first-day baseline | Built |
| Delivery: `console`, `file`, `email` (SMTP) | Built |
| Website: search, a public page per project, English and Hindi | Built, checked in a real browser on desktop and phone |
| Email sign-up with double opt-in and a consent record | Built |
| A personal "stop alerts / delete my data" link in every message, plus the one-click button mail apps show | Built |
| Daily job that syncs both lists, checks followed projects, sends, cleans up, and emails you a problem report | Built |
| `/health` page for an uptime monitor (goes red if the daily job stops) | Built |
| Delivery: WhatsApp | **Not built.** Needs a Meta Business account and approved message templates |
| Payments and automatic renewal | **Not built.** Needs a payment-gateway account (for example Razorpay) |
| Other states | **Not built.** See "Data sources" |

Nothing here has been published. Read "Before you publish or charge" first.

## Quick start

Python 3.9 or newer (tested on 3.11, 3.12 and 3.13). No third-party packages are needed to run or test it.

```bash
cd rera-tracker
python3 -m rera_tracker sync all               # download both registered-projects lists (2 requests)
python3 -m rera_tracker stats                  # counts for the stored list
python3 -m rera_tracker find "eden"            # look a project up
python3 -m rera_tracker subscribe RERA-GRG-1817-2024 \
    --name "A Buyer" --channel email --address buyer@example.com --lang hi
python3 -m rera_tracker check                  # read followed projects, queue messages
python3 -m rera_tracker send                   # deliver queued messages
python3 -m rera_tracker report RERA-GRG-1817-2024 --lang en    # one project, full status
python3 -m rera_tracker serve --dev            # the website, on http://127.0.0.1:8080
```

`serve --dev` fills in harmless settings and **prints confirmation emails to
the terminal** instead of sending them, so you can try the whole sign-up
journey on your own computer.

The daily job is one command; run it once a day on any machine with a disk:

```cron
17 6 * * *  cd /path/to/rera-tracker && python3 -m rera_tracker run >> tracker.log 2>&1
```

`run` re-downloads both lists, checks every followed project, sends what is
queued, deletes sign-up requests that were never confirmed, and records how it
went. If something could not be read and `RERA_TRACKER_ADMIN_EMAIL` is set, it
emails you a short problem report. For real hosting see `docs/deploy.md`.

### Settings (environment variables)

| Variable | Meaning |
|---|---|
| `RERA_TRACKER_DB` | SQLite file (default `rera_tracker.db`) |
| `RERA_TRACKER_CONTACT` | Contact address placed in the User-Agent so the site's owners can reach you. **Set this before running for real** |
| `RERA_TRACKER_DELAY` | Seconds between requests (default 5) |
| `RERA_TRACKER_MAX_REQUESTS` | Hard cap on requests per run (default 500; the lists cost 2, each followed project about 2 a day) |
| `RERA_TRACKER_CA_BUNDLE` | Extra CA file, if your machine does not trust the site's certificate chain |
| `RERA_TRACKER_SMTP_HOST`, `_PORT`, `_FROM`, `_USER`, `_PASSWORD` | Email delivery (STARTTLS) |
| `RERA_TRACKER_ADMIN_EMAIL` | Where the daily problem report goes |
| **Website** | |
| `RERA_TRACKER_SECRET` | Long random value (16+ characters) that signs links and forms. Keep it private. Changing it breaks links already sent |
| `RERA_TRACKER_BASE_URL` | The public `https://` address of the site. Used in every link in every email |
| `RERA_TRACKER_BUSINESS_NAME`, `RERA_TRACKER_CONTACT_EMAIL` | Printed in the consent text and the privacy notice. The site will not start without them |
| `RERA_TRACKER_TRUST_PROXY` | Set to `1` only behind a reverse proxy that overwrites `X-Forwarded-For` |

Alert emails get the personal stop link only when `RERA_TRACKER_BASE_URL` and
`RERA_TRACKER_SECRET` are set, for the daily job as well as the website.

### Checking the work

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -t .
```

The tests use invented pages that copy the real site's layout. No page from the
real site is stored in this repository.

## The website

| Page | What it does |
|---|---|
| `/` | Search box, one paragraph on what the service does, how many projects it covers |
| `/search?q=` | Up to 25 matches by project name, builder, place or RERA ID |
| `/p/<authority>/<project id>` | The public page for one project: the record in plain language, the date it was read, a link to the official page, and the sign-up form |
| `/privacy` | The privacy notice (English and Hindi) |
| `/confirm`, `/unsubscribe` | Reached only from links in emails. A plain visit shows a button; nothing changes until the button is pressed |
| `/health` | JSON for an uptime monitor. Returns 503 if the daily job has not run for 36 hours |
| `/sitemap.xml`, `/robots.txt` | For search engines |

How sign-up works: the visitor gives an email address, picks a language and
ticks a consent box. They get one email with a confirmation link. Only after
they press the confirm button are they subscribed. Their first status report
arrives with the next daily run, then an email only when something changes.
Every email has a personal link that stops that project's alerts, or stops
everything and **erases the person's data at once**.

What the site collects: the email address, the language, the project followed,
and the date and time of consent with the version of the privacy notice. No
name, no phone number, no cookies, no JavaScript.

Abuse protection: a signed form token with a minimum and maximum age, a hidden
trap field for bots, at most three confirmation emails per address per day,
at most 20 sign-ups per visitor per hour, and the same neutral answer whether
or not an address is already subscribed.

## How the tracker behaves

* **Polite.** One request at a time, a pause between requests, an identifying
  User-Agent, a cap on requests per run, and only `https://haryanarera.gov.in`
  URLs.
* **No captcha, no login.** It reads only pages the site links openly from its
  own menus. The site's "search by registration number" form has a captcha;
  the tracker never touches it and does not try to get around it.
* **An outage is never news.** If a page cannot be read or its layout has
  changed, the old state is kept, nothing is announced, and the problem is
  printed. A page that could not be read earlier and is read for the first
  time later is not announced as if it had just changed.
* **Quiet first day.** A new subscriber gets one status report. Warnings that
  are already true that day (for example "registration ends in 40 days") are
  remembered, not announced as news.
* **Each message is sent once.** Events have a stable key, and the outbox has a
  unique key per subscriber and event.
* **Dates are India dates.** "Days left" and "report overdue" use India time,
  so they do not shift on a server that runs on UTC.

## Data sources: what was checked

Checked on 11–13 November 2026.

| Source | Result |
|---|---|
| Haryana RERA (Panchkula and Gurugram) | Open. The project list, project pages, quarterly report list and each quarterly report load without login or captcha. About 2,200 projects |
| Maharashtra (`maharerait.maharashtra.gov.in`) | Project details sit behind a captcha. Not used. Ask MahaRERA for an official data feed or written permission instead |
| Maharashtra main site, national portal (`rera.mohua.gov.in`) | Refused every connection from the cloud machine used for this work. Untested; may work from an Indian connection |
| Uttar Pradesh (`up-rera.in`) | Its server does not send its intermediate certificate, so the cloud machine could not verify it. Untested |

## Before you publish or charge

Read `docs/launch-checklist.md`. The short version:

1. **Permission.** Haryana RERA's Terms of Use say material "may be reproduced
   after taking proper permission by sending a mail" to the site's web
   information manager. The public project pages reproduce that material.
   Send the email first. A draft is in `docs/permission-request-haryana-rera.md`.
2. **Personal data.** Email addresses are personal data under the Digital
   Personal Data Protection Act, 2023. The consent box and the privacy notice
   in `rera_tracker/web_text.py` are a careful first draft, **not legal advice**.
   Have a lawyer read them, fill in what your host and email provider log, and
   have a Hindi speaker read the Hindi.
3. **Information, not advice.** Every page and message says so and links to the
   official page. Keep it that way.

## Code map

| File | Job |
|---|---|
| `rera_tracker/tables.py` | Reads HTML tables, links, pop-up links and forms |
| `rera_tracker/haryana.py` | Understands the Haryana pages |
| `rera_tracker/fetch.py` | The polite HTTP client |
| `rera_tracker/detect.py` | Compares two snapshots of a project and lists the events |
| `rera_tracker/messages.py` | English and Hindi text of messages and status reports |
| `rera_tracker/store.py` | SQLite tables, sign-ups, erasure |
| `rera_tracker/tracker.py` | Ties the pieces together |
| `rera_tracker/notify.py` | Delivery channels |
| `rera_tracker/web.py`, `web_text.py` | The website and its wording |
| `rera_tracker/tokens.py` | Signed links and form tokens |
| `rera_tracker/clock.py` | India dates |
| `rera_tracker/cli.py` | The commands |
