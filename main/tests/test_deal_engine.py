from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from main.deal_engine import (
    InvalidTransition,
    PermissionDeniedForTransition,
    execute,
    get_engine_state,
)
from main.models import Deal, DealDeadline, DealEvent, DealTransitionLog, Payment


class DealEngineTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", password="pass")
        self.buyer = User.objects.create_user(username="buyer", password="pass")
        self.admin = User.objects.create_user(username="admin", password="pass", is_staff=True)
        self.deal = Deal.objects.create(
            seller=self.seller,
            product_title="Secure engine deal",
            product_description="A deal used to test the state machine.",
            price=Decimal("120.00"),
            status="new",
        )

    def test_buyer_can_reserve_open_deal_and_event_is_recorded(self):
        result = execute(
            "reserve_deal",
            deal=self.deal,
            actor=self.buyer,
            metadata={"test": "reserve"},
        )

        self.deal.refresh_from_db()
        self.assertTrue(result.allowed)
        self.assertEqual(result.from_state, "open")
        self.assertEqual(result.to_state, "matched")
        self.assertEqual(self.deal.status, "reserved")
        self.assertEqual(DealEvent.objects.filter(deal=self.deal, event_type="deal_reserved").count(), 1)
        self.assertEqual(DealTransitionLog.objects.filter(deal=self.deal, allowed=True).count(), 1)

    def test_seller_cannot_reserve_own_deal_and_attempt_is_logged(self):
        with self.assertRaises(PermissionDeniedForTransition):
            execute(
                "reserve_deal",
                deal=self.deal,
                actor=self.seller,
                raise_on_error=True,
            )

        self.deal.refresh_from_db()
        log = DealTransitionLog.objects.get(deal=self.deal)
        self.assertEqual(self.deal.status, "new")
        self.assertFalse(log.allowed)
        self.assertEqual(log.reason, "permission_denied")
        self.assertEqual(DealEvent.objects.filter(deal=self.deal).count(), 0)

    def test_start_delivery_is_blocked_before_escrow_and_logged(self):
        with self.assertRaises(InvalidTransition):
            execute(
                "start_delivery",
                deal=self.deal,
                actor=self.seller,
                raise_on_error=True,
            )

        self.deal.refresh_from_db()
        log = DealTransitionLog.objects.get(deal=self.deal)
        self.assertEqual(self.deal.status, "new")
        self.assertFalse(log.allowed)
        self.assertEqual(log.reason, "invalid_transition")

    def test_seller_can_start_delivery_after_escrow_is_held(self):
        self.deal.buyer = self.buyer
        self.deal.status = "reserved"
        self.deal.save()
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=self.deal.price,
            status="escrow_held",
            transaction_id="txn-engine-held",
        )

        result = execute("start_delivery", deal=self.deal, actor=self.seller)

        self.deal.refresh_from_db()
        self.assertTrue(result.allowed)
        self.assertEqual(result.from_state, "escrow_held")
        self.assertEqual(result.to_state, "in_delivery")
        self.assertEqual(self.deal.status, "shipped")
        self.assertEqual(get_engine_state(self.deal), "in_delivery")
        self.assertEqual(DealEvent.objects.filter(deal=self.deal, event_type="delivery_started").count(), 1)

    def test_admin_can_refund_disputed_deal_without_rewriting_legacy_status(self):
        self.deal.buyer = self.buyer
        self.deal.status = "disputed"
        self.deal.save()

        result = execute("refund", deal=self.deal, actor=self.admin, save=False)

        self.deal.refresh_from_db()
        self.assertTrue(result.allowed)
        self.assertEqual(result.from_state, "disputed")
        self.assertEqual(result.to_state, "refunded")
        self.assertEqual(self.deal.status, "disputed")
        self.assertEqual(DealEvent.objects.filter(deal=self.deal, event_type="payment_refunded").count(), 1)

    def test_payment_held_transition_creates_delivery_deadline(self):
        self.deal.buyer = self.buyer
        self.deal.status = "reserved"
        self.deal.save()

        result = execute("payment_held", deal=self.deal, actor=self.buyer)

        self.assertTrue(result.allowed)
        deadline = DealDeadline.objects.get(deal=self.deal, deadline_type=DealDeadline.TYPE_DELIVERY)
        self.assertEqual(deadline.status, DealDeadline.STATUS_ACTIVE)
        self.assertEqual(deadline.actor_role, "seller")
        self.assertEqual(deadline.source_event_id, result.event_id)
