# Putting the tracker on a server

This is a recipe for one small Linux server (any provider with a data centre in
India). Everything except step 3's `gunicorn` uses the standard library. The
production command in step 4 was run and checked with two workers.

Do **not** put the site on the internet until you have read the "Before you
publish or charge" section of the README.

## 1. The machine

* Ubuntu 22.04 or newer, Python 3.9 or newer (the tests were run on 3.11, 3.12 and 3.13), 1 GB of memory is enough.
* A domain name pointing at it, and an https certificate (certbot with nginx is
  the usual way). The settings below refuse a non-https address, except on
  `127.0.0.1`.

## 2. Code and settings

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin rera
sudo -u rera git clone <your repository> /home/rera/app      # or unzip the folder there
sudo -u rera mkdir -p /home/rera/data
```

Put the settings in `/etc/rera-tracker.env`, readable only by root and the
service user (`chmod 640`, `chown root:rera`). One `NAME=value` per line:

```
RERA_TRACKER_DB=/home/rera/data/rera_tracker.db
RERA_TRACKER_SECRET=<output of: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
RERA_TRACKER_BASE_URL=https://your-domain.example
RERA_TRACKER_BUSINESS_NAME=Your Business Name
RERA_TRACKER_CONTACT_EMAIL=help@your-domain.example
RERA_TRACKER_CONTACT=help@your-domain.example
RERA_TRACKER_ADMIN_EMAIL=you@your-domain.example
RERA_TRACKER_SMTP_HOST=smtp.your-provider.example
RERA_TRACKER_SMTP_PORT=587
RERA_TRACKER_SMTP_FROM=alerts@your-domain.example
RERA_TRACKER_SMTP_USER=...
RERA_TRACKER_SMTP_PASSWORD=...
RERA_TRACKER_TRUST_PROXY=1
```

Never commit this file. If you ever change `RERA_TRACKER_SECRET`, every link
already emailed stops working.

For email to reach inboxes, set up SPF, DKIM and DMARC for the sending domain at
your email provider.

## 3. Python environment

```bash
sudo -u rera python3 -m venv /home/rera/venv
sudo -u rera /home/rera/venv/bin/pip install gunicorn
```

## 4. The website

`/etc/systemd/system/rera-web.service`:

```ini
[Unit]
Description=RERA tracker website
After=network.target

[Service]
User=rera
WorkingDirectory=/home/rera/app/rera-tracker
EnvironmentFile=/etc/rera-tracker.env
ExecStart=/home/rera/venv/bin/gunicorn -w 2 --threads 2 -b 127.0.0.1:8000 'rera_tracker.web:create_app()'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`sudo systemctl enable --now rera-web`. If a setting is missing, the service
refuses to start and the journal (`journalctl -u rera-web`) says which one.

The per-visitor sign-up limit is counted inside each worker, so with two
workers a visitor can in practice send up to twice the limit.

## 5. nginx in front, with https

Two small files. First, the log format. It goes **outside** any `server` block,
for example in `/etc/nginx/conf.d/rera-log.conf`, because nginx only allows
`log_format` at that level. It logs the path only: query strings carry one-time
tokens and must not be written to disk.

```nginx
log_format notokens '$remote_addr [$time_local] "$request_method $uri" $status $body_bytes_sent';
```

Then the site itself:

```nginx
server {
    server_name your-domain.example;
    # certbot adds the listen 443 ssl lines and the certificate paths

    access_log /var/log/nginx/rera.access.log notokens;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;   # overwrite, never append
        client_max_body_size 16k;
    }
}
```

Check it with `sudo nginx -t` before reloading.

Because nginx overwrites `X-Forwarded-For`, `RERA_TRACKER_TRUST_PROXY=1` is
safe. Without a proxy in front, leave that setting out.

## 6. The daily job

`/etc/systemd/system/rera-daily.service`:

```ini
[Unit]
Description=RERA tracker daily run

[Service]
Type=oneshot
User=rera
WorkingDirectory=/home/rera/app/rera-tracker
EnvironmentFile=/etc/rera-tracker.env
ExecStart=/usr/bin/python3 -m rera_tracker run
```

`/etc/systemd/system/rera-daily.timer` (06:17 India time, an hour with little
traffic on government sites):

```ini
[Unit]
Description=RERA tracker daily run

[Timer]
OnCalendar=*-*-* 06:17:00 Asia/Kolkata
Persistent=true

[Install]
WantedBy=timers.target
```

`sudo systemctl enable --now rera-daily.timer`. Check the time is what you meant with
`systemd-analyze calendar '*-*-* 06:17:00 Asia/Kolkata'`, which prints the next run.

The job costs two requests for the lists plus about two a day for each followed
project, at five seconds apart. The default cap is 500 requests a run. If you
follow more than about 240 projects, raise `RERA_TRACKER_MAX_REQUESTS`, and tell
HRERA the volume in your permission request.

## 7. Watching it

* Point an uptime monitor (any free one) at `https://your-domain.example/health`.
  It returns **503 if the daily job has not run for 36 hours**, so a stopped job
  turns the monitor red.
* The daily job emails `RERA_TRACKER_ADMIN_EMAIL` when a page could not be read.
  A burst of "could not read" lines usually means HRERA changed a page layout;
  the old data stays in place and nothing wrong is sent to anyone.

## 8. Backups

The whole business is one file. Install the tool once (`sudo apt install sqlite3`). Then
this makes a daily copy that is safe while the site is running:

```bash
sqlite3 /home/rera/data/rera_tracker.db ".backup '/home/rera/backup/rera-$(date +%F).db'"
```

Keep a few days, and copy them off the machine. The backup contains email
addresses, so protect it like the database and delete old ones.
