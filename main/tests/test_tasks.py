from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from main.models import Bid, Deal, Notification
from main.tasks import finalize_expired_auctions


class FinalizeExpiredAuctionsTests(TestCase):
    def test_expired_auction_with_bids_is_marked_expired_and_notifies_users(self):
        seller = User.objects.create_user(username="seller", password="x")
        bidder = User.objects.create_user(username="bidder", password="x")
        deal = Deal.objects.create(
            seller=seller,
            product_title="Auction Deal",
            product_description="Auction description",
            is_auction=True,
            starting_price="100.00",
            price="100.00",
            auction_ends_at=timezone.now() - timedelta(minutes=5),
            status="new",
        )
        Bid.objects.create(deal=deal, bidder=bidder, amount="120.00")

        result = finalize_expired_auctions()

        deal.refresh_from_db()
        self.assertEqual(deal.status, "expired")
        self.assertEqual(result["expired_with_bids"], 1)
        self.assertEqual(Notification.objects.filter(recipient=seller).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=bidder).count(), 1)

    def test_expired_auction_without_bids_is_cancelled(self):
        seller = User.objects.create_user(username="seller2", password="x")
        deal = Deal.objects.create(
            seller=seller,
            product_title="No Bid Auction",
            product_description="Auction description",
            is_auction=True,
            starting_price="80.00",
            price="80.00",
            auction_ends_at=timezone.now() - timedelta(minutes=5),
            status="new",
        )

        result = finalize_expired_auctions()

        deal.refresh_from_db()
        self.assertEqual(deal.status, "cancelled")
        self.assertEqual(result["cancelled_without_bids"], 1)
        self.assertEqual(Notification.objects.filter(recipient=seller).count(), 1)
