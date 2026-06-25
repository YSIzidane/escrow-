from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from main.models import DealDeadline

from .permissions import ROLE_ADMIN, ROLE_BUYER, ROLE_SELLER
from .states import (
    STATE_CANCELLED,
    STATE_COMPLETED,
    STATE_DISPUTED,
    STATE_ESCROW_HELD,
    STATE_IN_DELIVERY,
    STATE_PAYMENT_PENDING,
    STATE_REFUNDED,
)


DEADLINE_RULES = {
    STATE_PAYMENT_PENDING: {
        "deadline_type": DealDeadline.TYPE_PAYMENT,
        "actor_role": ROLE_BUYER,
        "duration": timedelta(minutes=30),
    },
    STATE_ESCROW_HELD: {
        "deadline_type": DealDeadline.TYPE_DELIVERY,
        "actor_role": ROLE_SELLER,
        "duration": timedelta(hours=48),
    },
    STATE_IN_DELIVERY: {
        "deadline_type": DealDeadline.TYPE_RECEIPT,
        "actor_role": ROLE_BUYER,
        "duration": timedelta(hours=24),
    },
    STATE_DISPUTED: {
        "deadline_type": DealDeadline.TYPE_DISPUTE_RESPONSE,
        "actor_role": ROLE_ADMIN,
        "duration": timedelta(hours=24),
    },
}

TERMINAL_STATES = {STATE_CANCELLED, STATE_COMPLETED, STATE_REFUNDED}


def _complete_active_deadlines(deal, *, status=DealDeadline.STATUS_COMPLETED, exclude_type=""):
    active = deal.deadlines.filter(status=DealDeadline.STATUS_ACTIVE)
    if exclude_type:
        active = active.exclude(deadline_type=exclude_type)
    now = timezone.now()
    active.update(status=status, completed_at=now)


def sync_deadline_for_transition(*, deal, event, to_state):
    if to_state in TERMINAL_STATES:
        _complete_active_deadlines(deal, status=DealDeadline.STATUS_COMPLETED)
        return None

    rule = DEADLINE_RULES.get(to_state)
    if not rule:
        return None

    deadline_type = rule["deadline_type"]
    _complete_active_deadlines(deal, exclude_type=deadline_type)

    existing = deal.deadlines.filter(
        deadline_type=deadline_type,
        status=DealDeadline.STATUS_ACTIVE,
    ).first()
    if existing:
        return existing

    duration = rule["duration"]
    return DealDeadline.objects.create(
        deal=deal,
        deadline_type=deadline_type,
        actor_role=rule["actor_role"],
        state=to_state,
        due_at=timezone.now() + duration,
        source_event=event,
        metadata={
            "duration_seconds": int(duration.total_seconds()),
            "source": "deal_engine",
        },
    )
