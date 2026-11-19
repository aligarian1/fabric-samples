import unittest
from unittest import mock

from rera_tracker import notify


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sent, self.logged_in = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent.append(message)


ENV = {"RERA_TRACKER_SMTP_HOST": "smtp.example.test", "RERA_TRACKER_SMTP_FROM": "alerts@example.test",
       "RERA_TRACKER_SMTP_USER": "u", "RERA_TRACKER_SMTP_PASSWORD": "p"}


class SendEmailTest(unittest.TestCase):
    def setUp(self):
        FakeSMTP.instances = []

    def test_message_and_one_click_unsubscribe_headers(self):
        with mock.patch.dict("os.environ", ENV), mock.patch.object(notify.smtplib, "SMTP", FakeSMTP):
            notify.send_email("a@example.com", "Hello हिंदी", "Body",
                              {"List-Unsubscribe": "<https://x.example/u?t=1>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port, smtp.tls, smtp.logged_in), ("smtp.example.test", 587, True, ("u", "p")))
        message = smtp.sent[0]
        self.assertEqual(message["To"], "a@example.com")
        self.assertEqual(message["From"], "alerts@example.test")
        self.assertEqual(message["List-Unsubscribe"], "<https://x.example/u?t=1>")
        self.assertEqual(message["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertIn("Body", message.get_content())

    def test_headers_with_line_breaks_are_refused(self):
        with mock.patch.dict("os.environ", ENV), mock.patch.object(notify.smtplib, "SMTP", FakeSMTP):
            with self.assertRaises(notify.DeliveryError):
                notify.send_email("a@example.com", "s", "b", {"X-Evil": "ok\r\nBcc: victim@example.com"})
        self.assertEqual(FakeSMTP.instances, [])

    def test_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(notify.DeliveryError) as caught:
                notify.send_email("a@example.com", "s", "b")
        self.assertIn("not configured", str(caught.exception))

    def test_network_trouble_becomes_a_delivery_error(self):
        class Broken(FakeSMTP):
            def send_message(self, message):
                raise notify.smtplib.SMTPException("mailbox full")

        with mock.patch.dict("os.environ", ENV), mock.patch.object(notify.smtplib, "SMTP", Broken):
            with self.assertRaises(notify.DeliveryError) as caught:
                notify.send_email("a@example.com", "s", "b")
        self.assertIn("mailbox full", str(caught.exception))

    def test_deliver_passes_headers_to_email_only(self):
        with mock.patch.object(notify, "send_email") as send:
            notify.deliver("email", "a@example.com", "s", "b", headers={"H": "v"})
            send.assert_called_once_with("a@example.com", "s", "b", {"H": "v"})
        printed = []
        notify.deliver("console", "a@example.com", "s", "b", out=printed.append, headers={"H": "v"})
        self.assertIn("Subject: s", printed)


if __name__ == "__main__":
    unittest.main()
