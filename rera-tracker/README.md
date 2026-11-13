# RERA tracker

Plain-language alerts for people waiting on a flat, built from the **public**
records of Haryana RERA (`haryanarera.gov.in`).

Every day the tracker re-reads the public pages of each project somebody
follows. When something changes it writes a short message, in English or Hindi,
that says what the public record now shows and links to the official page.
It states facts as filed. It never says a builder is "late", "safe" or a
"fraud".

## What is built, and what is not

| Part | State |
|---|---|
| Reader for the Haryana RERA list, project page, quarterly report list and quarterly report | Built, tested on the live site |
| Change detection (new quarterly report, registration extended / ending / passed, lapsed, completion certificate, status, hearings, missing report) | Built, 89 automated tests |
| English and Hindi messages | Built |
| Storage (SQLite), message queue, no duplicate sends, silent first-day baseline | Built |
| Delivery: `console`, `file`, `email` (SMTP) | Built |
| Delivery: WhatsApp | **Not built.** Needs a Meta Business account and approved message templates |
| Website where a buyer finds a project and signs up | **Not built** |
| Payments and automatic renewal | **Not built.** Needs a payment-gateway account (for example Razorpay) |
| Other states | **Not built.** See "Data sources" |

Until the last four rows exist, subscribers are added by hand with the
`subscribe` command. The engine does not depend on how they sign up.

## Quick start

Python 3.9 or newer. No third-party packages.

```bash
cd rera-tracker
python3 -m rera_tracker sync gurugram          # download the registered-projects list (1 request)
python3 -m rera_tracker stats                  # counts for the stored list
python3 -m rera_tracker find "eden"            # look a project up
python3 -m rera_tracker subscribe RERA-GRG-1817-2024 \
    --name "A Buyer" --channel email --address buyer@example.com --lang hi
python3 -m rera_tracker check                  # read tracked projects, queue messages
python3 -m rera_tracker send                   # deliver queued messages
python3 -m rera_tracker report RERA-GRG-1817-2024 --lang en    # one project, full status
```

The daily job is one command; run it once a day from cron on any machine with a disk:

```cron
17 6 * * *  cd /path/to/rera-tracker && python3 -m rera_tracker run >> tracker.log 2>&1
```

`run` re-downloads the list for each authority that has a tracked project,
checks every tracked project, and sends what is queued.

### Settings (environment variables)

| Variable | Meaning |
|---|---|
| `RERA_TRACKER_DB` | SQLite file (default `rera_tracker.db`) |
| `RERA_TRACKER_CONTACT` | Contact address placed in the User-Agent so the site's owners can reach you. **Set this before running for real** |
| `RERA_TRACKER_DELAY` | Seconds between requests (default 5) |
| `RERA_TRACKER_MAX_REQUESTS` | Hard cap on requests per run (default 500) |
| `RERA_TRACKER_CA_BUNDLE` | Extra CA file, if your machine does not trust the site's certificate chain |
| `RERA_TRACKER_SMTP_HOST`, `_PORT`, `_FROM`, `_USER`, `_PASSWORD` | Email delivery (STARTTLS) |

### Checking the work

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -t .
```

The tests use invented pages that copy the real site's layout. No page from the
real site is stored in this repository.

## How it behaves

* **Polite.** One request at a time, a pause between requests, an identifying
  User-Agent, a cap on requests per run, and only `https://haryanarera.gov.in`
  URLs. A tracked project costs two or three requests a day, and one more on
  the day a new quarterly report appears.
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

## Data sources: what was checked

Checked on 11–13 November 2026.

| Source | Result |
|---|---|
| Haryana RERA (Panchkula and Gurugram) | Open. The project list, project pages, quarterly report list and each quarterly report load without login or captcha. About 2,200 projects |
| Maharashtra (`maharerait.maharashtra.gov.in`) | Project details sit behind a captcha. Not used. Ask MahaRERA for an official data feed or written permission instead |
| Maharashtra main site, national portal (`rera.mohua.gov.in`) | Refused every connection from the cloud machine used for this work. Untested; may work from an Indian connection |
| Uttar Pradesh (`up-rera.in`) | Its server does not send its intermediate certificate, so the cloud machine could not verify it. Untested |

## Before you charge anyone

Read `docs/launch-checklist.md`. The short version:

1. Haryana RERA's Terms of Use say material "may be reproduced after taking
   proper permission by sending a mail" to the site's web information manager.
   Send that email first. A draft is in `docs/permission-request-haryana-rera.md`.
2. Subscribers' phone numbers and email addresses are personal data under the
   Digital Personal Data Protection Act, 2023. You need a clear consent
   screen, a privacy notice and a way to delete a person's data.
3. This is information, not legal advice. Every message says so and links to
   the official page. Keep it that way.

## Code map

| File | Job |
|---|---|
| `rera_tracker/tables.py` | Reads HTML tables, links, pop-up links and forms |
| `rera_tracker/haryana.py` | Understands the Haryana pages |
| `rera_tracker/fetch.py` | The polite HTTP client |
| `rera_tracker/detect.py` | Compares two snapshots of a project and lists the events |
| `rera_tracker/messages.py` | English and Hindi text |
| `rera_tracker/store.py` | SQLite tables |
| `rera_tracker/tracker.py` | Ties the pieces together |
| `rera_tracker/notify.py` | Delivery channels |
| `rera_tracker/cli.py` | The commands |
