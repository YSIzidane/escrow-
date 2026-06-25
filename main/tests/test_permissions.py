# ==================== Permissions Tests ====================
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.models import Bid, Deal, Friendship, Payment


class PostOnlyEndpointTests(TestCase):
    """Ensure state-changing endpoints reject GET requests."""

    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", password="testpass")
        self.user2 = User.objects.create_user(username="user2", password="testpass")
        self.deal = Deal.objects.create(
            seller=self.user1,
            buyer=self.user2,
            product_title="Test Deal",
            product_description="Test",
            price=Decimal("50.00"),
            status="reserved",
        )
        self.client.login(username="user1", password="testpass")

    def test_confirm_deal_rejects_get(self):
        """confirm_deal should reject GET requests (405)."""
        response = self.client.get(
            reverse("confirm_deal", args=[self.deal.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_deal_rejects_get(self):
        """delete_deal should reject GET requests (405)."""
        self.deal.status = "new"
        self.deal.save()
        response = self.client.get(
            reverse("delete_deal", args=[self.deal.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_accept_bid_rejects_get(self):
        """accept_bid should reject GET requests (405)."""
        bid = Bid.objects.create(
            deal=self.deal, bidder=self.user2, amount=Decimal("60.00")
        )
        response = self.client.get(
            reverse("accept_bid", args=[bid.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_accept_friend_request_rejects_get(self):
        """accept_friend_request should reject GET requests (405)."""
        friendship = Friendship.objects.create(
            from_user=self.user2, to_user=self.user1, status="pending"
        )
        response = self.client.get(
            reverse("accept_friend_request", args=[friendship.id])
        )
        self.assertEqual(response.status_code, 405)


class DealPermissionTests(TestCase):
    """Ensure deal operations respect user permissions."""

    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.outsider = User.objects.create_user(username="outsider", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            product_title="Test",
            product_description="Test desc",
            price=Decimal("50.00"),
            status="new",
        )

    def test_non_seller_cannot_delete_deal(self):
        """Non-seller should not be able to delete a deal."""
        self.client.login(username="outsider", password="x")
        response = self.client.post(
            reverse("delete_deal", args=[self.deal.id])
        )
        # Should redirect with error, not delete
        self.assertTrue(Deal.objects.filter(id=self.deal.id).exists())

    def test_seller_can_delete_new_deal(self):
        """Seller should be able to delete their own new deal."""
        self.client.login(username="seller", password="x")
        response = self.client.post(
            reverse("delete_deal", args=[self.deal.id])
        )
        self.assertFalse(Deal.objects.filter(id=self.deal.id).exists())

    def test_payment_release_requires_staff(self):
        """Non-staff should be denied from releasing payments."""
        self.client.login(username="buyer", password="x")
        response = self.client.post(
            reverse("payment_release", args=[self.deal.id])
        )
        # Should redirect with error message
        self.assertEqual(response.status_code, 302)

    def test_payment_refund_requires_staff(self):
        """Non-staff should be denied from refunding payments."""
        self.client.login(username="buyer", password="x")
        response = self.client.post(
            reverse("payment_refund", args=[self.deal.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_seller_cannot_start_checkout_for_own_deal(self):
        self.client.login(username="seller", password="x")

        response = self.client.get(reverse("create_payment", args=[self.deal.id]))

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.assertFalse(Payment.objects.filter(deal=self.deal).exists())

    def test_seller_cannot_submit_ccp_payment_for_own_deal(self):
        self.client.login(username="seller", password="x")

        response = self.client.post(
            reverse("ccp_checkout_submit", args=[self.deal.id]),
            {
                "reference_number": "SELF-REF-1",
                "proof_file": SimpleUploadedFile(
                    "proof.png",
                    b"fake-proof",
                    content_type="image/png",
                ),
            },
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.assertFalse(Payment.objects.filter(deal=self.deal).exists())

    def test_fixed_price_deal_rejects_bids(self):
        self.client.login(username="buyer", password="x")

        response = self.client.post(
            reverse("submit_bid", args=[self.deal.id]),
            {"amount": "60.00", "message": "offer"},
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        self.assertEqual(Bid.objects.filter(deal=self.deal).count(), 0)
