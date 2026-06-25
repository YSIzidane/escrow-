from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from main.models import Deal, DealDeadline, Notification, Payment
from main.services.deal_deadline_service import process_deal_deadlines


class DealDeadlineServiceTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="deadline_seller", password="pass")
        self.buyer = User.objects.create_user(username="deadline_buyer", password="pass")
        self.admin = User.objects.create_user(
            username="deadline_admin",
            password="pass",
            is_staff=True,
            is_superuser=True,
        )
        self.deal = Deal.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            product_title="Deadline protected deal",
            product_description="Deadline service coverage",
            price=Decimal("150.00"),
            status="reserved",
        )
        Payment.objects.create(
            deal=self.deal,
            payer=self.buyer,
            amount=self.deal.price,
            status="escrow_held",
            transaction_id="txn_deadline_service",
        )

    def _delivery_deadline(self, due_at):
        return DealDeadline.objects.create(
            deal=self.deal,
            deadline_type=DealDeadline.TYPE_DELIVERY,
            actor_role="seller",
            state="escrow_held",
            due_at=due_at,
            metadata={"duration_seconds": 48 * 60 * 60},
        )

    def test_due_soon_deadline_sends_one_reminder_to_actor(self):
        now = timezone.now()
        deadline = self._delivery_deadline(now + timedelta(hours=2))

        result = process_deal_deadlines(now=now)
        second_result = process_deal_deadlines(now=now + timedelta(minutes=1))

        deadline.refresh_from_db()
        notification = Notification.objects.get(
            recipient=self.seller,
            action="deadline_reminder_delivery",
        )
        self.assertEqual(result.reminders_sent, 1)
        self.assertEqual(second_result.reminders_sent, 0)
        self.assertEqual(notification.deal, self.deal)
        self.assertEqual(notification.priority, Notification.PRIORITY_HIGH)
        self.assertIn("reminder_sent_at", deadline.metadata)

    def test_expired_deadline_escalates_to_actor_and_admin_once(self):
        now = timezone.now()
        deadline = self._delivery_deadline(now - timedelta(minutes=5))

        result = process_deal_deadlines(now=now)
        second_result = process_deal_deadlines(now=now + timedelta(minutes=1))

        deadline.refresh_from_db()
        self.assertEqual(result.expired, 1)
        self.assertEqual(result.escalations_sent, 2)
        self.assertEqual(second_result.expired, 0)
        self.assertEqual(deadline.status, DealDeadline.STATUS_EXPIRED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.seller,
                action="deadline_expired_delivery",
                deal=self.deal,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                action="deadline_escalated_delivery",
                priority=Notification.PRIORITY_CRITICAL,
                deal=self.deal,
            ).exists()
        )

    def test_deadline_is_completed_when_deal_state_changed(self):
        now = timezone.now()
        deadline = self._delivery_deadline(now + timedelta(hours=2))
        self.deal.status = "shipped"
        self.deal.save(update_fields=["status", "updated_at"])

        result = process_deal_deadlines(now=now)

        deadline.refresh_from_db()
        self.assertEqual(result.completed, 1)
        self.assertEqual(deadline.status, DealDeadline.STATUS_COMPLETED)
        self.assertEqual(Notification.objects.filter(deal=self.deal).count(), 0)

    def test_management_command_supports_dry_run(self):
        self._delivery_deadline(timezone.now() + timedelta(hours=2))
        output = StringIO()

        call_command("process_deal_deadlines", "--dry-run", stdout=output)

        self.assertIn("Processed deal deadlines", output.getvalue())
        self.assertEqual(Notification.objects.filter(deal=self.deal).count(), 0)
