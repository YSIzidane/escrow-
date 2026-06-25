# ==================== Payment Tests ====================
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from main.models import Bid, Deal, Payment, PaymentAuditLog, Profile, TransactionInvoice
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups
from main.services.payment_service import process_successful_payment
from main.views.payments import (
    PaymentStateError,
    release_payment_for_deal,
    refund_payment_for_deal,
)


class ReleasePaymentTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Test Product",
            product_description="Test description",
            price=Decimal("100.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("100.00"),
            status="escrow_held",
            transaction_id="pi_test_123",
        )

    def test_release_success(self):
        """Release should succeed when payment is in escrow_held."""
        payment, net, fee, deal = release_payment_for_deal(self.deal)

        self.assertEqual(payment.status, "released")
        self.assertEqual(deal.status, "completed")
        self.assertEqual(fee, Decimal("100.00") * Decimal("0.05"))
        self.assertEqual(net, Decimal("100.00") - fee)

        # Seller balance should be credited
        seller_profile = Profile.objects.get(user=self.seller)
        self.assertEqual(seller_profile.balance, net)

        invoice = TransactionInvoice.objects.get(payment=payment)
        self.assertEqual(invoice.buyer, self.buyer)
        self.assertEqual(invoice.seller, self.seller)
        self.assertEqual(invoice.subtotal, Decimal("100.00"))
        self.assertEqual(invoice.platform_fee, fee)
        self.assertEqual(invoice.seller_net, net)

    def test_release_rejects_non_escrow_held(self):
        """Release should raise PaymentStateError when not escrow_held."""
        self.payment.status = "pending"
        self.payment.save()

        with self.assertRaises(PaymentStateError):
            release_payment_for_deal(self.deal)

        # State should not change
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "reserved")

    def test_release_rejects_no_payment(self):
        """Release should raise PaymentStateError when no payment exists."""
        self.payment.delete()

        with self.assertRaises(PaymentStateError):
            release_payment_for_deal(self.deal)

    def test_release_idempotent_guard(self):
        """Releasing twice should fail the second time."""
        release_payment_for_deal(self.deal)

        with self.assertRaises(PaymentStateError):
            release_payment_for_deal(self.deal)

    def test_release_credits_platform_owner_fee_when_superuser_exists(self):
        owner = User.objects.create_superuser(
            username="owner",
            email="owner@example.com",
            password="x",
        )

        _, net, fee, _ = release_payment_for_deal(self.deal)

        owner.profile.refresh_from_db()
        self.assertEqual(owner.profile.balance, fee)
        self.assertEqual(Profile.objects.get(user=self.seller).balance, net)


class RefundPaymentTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Test Product",
            product_description="Test description",
            price=Decimal("100.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("100.00"),
            status="escrow_held",
            transaction_id="pi_test_456",
        )

    @patch("main.views.payments._stripe_is_configured", return_value=False)
    def test_refund_success_without_stripe(self, mock_stripe):
        """CCP refunds may complete locally when no Stripe refund is required."""
        self.payment.payment_method = "ccp"
        self.payment.save(update_fields=["payment_method"])

        payment, deal = refund_payment_for_deal(self.deal)

        self.assertEqual(payment.status, "refunded")
        self.assertEqual(deal.status, "new")
        self.assertIsNone(deal.buyer)

    @patch("main.views.payments._stripe_is_configured", return_value=False)
    def test_refund_blocks_stripe_payment_without_stripe_config(self, mock_stripe):
        """Stripe refunds must not be marked locally if Stripe is unavailable."""
        with self.assertRaises(PaymentStateError) as exc_info:
            refund_payment_for_deal(self.deal)

        self.assertEqual(str(exc_info.exception), "stripe_not_configured")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "escrow_held")

        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "reserved")

    def test_refund_rejects_released_payment(self):
        """Refund should raise PaymentStateError when already released."""
        self.payment.status = "released"
        self.payment.save()

        with self.assertRaises(PaymentStateError):
            refund_payment_for_deal(self.deal)

    def test_refund_rejects_no_payment(self):
        """Refund should raise PaymentStateError when no payment exists."""
        self.payment.delete()

        with self.assertRaises(PaymentStateError):
            refund_payment_for_deal(self.deal)

    @patch("main.views.payments._stripe_is_configured", return_value=True)
    @patch("stripe.Refund.create")
    def test_refund_calls_stripe(self, mock_refund, mock_stripe_configured):
        """Refund should call Stripe API when configured."""
        refund_payment_for_deal(self.deal)

        mock_refund.assert_called_once()
        call_kwargs = mock_refund.call_args
        self.assertIn("payment_intent", call_kwargs.kwargs)

    @patch("main.views.payments._stripe_is_configured", return_value=False)
    def test_refund_marks_invoice_as_refunded(self, mock_stripe):
        self.payment.payment_method = "ccp"
        self.payment.save(update_fields=["payment_method"])

        payment, _ = refund_payment_for_deal(self.deal)

        invoice = TransactionInvoice.objects.get(payment=payment)
        self.assertEqual(invoice.status, "refunded")

    @patch("main.views.payments._stripe_is_configured", return_value=False)
    def test_refund_resets_auction_bid_state_and_price(self, mock_stripe):
        seller = User.objects.create_user(username="auction_seller", password="x")
        buyer = User.objects.create_user(username="auction_buyer", password="x")
        other_bidder = User.objects.create_user(username="auction_other", password="x")
        deal = Deal.objects.create(
            seller=seller,
            buyer=buyer,
            product_title="Auction product",
            product_description="Auction refund coverage",
            starting_price=Decimal("25.00"),
            price=Decimal("60.00"),
            is_auction=True,
            auction_ends_at="2030-01-01T00:00:00Z",
            status="reserved",
        )
        accepted_bid = Bid.objects.create(
            deal=deal,
            bidder=buyer,
            amount=Decimal("60.00"),
            is_accepted=True,
        )
        other_bid = Bid.objects.create(
            deal=deal,
            bidder=other_bidder,
            amount=Decimal("55.00"),
            is_rejected=True,
        )
        payment = Payment.objects.create(
            deal=deal,
            payer=buyer,
            amount=Decimal("60.00"),
            status="escrow_held",
            payment_method="ccp",
            transaction_id="CCP-AUCTION-REFUND",
        )

        refund_payment_for_deal(deal)

        deal.refresh_from_db()
        payment.refresh_from_db()
        accepted_bid.refresh_from_db()
        other_bid.refresh_from_db()

        self.assertEqual(payment.status, "refunded")
        self.assertEqual(deal.status, "new")
        self.assertIsNone(deal.buyer)
        self.assertEqual(deal.price, Decimal("25.00"))
        self.assertFalse(accepted_bid.is_accepted)
        self.assertFalse(accepted_bid.is_rejected)
        self.assertFalse(other_bid.is_accepted)
        self.assertFalse(other_bid.is_rejected)


class InvoiceAccessTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.outsider = User.objects.create_user(username="outsider", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Secured Laptop",
            product_description="Test description",
            price=Decimal("100.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("100.00"),
            status="escrow_held",
            transaction_id="pi_test_789",
        )
        release_payment_for_deal(self.deal)
        self.invoice = TransactionInvoice.objects.get(payment=self.payment)

    def test_buyer_can_open_invoice(self):
        self.client.login(username="buyer", password="x")
        response = self.client.get(reverse("invoice_detail", args=[self.invoice.id]))
        self.assertEqual(response.status_code, 200)

    def test_outsider_cannot_open_invoice(self):
        self.client.login(username="outsider", password="x")
        response = self.client.get(reverse("invoice_detail", args=[self.invoice.id]))
        self.assertRedirects(response, reverse("profile"))

    @patch("main.views.payments.model_table_exists", return_value=False)
    def test_invoice_page_redirects_when_table_missing(self, mocked_exists):
        self.client.login(username="buyer", password="x")
        response = self.client.get(reverse("invoice_detail", args=[self.invoice.id]))
        self.assertRedirects(response, reverse("profile"))


class PaymentSuccessAccessTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="success_seller", password="x")
        self.buyer = User.objects.create_user(username="success_buyer", password="x")
        self.outsider = User.objects.create_user(username="success_outsider", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Private Payment",
            product_description="Success page access check",
            price=Decimal("120.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("120.00"),
            status="escrow_held",
            transaction_id="pi_private_success",
        )

    def test_buyer_can_open_payment_success_page(self):
        self.client.login(username="success_buyer", password="x")
        response = self.client.get(reverse("payment_success_page", args=[self.deal.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pi_private_success")

    def test_outsider_cannot_open_payment_success_page(self):
        self.client.login(username="success_outsider", password="x")
        response = self.client.get(reverse("payment_success_page", args=[self.deal.id]))
        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))


class PaymentAuditTrailTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        self.staff.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"]))
        self.seller = User.objects.create_user(username="seller_audit", password="x")
        self.buyer = User.objects.create_user(username="buyer_audit", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Audited Deal",
            product_description="Audit coverage",
            price=Decimal("80.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("80.00"),
            status="escrow_held",
            payment_method="ccp",
            transaction_id="CCP-AUDIT-001",
        )
        self.client.login(username="staff", password="x")

    def test_payment_release_creates_audit_log(self):
        response = self.client.post(reverse("payment_release", args=[self.deal.id]))

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        audit = PaymentAuditLog.objects.get(action="released")
        self.assertEqual(audit.payment, self.payment)
        self.assertEqual(audit.admin, self.staff)
        self.assertEqual(audit.reason, "Admin release from direct payment action.")

    def test_payment_refund_creates_audit_log(self):
        response = self.client.post(reverse("payment_refund", args=[self.deal.id]))

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        audit = PaymentAuditLog.objects.get(action="refunded")
        self.assertEqual(audit.payment, self.payment)
        self.assertEqual(audit.admin, self.staff)
        self.assertEqual(audit.reason, "Admin refund from direct payment action.")


class SuccessfulPaymentIdempotencyTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller_idem", password="x")
        self.buyer = User.objects.create_user(username="buyer_idem", password="x")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Idempotent Deal",
            product_description="Webhook safety",
            price=Decimal("150.00"),
            status="reserved",
        )

    def test_successful_payment_does_not_reopen_released_payment(self):
        payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("150.00"),
            status="released",
            payment_method="stripe",
            transaction_id="pi_existing",
        )

        processed_payment, processed_deal = process_successful_payment(
            self.deal,
            self.buyer,
            transaction_id="pi_newer",
            payment_method="stripe",
        )

        payment.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertEqual(processed_payment.id, payment.id)
        self.assertEqual(payment.status, "released")
        self.assertEqual(payment.transaction_id, "pi_existing")
        self.assertEqual(processed_deal.status, "reserved")

    def test_successful_payment_does_not_reopen_refunded_payment(self):
        payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("150.00"),
            status="refunded",
            payment_method="stripe",
            transaction_id="pi_refunded",
        )
        self.deal.status = "new"
        self.deal.buyer = None
        self.deal.save(update_fields=["status", "buyer"])

        processed_payment, processed_deal = process_successful_payment(
            self.deal,
            self.buyer,
            transaction_id="pi_late_duplicate",
            payment_method="stripe",
        )

        payment.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertEqual(processed_payment.id, payment.id)
        self.assertEqual(payment.status, "refunded")
        self.assertEqual(payment.transaction_id, "pi_refunded")
        self.assertEqual(processed_deal.status, "new")
        self.assertIsNone(self.deal.buyer)
