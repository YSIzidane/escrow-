from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.models import Deal, DealMessage, Payment, PrivateMessage, Profile, SupportTicket, TicketReply
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups


class SensitiveMediaAccessTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.operations_group = Group.objects.get(name=ADMIN_ROLE_SPECS["operations_admin"]["name"])
        self.finance_group = Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"])
        self.support_group = Group.objects.get(name=ADMIN_ROLE_SPECS["support_admin"]["name"])

        self.operations_admin = User.objects.create_user(
            username="ops_admin",
            password="opspass",
            is_staff=True,
        )
        self.operations_admin.groups.add(self.operations_group)

        self.finance_admin = User.objects.create_user(
            username="finance_admin",
            password="financepass",
            is_staff=True,
        )
        self.finance_admin.groups.add(self.finance_group)

        self.support_admin = User.objects.create_user(
            username="support_admin",
            password="supportpass",
            is_staff=True,
        )
        self.support_admin.groups.add(self.support_group)

        self.regular_user = User.objects.create_user(
            username="regular",
            password="regularpass",
        )

        self.seller = User.objects.create_user(
            username="seller_sensitive",
            password="sellerpass",
        )
        self.buyer = User.objects.create_user(
            username="buyer_sensitive",
            password="buyerpass",
        )

        self.profile = Profile.objects.get(user=self.seller)
        self.profile.kyc_document = SimpleUploadedFile(
            "identity.pdf",
            b"%PDF-1.4 test kyc document",
            content_type="application/pdf",
        )
        self.profile.kyc_status = "pending"
        self.profile.save()

        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Sensitive Payment",
            product_description="Payment proof test",
            price=Decimal("50.00"),
            status="reserved",
        )
        self.payment = Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=Decimal("50.00"),
            status="pending_manual_verification",
            payment_method="ccp",
            transaction_id="CCP-PROOF-001",
            proof_file=SimpleUploadedFile(
                "proof.png",
                b"fake image bytes",
                content_type="image/png",
            ),
            reference_number="REF-123",
        )
        self.private_message = PrivateMessage.objects.create(
            sender=self.seller,
            receiver=self.buyer,
            text="private attachment",
            file=SimpleUploadedFile(
                "chat-note.pdf",
                b"%PDF-1.4 private attachment",
                content_type="application/pdf",
            ),
        )
        self.ticket = SupportTicket.objects.create(
            user=self.seller,
            subject="Attachment ticket",
            description="Need help",
            attachment=SimpleUploadedFile(
                "ticket-proof.pdf",
                b"%PDF-1.4 ticket attachment",
                content_type="application/pdf",
            ),
        )
        self.ticket_reply = TicketReply.objects.create(
            ticket=self.ticket,
            sender=self.support_admin,
            message="Here is the reply attachment",
            is_staff_reply=True,
            attachment=SimpleUploadedFile(
                "reply-proof.pdf",
                b"%PDF-1.4 reply attachment",
                content_type="application/pdf",
            ),
        )
        self.deal_message = DealMessage.objects.create(
            deal=self.deal,
            sender=self.seller,
            text="deal attachment",
            file=SimpleUploadedFile(
                "deal-note.pdf",
                b"%PDF-1.4 deal attachment",
                content_type="application/pdf",
            ),
        )

    def test_operations_admin_can_open_kyc_document(self):
        self.client.login(username="ops_admin", password="opspass")
        response = self.client.get(reverse("admin_kyc_document", args=[self.profile.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_finance_admin_cannot_open_kyc_document(self):
        self.client.login(username="finance_admin", password="financepass")
        response = self.client.get(reverse("admin_kyc_document", args=[self.profile.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_finance_admin_can_open_payment_proof(self):
        self.client.login(username="finance_admin", password="financepass")
        response = self.client.get(reverse("staff_payment_proof", args=[self.payment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_operations_admin_cannot_open_payment_proof(self):
        self.client.login(username="ops_admin", password="opspass")
        response = self.client.get(reverse("staff_payment_proof", args=[self.payment.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_regular_user_cannot_open_sensitive_files(self):
        self.client.login(username="regular", password="regularpass")

        kyc_response = self.client.get(reverse("admin_kyc_document", args=[self.profile.id]))
        proof_response = self.client.get(reverse("staff_payment_proof", args=[self.payment.id]))

        self.assertIn(kyc_response.status_code, (302, 403))
        self.assertIn(proof_response.status_code, (302, 403))

    def test_private_message_attachment_is_limited_to_chat_participants(self):
        self.client.login(username="buyer_sensitive", password="buyerpass")
        allowed_response = self.client.get(reverse("private_message_attachment", args=[self.private_message.id]))
        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(allowed_response["X-Content-Type-Options"], "nosniff")

        self.client.login(username="regular", password="regularpass")
        denied_response = self.client.get(reverse("private_message_attachment", args=[self.private_message.id]))
        self.assertEqual(denied_response.status_code, 404)

    def test_support_ticket_attachments_are_limited_to_owner_and_support_admin(self):
        self.client.login(username="seller_sensitive", password="sellerpass")
        owner_response = self.client.get(reverse("ticket_attachment", args=[self.ticket.id]))
        self.assertEqual(owner_response.status_code, 200)

        reply_owner_response = self.client.get(reverse("ticket_reply_attachment", args=[self.ticket_reply.id]))
        self.assertEqual(reply_owner_response.status_code, 200)

        self.client.login(username="support_admin", password="supportpass")
        support_response = self.client.get(reverse("ticket_attachment", args=[self.ticket.id]))
        self.assertEqual(support_response.status_code, 200)

        reply_support_response = self.client.get(reverse("ticket_reply_attachment", args=[self.ticket_reply.id]))
        self.assertEqual(reply_support_response.status_code, 200)

        self.client.login(username="regular", password="regularpass")
        denied_response = self.client.get(reverse("ticket_attachment", args=[self.ticket.id]))
        self.assertEqual(denied_response.status_code, 404)

    def test_deal_message_attachment_is_limited_to_parties_and_authorized_admins(self):
        self.client.login(username="buyer_sensitive", password="buyerpass")
        buyer_response = self.client.get(reverse("deal_message_attachment", args=[self.deal_message.id]))
        self.assertEqual(buyer_response.status_code, 200)

        self.client.login(username="ops_admin", password="opspass")
        admin_response = self.client.get(reverse("deal_message_attachment", args=[self.deal_message.id]))
        self.assertEqual(admin_response.status_code, 200)

        self.client.login(username="support_admin", password="supportpass")
        denied_response = self.client.get(reverse("deal_message_attachment", args=[self.deal_message.id]))
        self.assertEqual(denied_response.status_code, 404)


class SensitiveUploadValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="uploader", password="pass123")
        self.other = User.objects.create_user(username="receiver", password="pass123")

    def test_reject_invalid_private_message_file(self):
        with self.assertRaises(ValidationError):
            PrivateMessage.objects.create(
                sender=self.user,
                receiver=self.other,
                text="see attachment",
                file=SimpleUploadedFile("payload.html", b"<script>alert(1)</script>", content_type="text/html"),
            )

    def test_reject_invalid_ticket_attachment_extension(self):
        with self.assertRaises(ValidationError):
            SupportTicket.objects.create(
                user=self.user,
                subject="Bad attachment",
                description="Testing file validation",
                attachment=SimpleUploadedFile("payload.js", b"alert(1)", content_type="application/javascript"),
            )
