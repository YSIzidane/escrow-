from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from main.deal_engine import get_engine_state
from main.models import DealDeadline, Notification
from main.services.admin_roles import ADMIN_ROLE_SPECS


REMINDER_WINDOWS = {
    DealDeadline.TYPE_PAYMENT: timedelta(minutes=10),
    DealDeadline.TYPE_DELIVERY: timedelta(hours=6),
    DealDeadline.TYPE_RECEIPT: timedelta(hours=4),
    DealDeadline.TYPE_DISPUTE_RESPONSE: timedelta(hours=4),
}

AR_LABELS = {
    DealDeadline.TYPE_PAYMENT: "الدفع",
    DealDeadline.TYPE_DELIVERY: "بدء التسليم",
    DealDeadline.TYPE_RECEIPT: "تأكيد الاستلام",
    DealDeadline.TYPE_DISPUTE_RESPONSE: "الرد على النزاع",
}


@dataclass(frozen=True)
class DeadlineProcessingResult:
    reminders_sent: int = 0
    escalations_sent: int = 0
    expired: int = 0
    completed: int = 0

    def as_dict(self):
        return {
            "reminders_sent": self.reminders_sent,
            "escalations_sent": self.escalations_sent,
            "expired": self.expired,
            "completed": self.completed,
        }


def _admin_recipients():
    group_names = [
        ADMIN_ROLE_SPECS["operations_admin"]["name"],
        ADMIN_ROLE_SPECS["finance_admin"]["name"],
        ADMIN_ROLE_SPECS["security_admin"]["name"],
    ]
    return User.objects.filter(
        Q(is_superuser=True) | Q(groups__name__in=group_names),
        is_active=True,
        is_staff=True,
    ).distinct()


def _deadline_recipient(deadline):
    deal = deadline.deal
    if deadline.actor_role == "buyer":
        return deal.buyer
    if deadline.actor_role == "seller":
        return deal.seller
    return None


def _deadline_label(deadline):
    return AR_LABELS.get(deadline.deadline_type, "الإجراء المطلوب")


def _deadline_url(deadline):
    return f"/escrow/{deadline.deal_id}/"


def _create_notification(*, recipient, deadline, action, title, body, priority, actor=None, metadata=None):
    if not recipient:
        return None
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        deal=deadline.deal,
        notif_type="dispute" if deadline.deadline_type == DealDeadline.TYPE_DISPUTE_RESPONSE else "message",
        action=action,
        priority=priority,
        channel="in_app",
        title=title,
        body=body,
        url=_deadline_url(deadline),
        metadata={
            "deadline_id": deadline.id,
            "deadline_type": deadline.deadline_type,
            "due_at": deadline.due_at.isoformat(),
            **(metadata or {}),
        },
    )


def _send_reminder(deadline, now):
    label = _deadline_label(deadline)
    recipient = _deadline_recipient(deadline)
    if not recipient:
        return 0

    _create_notification(
        recipient=recipient,
        deadline=deadline,
        action=f"deadline_reminder_{deadline.deadline_type}",
        priority=Notification.PRIORITY_HIGH,
        title=f"تذكير: مهلة {label} اقتربت",
        body=f"تبقى وقت محدود قبل انتهاء مهلة {label} في الصفقة #{deadline.deal_id}.",
        metadata={"sent_at": now.isoformat()},
    )
    return 1


def _send_expiration(deadline, now):
    label = _deadline_label(deadline)
    sent = 0
    recipient = _deadline_recipient(deadline)
    if recipient:
        _create_notification(
            recipient=recipient,
            deadline=deadline,
            action=f"deadline_expired_{deadline.deadline_type}",
            priority=Notification.PRIORITY_HIGH,
            title=f"انتهت مهلة {label}",
            body=f"انتهت مهلة {label} في الصفقة #{deadline.deal_id}. تم تصعيد الحالة للمراجعة.",
            metadata={"expired_at": now.isoformat()},
        )
        sent += 1

    for admin in _admin_recipients():
        _create_notification(
            recipient=admin,
            deadline=deadline,
            action=f"deadline_escalated_{deadline.deadline_type}",
            priority=Notification.PRIORITY_CRITICAL,
            title=f"تصعيد مهلة منتهية: صفقة #{deadline.deal_id}",
            body=f"انتهت مهلة {label}. راجع غرفة الضمان وسجل الأحداث قبل اتخاذ القرار.",
            metadata={"expired_at": now.isoformat()},
        )
        sent += 1
    return sent


def _metadata_with(deadline, **updates):
    metadata = dict(deadline.metadata or {})
    metadata.update(updates)
    return metadata


def process_deal_deadlines(*, now=None, dry_run=False):
    now = now or timezone.now()
    reminders_sent = 0
    escalations_sent = 0
    expired = 0
    completed = 0

    deadline_ids = list(
        DealDeadline.objects.filter(status=DealDeadline.STATUS_ACTIVE)
        .values_list("id", flat=True)
    )

    for deadline_id in deadline_ids:
        with transaction.atomic():
            deadline = (
                DealDeadline.objects.select_for_update()
                .select_related("deal")
                .get(id=deadline_id)
            )
            if deadline.status != DealDeadline.STATUS_ACTIVE:
                continue

            current_state = get_engine_state(deadline.deal)
            if current_state != deadline.state:
                if not dry_run:
                    deadline.status = DealDeadline.STATUS_COMPLETED
                    deadline.completed_at = now
                    deadline.metadata = _metadata_with(
                        deadline,
                        completed_by_processor_at=now.isoformat(),
                        completed_reason="state_changed",
                        observed_state=current_state,
                    )
                    deadline.save(update_fields=["status", "completed_at", "metadata"])
                completed += 1
                continue

            metadata = dict(deadline.metadata or {})
            if deadline.due_at <= now:
                if not dry_run:
                    if not metadata.get("expired_notification_sent_at"):
                        escalations_sent += _send_expiration(deadline, now)
                        metadata["expired_notification_sent_at"] = now.isoformat()
                    deadline.status = DealDeadline.STATUS_EXPIRED
                    deadline.completed_at = now
                    deadline.metadata = metadata
                    deadline.save(update_fields=["status", "completed_at", "metadata"])
                expired += 1
                continue

            reminder_window = REMINDER_WINDOWS.get(deadline.deadline_type)
            should_remind = (
                reminder_window
                and deadline.due_at - now <= reminder_window
                and not metadata.get("reminder_sent_at")
            )
            if should_remind:
                if not dry_run:
                    reminders_sent += _send_reminder(deadline, now)
                    metadata["reminder_sent_at"] = now.isoformat()
                    deadline.metadata = metadata
                    deadline.save(update_fields=["metadata"])
                else:
                    reminders_sent += 1

    return DeadlineProcessingResult(
        reminders_sent=reminders_sent,
        escalations_sent=escalations_sent,
        expired=expired,
        completed=completed,
    )
