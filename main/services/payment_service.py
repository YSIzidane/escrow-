# ==================== Payment Service Layer ====================
"""
Shared business logic for processing successful payments.
Used by both Stripe Webhook and CCP Admin Approval to ensure
consistent behavior across all payment methods.
"""
import uuid
import logging

from django.db import transaction

from ..models import Deal, Payment, EscrowRoom, EscrowMessage
from ..deal_engine import execute as execute_deal_command

logger = logging.getLogger(__name__)


def process_successful_payment(deal, buyer, transaction_id=None, payment_method="stripe"):
    """
    Processes a successful payment for a deal.
    This is the SINGLE source of truth for transitioning a payment to escrow_held.

    Called by:
    - Stripe Webhook (checkout.session.completed)
    - CCP Admin Approval (staff_approve_ccp)

    Returns: (payment, deal)
    """
    from ..views.notifications import create_notification

    with transaction.atomic():
        locked_deal = Deal.objects.select_for_update().get(id=deal.id)

        existing_payment = getattr(locked_deal, "payment", None)
        if existing_payment:
            locked_payment = Payment.objects.select_for_update().get(id=existing_payment.id)
            if locked_payment.status in {"escrow_held", "released", "refunded"}:
                logger.warning(
                    "process_successful_payment: deal %s already finalized with payment status %s, skipping.",
                    deal.id,
                    locked_payment.status,
                )
                return locked_payment, locked_deal
            if locked_payment.status not in {"pending", "pending_manual_verification", "failed"}:
                logger.warning(
                    "process_successful_payment: deal %s is in unexpected payment status %s, skipping.",
                    deal.id,
                    locked_payment.status,
                )
                return locked_payment, locked_deal

        if not transaction_id:
            transaction_id = f"CCP-{uuid.uuid4().hex[:12].upper()}"

        payment, _ = Payment.objects.update_or_create(
            deal=locked_deal,
            defaults={
                "payer": buyer,
                "amount": locked_deal.price,
                "status": "escrow_held",
                "transaction_id": transaction_id,
                "payment_method": payment_method,
            },
        )

        locked_deal.buyer = buyer
        locked_deal.buyer_approved = True
        locked_deal.save(update_fields=["buyer", "buyer_approved", "updated_at"])
        execute_deal_command(
            "payment_held",
            deal=locked_deal,
            actor=buyer,
            metadata={
                "source": "process_successful_payment",
                "payment_id": payment.id,
                "payment_method": payment_method,
                "amount": str(locked_deal.price),
            },
            raise_on_error=True,
        )

    # Notifications (outside atomic block)
    create_notification(
        recipient=locked_deal.seller,
        notif_type="payment",
        title=f"💰 دفع جديد — {locked_deal.product_title}",
        body=f"قام {buyer.username} بدفع ${locked_deal.price} واحتجازه في Escrow.",
        url=f"/escrow/{locked_deal.id}/",
    )

    # Create/open Escrow Room
    room, _ = EscrowRoom.objects.get_or_create(deal=locked_deal)
    EscrowMessage.objects.get_or_create(
        room=room,
        sender=buyer,
        defaults={
            "text": f"✅ تم احتجاز ${locked_deal.price} في Escrow. الغرفة مفتوحة للتواصل.",
            "is_admin": False,
        },
    )

    logger.info("process_successful_payment: deal %s payment confirmed (%s).", deal.id, payment_method)
    return payment, locked_deal
