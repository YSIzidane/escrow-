from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Deal
from .services.deal_deadline_service import process_deal_deadlines
from .views.notifications import create_notification


@shared_task
def finalize_expired_auctions():
    now = timezone.now()
    expired_with_bids = 0
    cancelled_without_bids = 0

    auction_ids = list(
        Deal.objects.filter(
            is_auction=True,
            status="new",
            auction_ends_at__isnull=False,
            auction_ends_at__lte=now,
        ).values_list("id", flat=True)
    )

    for deal_id in auction_ids:
        highest_bid = None
        seller = None

        with transaction.atomic():
            deal = (
                Deal.objects.select_for_update()
                .select_related("seller")
                .prefetch_related("bids__bidder")
                .get(id=deal_id)
            )

            if deal.status != "new" or not deal.auction_ends_at or deal.auction_ends_at > now:
                continue

            highest_bid = deal.bids.order_by("-amount", "-created_at").select_related("bidder").first()
            seller = deal.seller

            if highest_bid:
                deal.status = "expired"
                expired_with_bids += 1
            else:
                deal.status = "cancelled"
                cancelled_without_bids += 1
            deal.save()

        if highest_bid:
            create_notification(
                recipient=seller,
                notif_type="message",
                title=f"انتهت المزايدة — {deal.product_title}",
                body=f"انتهى وقت المزاد، وأعلى عرض حالي هو ${highest_bid.amount} من {highest_bid.bidder.username}.",
                url=f"/deal/auction/{deal.id}/",
            )
            create_notification(
                recipient=highest_bid.bidder,
                notif_type="message",
                title=f"انتهت المزايدة — {deal.product_title}",
                body="انتهى المزاد، وسيقوم البائع الآن بمراجعة أعلى العروض واختيار العرض المناسب.",
                url=f"/deal/auction/{deal.id}/",
            )
        else:
            create_notification(
                recipient=seller,
                notif_type="message",
                title=f"انتهت المزايدة بدون عروض — {deal.product_title}",
                body="انتهى وقت المزاد بدون أي عروض جديدة، وتم إغلاقه تلقائيًا.",
                url=f"/deal/auction/{deal.id}/",
            )

    return {
        "expired_with_bids": expired_with_bids,
        "cancelled_without_bids": cancelled_without_bids,
    }


@shared_task
def process_deal_deadline_notifications():
    return process_deal_deadlines().as_dict()
