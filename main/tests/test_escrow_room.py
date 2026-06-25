# ==================== Escrow Room Tests ====================
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.deal_engine import build_deal_room_context
from main.models import Deal, DealEvent, DealEvidence, EscrowRoom, Notification, Payment
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups


class EscrowRoomSecurityTests(TestCase):
    """Tests that force release/refund paths are blocked."""

    def setUp(self):
        ensure_admin_role_groups()
        self.admin = User.objects.create_user(
            username="admin", password="adminpass", is_staff=True
        )
        self.admin.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"]))
        self.seller = User.objects.create_user(username="seller", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Test Deal",
            product_description="Test description",
            price=Decimal("200.00"),
            status="reserved",
        )
        self.room, _ = EscrowRoom.objects.get_or_create(deal=self.deal)

    def test_release_rejected_without_escrow_held(self):
        """Admin release should be rejected when no payment is escrow_held."""
        # No payment exists at all
        self.client.login(username="admin", password="adminpass")
        response = self.client.post(
            reverse("escrow_room", args=[self.deal.id]),
            {"action": "release"},
        )
        self.assertEqual(response.status_code, 302)

        # Deal status should NOT change
        self.deal.refresh_from_db()
        self.assertNotEqual(self.deal.status, "completed")

    def test_release_rejected_with_pending_payment(self):
        """Release should fail when payment is pending (not escrow_held)."""
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("200.00"),
            status="pending",
            transaction_id="pi_test",
        )
        self.client.login(username="admin", password="adminpass")
        self.client.post(
            reverse("escrow_room", args=[self.deal.id]),
            {"action": "release"},
        )

        self.deal.refresh_from_db()
        self.assertNotEqual(self.deal.status, "completed")

        # Payment status should NOT be changed locally
        payment = Payment.objects.get(deal=self.deal)
        self.assertNotEqual(payment.status, "released")

    def test_refund_rejected_with_released_payment(self):
        """Refund should fail when payment was already released."""
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("200.00"),
            status="released",
            transaction_id="pi_test",
        )
        self.client.login(username="admin", password="adminpass")
        self.client.post(
            reverse("escrow_room", args=[self.deal.id]),
            {"action": "refund"},
        )

        # Payment status should remain released
        payment = Payment.objects.get(deal=self.deal)
        self.assertEqual(payment.status, "released")

    def test_non_party_cannot_access_room(self):
        """Regular user who is not buyer/seller should be redirected."""
        outsider = User.objects.create_user(username="outsider", password="x")
        self.client.login(username="outsider", password="x")
        response = self.client.get(
            reverse("escrow_room", args=[self.deal.id])
        )
        self.assertRedirects(response, reverse("home"))

    def test_buyer_can_access_room(self):
        """Buyer should be able to access the escrow room."""
        self.client.login(username="buyer", password="x")
        response = self.client.get(
            reverse("escrow_room", args=[self.deal.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_seller_can_access_room(self):
        """Seller should be able to access the escrow room."""
        self.client.login(username="seller", password="x")
        response = self.client.get(
            reverse("escrow_room", args=[self.deal.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_seller_can_start_delivery_from_escrow_room(self):
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("200.00"),
            status="escrow_held",
            transaction_id="txn_room_delivery",
        )

        self.client.login(username="seller", password="x")
        response = self.client.post(
            reverse("escrow_room", args=[self.deal.id]),
            {
                "action": "mark_shipped",
                "tracking_number": "ROOM-TRACK-1",
                "shipping_proof": SimpleUploadedFile(
                    "delivery-proof.pdf",
                    b"%PDF-1.4 delivery proof",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertRedirects(response, reverse("escrow_room", args=[self.deal.id]))
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "shipped")
        self.assertTrue(self.deal.seller_shipped)
        self.assertEqual(self.deal.tracking_number, "ROOM-TRACK-1")
        self.assertTrue(
            DealEvent.objects.filter(deal=self.deal, event_type="delivery_started").exists()
        )
        evidence = DealEvidence.objects.get(deal=self.deal, evidence_type=DealEvidence.TYPE_DELIVERY)
        self.assertEqual(evidence.uploader, self.seller)
        self.assertEqual(len(evidence.sha256_hash), 64)
        notification = Notification.objects.get(recipient=self.buyer, action="delivery_started")
        self.assertEqual(notification.deal, self.deal)
        self.assertEqual(notification.actor, self.seller)
        self.assertEqual(notification.priority, Notification.PRIORITY_HIGH)

    def test_room_context_promotes_buyer_confirmation_after_delivery_started(self):
        self.deal.status = "shipped"
        self.deal.seller_shipped = True
        self.deal.save(update_fields=["status", "seller_shipped", "updated_at"])
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("200.00"),
            status="escrow_held",
            transaction_id="txn_room_context",
        )

        context = build_deal_room_context(self.deal, self.buyer, "en")

        self.assertEqual(context["engine_state"], "in_delivery")
        self.assertEqual(context["room_action"]["kind"], "confirm_form")
        self.assertTrue(context["room_deadline"]["active"])

    def test_evidence_artifact_cannot_be_mutated_after_creation(self):
        evidence = DealEvidence.objects.create(
            deal=self.deal,
            uploader=self.buyer,
            evidence_type=DealEvidence.TYPE_DISPUTE,
            file=SimpleUploadedFile(
                "dispute-proof.pdf",
                b"%PDF-1.4 dispute proof",
                content_type="application/pdf",
            ),
        )

        evidence.evidence_type = DealEvidence.TYPE_DELIVERY

        with self.assertRaises(ValidationError):
            evidence.save()
