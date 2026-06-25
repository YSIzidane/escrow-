from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Deal


class ShareExperienceTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="x")
        self.fixed_deal = Deal.objects.create(
            seller=self.seller,
            product_title="Gaming Account",
            product_description="Trusted fixed-price listing for testing share previews.",
            price=Decimal("50.00"),
            status="new",
        )
        self.auction_deal = Deal.objects.create(
            seller=self.seller,
            product_title="Rare Skin Bundle",
            product_description="Auction listing for public preview coverage.",
            is_auction=True,
            starting_price=Decimal("25.00"),
            auction_ends_at=timezone.now() + timedelta(days=2),
            status="new",
        )

    def test_home_page_renders_default_share_meta_and_network_overlay_in_arabic(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'property="og:locale" content="ar_AR"', html=False)
        self.assertContains(
            response,
            'property="og:image" content="http://testserver/static/images/brand/og-card.png"',
            html=False,
        )
        self.assertContains(response, 'id="se-network-overlay"', html=False)
        self.assertContains(response, 'aria-label="القائمة"', html=False)
        self.assertContains(response, "دليل الاستخدام")

    def test_home_page_switches_small_ui_labels_to_english(self):
        self.client.cookies["site_language"] = "en"

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'property="og:locale" content="en_US"', html=False)
        self.assertContains(response, 'aria-label="Menu"', html=False)
        self.assertContains(response, ">Guide<", html=False)

    def test_public_info_pages_use_full_english_translations(self):
        self.client.cookies["site_language"] = "en"

        about_response = self.client.get(reverse("about"))
        guide_response = self.client.get(reverse("how_it_works"))

        self.assertEqual(about_response.status_code, 200)
        self.assertContains(about_response, "User guide")
        self.assertContains(about_response, "Fees and commission")
        self.assertContains(about_response, "Create a report")

        self.assertEqual(guide_response.status_code, 200)
        self.assertContains(guide_response, "How It Works")
        self.assertContains(guide_response, "Browse listings")
        self.assertContains(guide_response, "Important warnings")

    def test_user_profile_page_uses_translated_listing_labels(self):
        self.client.cookies["site_language"] = "en"
        viewer = User.objects.create_user(username="viewer", password="x")
        self.client.force_login(viewer)

        response = self.client.get(reverse("user_profile", args=[self.seller.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Latest listings")
        self.assertContains(response, "active listings")
        self.assertContains(response, "View details")

    def test_fixed_deal_detail_includes_share_panel_and_product_meta(self):
        response = self.client.get(reverse("deal_detail", args=[self.fixed_deal.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مشاركة هذه الصفحة")
        self.assertContains(response, 'data-share-native', html=False)
        self.assertContains(response, 'property="product:price:amount" content="50.00"', html=False)

    def test_auction_detail_is_public_and_includes_share_actions(self):
        response = self.client.get(reverse("deal_auction_detail", args=[self.auction_deal.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.seller.username)
        self.assertContains(response, "نسخ الرابط")
        self.assertContains(response, 'property="product:price:amount" content="25.00"', html=False)
