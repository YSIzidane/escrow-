# ==================== Withdrawal Tests ====================
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from main.models import Notification, Profile, WithdrawalRequest
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups


class WithdrawalDisabledTests(TestCase):
    """Tests when WITHDRAWAL_ENABLED=False (default)."""

    def setUp(self):
        self.user = User.objects.create_user(username="user1", password="testpass123")
        self.profile = Profile.objects.get(user=self.user)
        self.profile.balance = Decimal("500.00")
        self.profile.kyc_status = "approved"
        self.profile.is_verified = True
        self.profile.save()
        self.client.login(username="user1", password="testpass123")

    @override_settings(WITHDRAWAL_ENABLED=False)
    def test_withdrawal_page_redirects_when_disabled(self):
        """Withdrawal page should redirect to profile when disabled."""
        response = self.client.get(reverse("request_withdrawal"))
        self.assertRedirects(response, reverse("profile"))

    @override_settings(WITHDRAWAL_ENABLED=False)
    def test_withdrawal_post_rejected_when_disabled(self):
        """POST to withdrawal should redirect when disabled."""
        response = self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(WithdrawalRequest.objects.count(), 0)


@override_settings(WITHDRAWAL_ENABLED=True)
class WithdrawalEnabledTests(TestCase):
    """Tests when WITHDRAWAL_ENABLED=True."""

    def setUp(self):
        self.user = User.objects.create_user(username="user1", password="testpass123")
        self.profile = Profile.objects.get(user=self.user)
        self.profile.balance = Decimal("500.00")
        self.profile.kyc_status = "approved"
        self.profile.is_verified = True
        self.profile.save()
        self.client.login(username="user1", password="testpass123")

    def test_successful_withdrawal(self):
        """Should create withdrawal and deduct balance."""
        response = self.client.post(
            reverse("request_withdrawal"),
            {"amount": "100.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertRedirects(response, reverse("request_withdrawal"))
        self.assertEqual(WithdrawalRequest.objects.count(), 1)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("400.00"))

        notification = Notification.objects.get(recipient=self.user)
        self.assertEqual(notification.notif_type, "withdrawal")
        self.assertEqual(notification.url, reverse("request_withdrawal"))

    def test_withdrawal_insufficient_balance(self):
        """Should reject withdrawal when amount exceeds balance."""
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "999.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("500.00"))

    def test_withdrawal_unverified_kyc(self):
        """Should reject withdrawal when KYC is not approved."""
        self.profile.kyc_status = "pending"
        self.profile.is_verified = False
        self.profile.save()

        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_withdrawal_rejects_without_verified_flag(self):
        """Should reject withdrawal if approval flag and verified flag are inconsistent."""
        self.profile.kyc_status = "approved"
        self.profile.is_verified = False
        self.profile.save()

        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_withdrawal_rejects_duplicate_pending_request(self):
        """Should prevent multiple pending requests for the same user."""
        self.user.refresh_from_db()
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal("60.00"),
            method="paypal",
            details="existing@paypal.com",
        )

        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 1)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("500.00"))

    def test_withdrawal_zero_amount(self):
        """Should reject zero or negative amounts."""
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "0", "method": "paypal", "details": "test@paypal.com"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_withdrawal_no_details(self):
        """Should reject withdrawal without account details."""
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": ""},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_withdrawal_rejects_invalid_paypal_email(self):
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "paypal", "details": "not-an-email"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_withdrawal_rejects_invalid_crypto_wallet(self):
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "50.00", "method": "crypto", "details": "bad-wallet"},
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_ajax_invalid_withdrawal_returns_json_error(self):
        response = self.client.post(
            reverse("request_withdrawal"),
            {"amount": "0", "method": "paypal", "details": "test@paypal.com"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("html", payload)
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_ajax_successful_withdrawal_returns_updated_shell(self):
        response = self.client.post(
            reverse("request_withdrawal"),
            {"amount": "75.00", "method": "paypal", "details": "test@paypal.com"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("html", payload)
        self.assertEqual(WithdrawalRequest.objects.count(), 1)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("425.00"))


@override_settings(WITHDRAWAL_ENABLED=True)
class WithdrawalAdminReviewTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.admin = User.objects.create_user(username="finance", password="financepass", is_staff=True)
        self.admin.groups.add(*list(self.admin.groups.model.objects.filter(name=ADMIN_ROLE_SPECS["finance_admin"]["name"])))

        self.user = User.objects.create_user(username="seller1", password="sellerpass")
        self.profile = Profile.objects.get(user=self.user)
        self.profile.balance = Decimal("300.00")
        self.profile.kyc_status = "approved"
        self.profile.is_verified = True
        self.profile.save()

        self.client.login(username="seller1", password="sellerpass")
        self.client.post(
            reverse("request_withdrawal"),
            {"amount": "120.00", "method": "paypal", "details": "seller@example.com"},
        )
        self.withdrawal = WithdrawalRequest.objects.get()
        self.client.logout()
        self.client.login(username="finance", password="financepass")

    def test_process_requires_payout_reference(self):
        response = self.client.post(
            reverse("admin_withdrawals_list"),
            {"req_id": self.withdrawal.id, "action": "process", "admin_note": "checked"},
        )

        self.assertRedirects(response, reverse("admin_withdrawals_list"))
        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "pending")
        self.assertEqual(self.withdrawal.payout_reference, "")

    def test_process_records_review_metadata(self):
        response = self.client.post(
            reverse("admin_withdrawals_list"),
            {
                "req_id": self.withdrawal.id,
                "action": "process",
                "payout_reference": "PAY-2026-0001",
                "admin_note": "Sent manually after reconciliation",
            },
        )

        self.assertRedirects(response, reverse("admin_withdrawals_list"))
        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "processed")
        self.assertEqual(self.withdrawal.payout_reference, "PAY-2026-0001")
        self.assertEqual(self.withdrawal.admin_note, "Sent manually after reconciliation")
        self.assertEqual(self.withdrawal.reviewed_by, self.admin)
        self.assertIsNotNone(self.withdrawal.reviewed_at)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("180.00"))

        notification = Notification.objects.filter(recipient=self.user).latest("created_at")
        self.assertEqual(notification.notif_type, "withdrawal")
        self.assertIn("approved", notification.title.lower())

    def test_reject_requires_reason(self):
        response = self.client.post(
            reverse("admin_withdrawals_list"),
            {"req_id": self.withdrawal.id, "action": "reject", "admin_note": "missing info"},
        )

        self.assertRedirects(response, reverse("admin_withdrawals_list"))
        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "pending")

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("180.00"))

    def test_reject_restores_balance_and_records_reason(self):
        response = self.client.post(
            reverse("admin_withdrawals_list"),
            {
                "req_id": self.withdrawal.id,
                "action": "reject",
                "rejection_reason": "Bank details do not match KYC record",
                "admin_note": "Asked user to resubmit details",
            },
        )

        self.assertRedirects(response, reverse("admin_withdrawals_list"))
        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "rejected")
        self.assertEqual(self.withdrawal.rejection_reason, "Bank details do not match KYC record")
        self.assertEqual(self.withdrawal.admin_note, "Asked user to resubmit details")
        self.assertEqual(self.withdrawal.reviewed_by, self.admin)
        self.assertIsNotNone(self.withdrawal.reviewed_at)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("300.00"))

        notification = Notification.objects.filter(recipient=self.user).latest("created_at")
        self.assertEqual(notification.notif_type, "withdrawal")
        self.assertIn("returned", notification.title.lower())

    def test_reviewed_request_cannot_be_rejected_twice(self):
        self.client.post(
            reverse("admin_withdrawals_list"),
            {
                "req_id": self.withdrawal.id,
                "action": "reject",
                "rejection_reason": "Initial rejection",
            },
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("300.00"))

        self.client.post(
            reverse("admin_withdrawals_list"),
            {
                "req_id": self.withdrawal.id,
                "action": "reject",
                "rejection_reason": "Second rejection should not apply",
            },
        )

        self.withdrawal.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "rejected")
        self.assertEqual(self.profile.balance, Decimal("300.00"))
