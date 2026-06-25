from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Deal


class MyDealsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="testpass123")
        self.other = User.objects.create_user(username="other", password="testpass123")
        self.third = User.objects.create_user(username="third", password="testpass123")
        self.client.login(username="owner", password="testpass123")

        self.seller_deal = Deal.objects.create(
            seller=self.user,
            buyer=self.other,
            product_title="Seller reserved deal",
            product_description="reserved",
            price=Decimal("100.00"),
            status="reserved",
        )
        self.buyer_deal = Deal.objects.create(
            seller=self.other,
            buyer=self.user,
            product_title="Buyer completed deal",
            product_description="completed",
            price=Decimal("90.00"),
            status="completed",
        )
        Deal.objects.create(
            seller=self.third,
            buyer=self.other,
            product_title="Foreign deal",
            product_description="should not appear",
            price=Decimal("40.00"),
            status="new",
        )

    def test_my_deals_page_lists_only_current_user_deals(self):
        response = self.client.get(reverse("my_deals"))

        self.assertEqual(response.status_code, 200)
        deals = list(response.context["deals"])
        self.assertEqual({deal.id for deal in deals}, {self.seller_deal.id, self.buyer_deal.id})

    def test_my_deals_page_exposes_expected_stats(self):
        response = self.client.get(reverse("my_deals"))

        self.assertEqual(response.status_code, 200)
        stats = response.context["stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["reserved"], 1)
        self.assertEqual(stats["selling"], 1)
        self.assertEqual(stats["buying"], 1)
        self.assertEqual(stats["active"], 1)
