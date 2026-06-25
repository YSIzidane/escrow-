from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Deal, SupportTicket


class SearchViewTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="alpha_seller", password="x")
        self.other = User.objects.create_user(username="otheruser", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            product_title="Gaming Laptop RTX",
            product_description="High performance machine for creators",
            price=Decimal("1200.00"),
            status="new",
        )

    def test_search_finds_deals_and_users(self):
        response = self.client.get(reverse("search"), {"q": "gaming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gaming Laptop RTX")
        self.assertEqual(response.context["deals_total"], 1)

    def test_search_partial_renders_for_htmx(self):
        response = self.client.get(
            reverse("search"),
            {"q": "alpha"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="search-results",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alpha_seller")
        self.assertNotContains(response, "<html", html=False)

    def test_search_page_uses_english_translation_keys(self):
        self.client.cookies["site_language"] = "en"

        response = self.client.get(reverse("search"), {"q": "gaming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search")
        self.assertContains(response, "1 deals")
        self.assertContains(response, "Search starts after at least 2 characters.")
        self.assertNotContains(response, "Fast search across users and listings")


class ReportingFlowTests(TestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(username="reporter", password="x")
        self.seller = User.objects.create_user(username="reported_seller", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            product_title="Suspicious Offer",
            product_description="Details",
            price=Decimal("75.00"),
            status="new",
        )
        self.client.login(username="reporter", password="x")

    def test_report_mode_creates_high_priority_ticket(self):
        response = self.client.post(
            reverse("create_ticket"),
            {
                "mode": "report",
                "subject": "Seller asked to move outside platform",
                "description": "The seller asked me to pay outside the website.",
                "category": "other",
                "deal_id": str(self.deal.id),
                "reported_user_id": str(self.seller.id),
            },
        )

        ticket = SupportTicket.objects.get()
        self.assertRedirects(response, reverse("ticket_detail", args=[ticket.id]))
        self.assertTrue(ticket.subject.startswith("[REPORT]"))
        self.assertEqual(ticket.priority, "high")
        self.assertEqual(ticket.category, "deal")
        self.assertEqual(ticket.deal, self.deal)
        self.assertIn("Reported user: reported_seller", ticket.description)
