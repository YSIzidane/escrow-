from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.models import Deal, Payment, PaymentAuditLog
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups


class CcpReviewFlowTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        finance_group = Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"])

        self.admin = User.objects.create_user(
            username="finance_reviewer",
            password="financepass",
            is_staff=True,
        )
        self.admin.groups.add(finance_group)

        self.seller = User.objects.create_user(username="seller_ccp", password="sellerpass")
        self.buyer = User.objects.create_user(username="buyer_ccp", password="buyerpass")

        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Manual Transfer Deal",
            product_description="CCP review flow",
            price=Decimal("250.00"),
            status="new",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("250.00"),
            status="pending_manual_verification",
            payment_method="ccp",
            transaction_id="CCP-APPROVE-001",
            proof_file=SimpleUploadedFile("proof.png", b"proof-bytes", content_type="image/png"),
            reference_number="REF-CCP-1",
        )
        self.client.login(username="finance_reviewer", password="financepass")

    def test_approve_requires_review_note(self):
        response = self.client.post(reverse("staff_approve_ccp", args=[self.payment.id]), {})

        self.assertRedirects(response, reverse("staff_pending_payments"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending_manual_verification")
        self.assertEqual(PaymentAuditLog.objects.count(), 0)

    def test_approve_records_audit_note_and_transitions_once(self):
        response = self.client.post(
            reverse("staff_approve_ccp", args=[self.payment.id]),
            {"review_note": "Reference and screenshot matched the expected transfer code."},
        )

        self.assertRedirects(response, reverse("staff_pending_payments"))
        self.payment.refresh_from_db()
        self.deal.refresh_from_db()

        self.assertEqual(self.payment.status, "escrow_held")
        self.assertEqual(self.deal.status, "reserved")
        self.assertEqual(self.deal.buyer, self.buyer)
        self.assertTrue(self.deal.buyer_approved)

        audit = PaymentAuditLog.objects.get()
        self.assertEqual(audit.action, "approved")
        self.assertEqual(audit.admin, self.admin)
        self.assertEqual(
            audit.reason,
            "Reference and screenshot matched the expected transfer code.",
        )

    def test_second_approve_does_not_duplicate_audit(self):
        approve_url = reverse("staff_approve_ccp", args=[self.payment.id])

        first_response = self.client.post(
            approve_url,
            {"review_note": "Initial approval after manual verification."},
        )
        second_response = self.client.post(
            approve_url,
            {"review_note": "Second approval attempt should be ignored."},
        )

        self.assertRedirects(first_response, reverse("staff_pending_payments"))
        self.assertRedirects(second_response, reverse("staff_pending_payments"))
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "escrow_held")
        self.assertEqual(PaymentAuditLog.objects.filter(action="approved").count(), 1)

    def test_reject_still_records_reason_in_audit_log(self):
        response = self.client.post(
            reverse("staff_reject_ccp", args=[self.payment.id]),
            {"reason": "Transfer code is missing from the receipt."},
        )

        self.assertRedirects(response, reverse("staff_pending_payments"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")

        audit = PaymentAuditLog.objects.get()
        self.assertEqual(audit.action, "rejected")
        self.assertEqual(audit.reason, "Transfer code is missing from the receipt.")

    def test_reject_clears_legacy_unfunded_reservation(self):
        self.deal.status = "reserved"
        self.deal.buyer_approved = True
        self.deal.save(update_fields=["status", "buyer_approved"])

        response = self.client.post(
            reverse("staff_reject_ccp", args=[self.payment.id]),
            {"reason": "Receipt does not match the transfer reference."},
        )

        self.assertRedirects(response, reverse("staff_pending_payments"))
        self.payment.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.deal.status, "new")
        self.assertIsNone(self.deal.buyer)
        self.assertFalse(self.deal.buyer_approved)


class CcpBuyerSubmissionGuardsTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller_ccp_buyer", password="sellerpass")
        self.buyer = User.objects.create_user(username="buyer_ccp_buyer", password="buyerpass")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Manual Transfer Checkout",
            product_description="CCP buyer guards",
            price=Decimal("180.00"),
            status="new",
        )
        self.client.login(username="buyer_ccp_buyer", password="buyerpass")

    def test_buyer_cannot_resubmit_while_manual_review_is_pending(self):
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("180.00"),
            status="pending_manual_verification",
            payment_method="ccp",
            transaction_id="CCP-PENDING-001",
            proof_file=SimpleUploadedFile("proof.png", b"proof-bytes", content_type="image/png"),
            reference_number="REF-PENDING",
        )

        response = self.client.post(
            reverse("ccp_checkout_submit", args=[self.deal.id]),
            {
                "reference_number": "REF-NEW",
                "proof_file": SimpleUploadedFile("new-proof.png", b"new-bytes", content_type="image/png"),
            },
        )

        self.assertRedirects(response, reverse("create_payment", args=[self.deal.id]))
        payment = Payment.objects.get(deal=self.deal)
        self.assertEqual(payment.status, "pending_manual_verification")
        self.assertEqual(payment.reference_number, "REF-PENDING")

    def test_opening_checkout_does_not_reset_pending_manual_review(self):
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("180.00"),
            status="pending_manual_verification",
            payment_method="ccp",
            transaction_id="CCP-PENDING-GET",
            reference_number="REF-PENDING-GET",
        )

        response = self.client.get(reverse("create_payment", args=[self.deal.id]))

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(deal=self.deal)
        self.assertEqual(payment.status, "pending_manual_verification")
        self.assertEqual(payment.transaction_id, "CCP-PENDING-GET")

    def test_buyer_cannot_resubmit_after_max_retries(self):
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("180.00"),
            status="failed_max_retries",
            payment_method="ccp",
            transaction_id="CCP-FAILED-001",
            rejection_count=3,
            rejection_reason="Too many invalid proofs",
            reference_number="REF-FAILED",
        )

        response = self.client.post(
            reverse("ccp_checkout_submit", args=[self.deal.id]),
            {
                "reference_number": "REF-NEW",
                "proof_file": SimpleUploadedFile("new-proof.png", b"new-bytes", content_type="image/png"),
            },
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        payment = Payment.objects.get(deal=self.deal)
        self.assertEqual(payment.status, "failed_max_retries")
        self.assertEqual(payment.reference_number, "REF-FAILED")

    def test_ccp_submission_does_not_reserve_deal_before_approval(self):
        self.deal.buyer = None
        self.deal.buyer_approved = False
        self.deal.status = "new"
        self.deal.save(update_fields=["buyer", "buyer_approved", "status"])

        response = self.client.post(
            reverse("ccp_checkout_submit", args=[self.deal.id]),
            {
                "reference_number": "REF-NOT-RESERVED",
                "proof_file": SimpleUploadedFile("proof.png", b"proof-bytes", content_type="image/png"),
            },
        )

        self.assertRedirects(response, reverse("deal_detail", args=[self.deal.id]))
        payment = Payment.objects.get(deal=self.deal)
        self.deal.refresh_from_db()
        self.assertEqual(payment.status, "pending_manual_verification")
        self.assertEqual(payment.payer, self.buyer)
        self.assertEqual(self.deal.status, "new")
        self.assertIsNone(self.deal.buyer)
        self.assertFalse(self.deal.buyer_approved)
