from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.models import Deal, DealMessage


class DealDetailAjaxTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller_ajax", password="pass123")
        self.buyer = User.objects.create_user(username="buyer_ajax", password="pass123")
        self.outsider = User.objects.create_user(username="outsider_ajax", password="pass123")
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Ajax Deal",
            product_description="Ajax coverage",
            price=Decimal("99.00"),
            status="reserved",
        )

    def test_party_can_send_deal_message_over_ajax_and_receive_payload(self):
        self.client.login(username="buyer_ajax", password="pass123")

        response = self.client.post(
            reverse("deal_detail", args=[self.deal.id]),
            {
                "message": "hello from ajax",
                "file": SimpleUploadedFile(
                    "proof.pdf",
                    b"%PDF-1.4 ajax deal attachment",
                    content_type="application/pdf",
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["text"], "hello from ajax")
        self.assertTrue(payload["file_url"].endswith("/attachment/"))

        message = DealMessage.objects.get(deal=self.deal, sender=self.buyer)
        self.assertEqual(payload["id"], message.id)

    def test_deal_detail_page_renders_with_poll_url(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("deal_detail", args=[self.deal.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("poll_deal_chat", args=[self.deal.id]))

    def test_poll_deal_chat_is_limited_to_parties(self):
        message = DealMessage.objects.create(
            deal=self.deal,
            sender=self.seller,
            text="secret deal note",
        )

        self.client.force_login(self.buyer)
        allowed_response = self.client.get(reverse("poll_deal_chat", args=[self.deal.id]))
        self.assertEqual(allowed_response.status_code, 200)
        allowed_payload = allowed_response.json()
        self.assertEqual(len(allowed_payload["messages"]), 1)
        self.assertEqual(allowed_payload["messages"][0]["id"], message.id)

        self.client.force_login(self.outsider)
        denied_response = self.client.get(reverse("poll_deal_chat", args=[self.deal.id]))
        self.assertEqual(denied_response.status_code, 403)
        if denied_response.headers.get("Content-Type", "").startswith("application/json"):
            self.assertEqual(denied_response.json()["messages"], [])
