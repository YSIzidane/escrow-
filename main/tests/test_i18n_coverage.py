import ast
import html
import re
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.i18n.ar import TRANSLATIONS_AR
from main.i18n.en import TRANSLATIONS_EN
from main.models import Deal, Friendship, Notification, SupportTicket


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TranslationCatalogCoverageTests(SimpleTestCase):
    def test_translation_catalogs_do_not_define_duplicate_keys(self):
        catalogs = [
            (PROJECT_ROOT / "main/i18n/ar.py", "TRANSLATIONS_AR"),
            (PROJECT_ROOT / "main/i18n/en.py", "TRANSLATIONS_EN"),
        ]

        for path, variable_name in catalogs:
            with self.subTest(catalog=str(path)):
                keys = self._literal_dict_keys(path, variable_name)
                duplicates = sorted({key for key in keys if keys.count(key) > 1})
                self.assertEqual(duplicates, [])

    def test_arabic_and_english_catalogs_have_the_same_keys(self):
        self.assertEqual(set(TRANSLATIONS_AR), set(TRANSLATIONS_EN))

    def test_used_translation_keys_exist_in_both_catalogs(self):
        used_keys = set()
        tag_pattern = re.compile(r"{%\s*t\s+[\"']([^\"']+)[\"']\s*%}")
        call_pattern = re.compile(r"get_translation\(\s*[\"']([^\"']+)[\"']")

        for source_file in self._iter_source_files():
            text = source_file.read_text(encoding="utf-8")
            used_keys.update(tag_pattern.findall(text))
            used_keys.update(call_pattern.findall(text))

        self.assertFalse(used_keys - set(TRANSLATIONS_AR))
        self.assertFalse(used_keys - set(TRANSLATIONS_EN))

    def test_support_choice_translation_keys_exist(self):
        expected_keys = set()
        expected_keys.update(f"support.status.{value}" for value, _ in SupportTicket.STATUS_CHOICES)
        expected_keys.update(f"support.priority.{value}" for value, _ in SupportTicket.PRIORITY_CHOICES)
        expected_keys.update(f"support.category.{value}" for value, _ in SupportTicket.CATEGORY_CHOICES)

        self.assertFalse(expected_keys - set(TRANSLATIONS_AR))
        self.assertFalse(expected_keys - set(TRANSLATIONS_EN))

    def test_translation_values_do_not_contain_common_mojibake(self):
        suspicious = ("\u00c3", "\u00d8", "\u00d9", "\ufffd")

        for catalog in (TRANSLATIONS_AR, TRANSLATIONS_EN):
            bad_keys = [
                key
                for key, value in catalog.items()
                if isinstance(value, str) and any(marker in value for marker in suspicious)
            ]
            self.assertEqual(bad_keys, [])

    def test_ui_source_files_do_not_contain_common_mojibake(self):
        suspicious = ("\u00c3", "\u00d8", "\u00d9", "\ufffd")
        offenders = []

        for source_file in self._iter_source_files():
            text = source_file.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in suspicious):
                offenders.append(str(source_file.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_recent_dark_pages_do_not_hardcode_arabic_copy(self):
        arabic_pattern = re.compile(r"[\u0600-\u06ff]")
        checked_files = [
            "templates/support/create_ticket.html",
            "templates/support/ticket_detail.html",
            "templates/notifications.html",
            "templates/chat_hub.html",
            "templates/friends_list.html",
            "templates/partials/friends_sections.html",
            "templates/private_chat.html",
            "templates/create_deal_form.html",
            "templates/deals.html",
            "templates/partials/deals_grid.html",
            "static/js/deals_dark.js",
            "static/js/support_dark.js",
        ]

        offenders = []
        for relative_path in checked_files:
            text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            if arabic_pattern.search(text):
                offenders.append(relative_path)

        self.assertEqual(offenders, [])

    def _iter_source_files(self):
        for root in ("templates", "main", "static/js"):
            for path in (PROJECT_ROOT / root).rglob("*"):
                if path.suffix not in {".html", ".txt", ".py", ".js"}:
                    continue
                if any(part in {"i18n", "migrations", "__pycache__"} for part in path.parts):
                    continue
                yield path

    def _literal_dict_keys(self, path, variable_name):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in tree.body:
            targets = getattr(node, "targets", ())
            if not any(getattr(target, "id", None) == variable_name for target in targets):
                continue
            if not isinstance(node.value, ast.Dict):
                return []
            return [
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
        return []


class AccountAuthPagesEnglishRenderTests(TestCase):
    def setUp(self):
        self.client.cookies["site_language"] = "en"

    def test_login_page_renders_english_copy_and_placeholders(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secure escrow access")
        self.assertContains(response, "Encrypted access")
        self.assertContains(response, "Security and trust signals")
        self.assertNotRegex(self._visible_text(response), r"[\u0600-\u06ff]")

        markup = response.content.decode("utf-8", errors="replace")
        self.assertIn('placeholder="example@email.com"', markup)
        self.assertIn('placeholder="Enter your password"', markup)

    def test_signup_page_renders_english_copy_and_field_text(self):
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secure account setup")
        self.assertContains(response, "Escrow protection")
        self.assertContains(response, "Security and trust signals")
        self.assertNotRegex(self._visible_text(response), r"[\u0600-\u06ff]")

        markup = response.content.decode("utf-8", errors="replace")
        expected_fragments = [
            'placeholder="Email address"',
            'placeholder="Business name"',
            'placeholder="Password"',
            'placeholder="Confirm password"',
            'data-label-weak="Weak"',
            'data-label-fair="Fair"',
            'data-label-good="Good"',
            'data-label-strong="Strong"',
        ]
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, markup)

    def _visible_text(self, response):
        text = response.content.decode("utf-8", errors="replace")
        text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return html.unescape(re.sub(r"\s+", " ", text))


class RecentDarkPagesEnglishRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="english_user", password="pass")
        self.friend = User.objects.create_user(username="english_friend", password="pass")
        Friendship.objects.create(from_user=self.user, to_user=self.friend, status="accepted")
        self.deal = Deal.objects.create(
            seller=self.user,
            product_title="Translation audit listing",
            product_description="A clean English test listing.",
            price=Decimal("42.00"),
            status="new",
        )
        self.ticket = SupportTicket.objects.create(
            user=self.user,
            deal=self.deal,
            subject="Payment confirmation",
            description="I need help checking a payment.",
            category="payment",
            priority="medium",
            status="open",
        )
        Notification.objects.create(
            recipient=self.user,
            notif_type="ticket",
            title="Ticket update",
            body="Support replied to your ticket.",
            url=reverse("ticket_detail", args=[self.ticket.id]),
        )
        self.client.login(username="english_user", password="pass")
        self.client.cookies["site_language"] = "en"

    def test_recent_dark_pages_render_key_english_copy(self):
        pages = [
            (reverse("notifications"), "Notifications"),
            (reverse("profile"), "Profile"),
            (reverse("my_deals"), "My Deals"),
            (reverse("my_tickets"), "Support and Reports"),
            (reverse("create_ticket"), "Open Support Ticket"),
            (f'{reverse("create_ticket")}?mode=report&deal_id={self.deal.id}&reported_user_id={self.friend.id}', "Create Report"),
            (reverse("ticket_detail", args=[self.ticket.id]), "Ticket summary"),
            (reverse("chat_hub"), "Messages"),
            (reverse("friends_list"), "Friends"),
            (reverse("private_chat", args=[self.friend.id]), "Secure private chat"),
            (reverse("create_deal"), "Create a New Deal"),
            (reverse("listings"), "Browse Deals"),
            (reverse("search"), "Search"),
        ]

        for url, expected_text in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_text)
                self.assertNotRegex(self._visible_text(response), r"[\u0600-\u06ff]")

    def test_ticket_detail_translates_choice_labels(self):
        response = self.client.get(reverse("ticket_detail", args=[self.ticket.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open")
        self.assertContains(response, "Medium")
        self.assertContains(response, "Payment issue")

    def _visible_text(self, response):
        text = response.content.decode("utf-8", errors="replace")
        text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return html.unescape(re.sub(r"\s+", " ", text))
