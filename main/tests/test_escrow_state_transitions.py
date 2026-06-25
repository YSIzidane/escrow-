from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Deal, Payment


class EscrowStateTransitionGuardsTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="guard_seller", password="x")
        self.buyer = User.objects.create_user(username="guard_buyer", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            buyer_approved=True,
            product_title="Guarded escrow deal",
            product_description="State transition guard coverage",
            price=Decimal("120.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("120.00"),
            status="pending",
            payment_method="stripe",
            transaction_id="pi_pending_guard",
        )

    def test_buyer_cannot_confirm_delivery_without_held_escrow(self):
        self.client.login(username="guard_buyer", password="x")

        response = self.client.post(
            reverse("deal_detail", args=[self.deal.id]),
            {"confirm_delivery": "1"},
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.deal.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.deal.status, "reserved")
        self.assertFalse(self.deal.buyer_confirmed)
        self.assertEqual(self.payment.status, "pending")

    def test_confirm_deal_cannot_complete_without_held_escrow(self):
        self.client.login(username="guard_buyer", password="x")

        response = self.client.post(reverse("confirm_deal", args=[self.deal.id]))

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.deal.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.deal.status, "reserved")
        self.assertFalse(self.deal.buyer_confirmed)
        self.assertFalse(self.deal.seller_confirmed)
        self.assertEqual(self.payment.status, "pending")

    def test_seller_cannot_mark_shipped_without_held_escrow(self):
        self.client.login(username="guard_seller", password="x")

        response = self.client.post(
            reverse("deal_detail", args=[self.deal.id]),
            {"mark_shipped": "1", "tracking_number": "TRACK-1"},
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.deal.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.deal.status, "reserved")
        self.assertFalse(self.deal.seller_shipped)
        self.assertEqual(self.payment.status, "pending")

    def test_confirm_deal_releases_only_when_payment_is_held(self):
        self.payment.status = "escrow_held"
        self.payment.save(update_fields=["status"])

        self.client.login(username="guard_buyer", password="x")
        first_response = self.client.post(reverse("confirm_deal", args=[self.deal.id]))

        self.client.login(username="guard_seller", password="x")
        second_response = self.client.post(reverse("confirm_deal", args=[self.deal.id]))

        self.assertRedirects(first_response, reverse("my_deals"))
        self.assertRedirects(second_response, reverse("my_deals"))
        self.deal.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertTrue(self.deal.buyer_confirmed)
        self.assertTrue(self.deal.seller_confirmed)
        self.assertEqual(self.deal.status, "completed")
        self.assertEqual(self.payment.status, "released")
