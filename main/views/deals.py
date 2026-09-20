from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views.decorators.http import require_POST

from ..models import (
    Bid,
    Deal,
    DealComment,
    DealImage,
    DealMessage,
    Friendship,
    Payment,
    Review,
)
from ..i18n import get_request_language, get_translation
from ..deal_engine import execute as execute_deal_command
from ..utils import safe_file_url
from ..validators import validate_public_attachment
from .notifications import create_notification


def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _ajax_response(request, message, message_type="success", status=200, **extra):
    list(messages.get_messages(request))
    payload = {
        "status": "ok" if status < 400 else "error",
        "message": message,
        "message_type": message_type,
    }
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _locked_held_payment_for_deal(deal):
    payment = Payment.objects.select_for_update().filter(deal=deal).first()
    if payment and payment.status == "escrow_held":
        return payment
    return None


def _escrow_required_response(request, deal):
    message = "لا يمكن تنفيذ هذا الإجراء قبل احتجاز مبلغ الصفقة في الضمان."
    messages.error(request, message)
    if _is_ajax(request):
        return _ajax_response(request, message, "error", 400)
    return redirect("deal_detail", deal_id=deal.id)


def _secure_confirm_deal(request, deal_id):
    user = request.user
    with transaction.atomic():
        deal = get_object_or_404(
            Deal.objects.select_for_update(),
            id=deal_id,
        )

        if user != deal.buyer and user != deal.seller:
            message = "غير مسموح لك بهذا الإجراء."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 403)
            return redirect("my_deals")

        if not _locked_held_payment_for_deal(deal):
            return _escrow_required_response(request, deal)

        update_fields = []
        if user == deal.buyer and not deal.buyer_confirmed:
            deal.buyer_confirmed = True
            update_fields.append("buyer_confirmed")
        if user == deal.seller and not deal.seller_confirmed:
            deal.seller_confirmed = True
            update_fields.append("seller_confirmed")
        if update_fields:
            update_fields.append("updated_at")
            deal.save(update_fields=update_fields)

        should_release = deal.buyer_confirmed and deal.seller_confirmed

    if should_release:
        from .payments import PaymentStateError, release_payment_for_deal

        try:
            release_payment_for_deal(deal, buyer_confirmed=True)
        except PaymentStateError:
            return _escrow_required_response(request, deal)

        success_message = "تم اكتمال الصفقة وتحرير المبلغ للبائع."
        messages.success(request, success_message)
        if _is_ajax(request):
            return _ajax_response(request, success_message)
        return redirect("my_deals")

    success_message = "تم التأكيد وبانتظار الطرف الآخر."
    messages.success(request, success_message)
    if _is_ajax(request):
        return _ajax_response(request, success_message)
    return redirect("my_deals")


def build_deal_share_context(request, deal, share_price=None):
    primary_image = deal.images.first()
    share_image_path = safe_file_url(
        primary_image.image if primary_image else None,
        "images/brand/og-card.png",
    )
    share_description = Truncator(strip_tags(deal.product_description or "")).chars(160)
    if not share_description:
        share_description = get_translation(
            "share.default_description",
            get_request_language(request),
        )

    return {
        "share_title": f"{deal.product_title} - ${share_price}" if share_price else deal.product_title,
        "share_description": share_description,
        "share_image_url": request.build_absolute_uri(share_image_path),
        "share_url": request.build_absolute_uri(),
        "share_price": share_price,
    }


@login_required(login_url="login")
def deal_room(request):
    """Display all deals for the current user."""
    user = request.user
    deals = (
        Deal.objects.filter(Q(buyer=user) | Q(seller=user))
        .select_related("buyer__profile", "seller__profile")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    stats = {
        "total": deals.count(),
        "completed": deals.filter(status="completed").count(),
        "new": deals.filter(status="new").count(),
        "reserved": deals.filter(status="reserved").count(),
        "shipped": deals.filter(status="shipped").count(),
        "disputed": deals.filter(status="disputed").count(),
        "selling": deals.filter(seller=user).count(),
        "buying": deals.filter(buyer=user).count(),
        "active": deals.filter(status__in=["new", "reserved", "shipped", "disputed"]).count(),
    }
    return render(
        request,
        "deal_room.html",
        {
            "deals": deals,
            "stats": stats,
        },
    )

def deal_detail(request, deal_id):
    """صفحة تفاصيل الصفقة."""
    deal = get_object_or_404(Deal, id=deal_id)
    images = deal.images.all()
    comments = (
        deal.comments.filter(parent=None)
        .select_related("author__profile")
        .prefetch_related("replies__author__profile")
    )

    is_party = (
        request.user.is_authenticated
        and (request.user == deal.seller or request.user == deal.buyer)
    )
    messages_list = deal.messages.all().order_by("created_at") if is_party else None

    friendship_with_seller = None
    if request.user.is_authenticated and request.user != deal.seller:
        friendship_with_seller = Friendship.objects.filter(
            Q(from_user=request.user, to_user=deal.seller)
            | Q(from_user=deal.seller, to_user=request.user)
        ).first()

    is_friend_with_seller = bool(
        friendship_with_seller and friendship_with_seller.status == "accepted"
    )
    friend_request_sent = bool(
        friendship_with_seller
        and friendship_with_seller.status == "pending"
        and friendship_with_seller.from_user == request.user
    )

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "يجب تسجيل الدخول أولاً.")
            return redirect("login")

        if "add_comment" in request.POST:
            comment_text = request.POST.get("comment_text", "").strip()
            parent_id = request.POST.get("parent_id")
            if not comment_text:
                messages.error(request, "التعليق لا يمكن أن يكون فارغاً.")
            elif len(comment_text) > 1000:
                messages.error(request, "التعليق طويل جداً. الحد الأقصى هو 1000 حرف.")
            else:
                parent = get_object_or_404(DealComment, id=parent_id) if parent_id else None
                comment = DealComment.objects.create(
                    deal=deal,
                    author=request.user,
                    parent=parent,
                    text=comment_text,
                )
                if _is_ajax(request):
                    return JsonResponse(
                        {
                            "status": "ok",
                            "comment_id": comment.id,
                            "author": comment.author.username,
                            "avatar": safe_file_url(comment.author.profile.avatar),
                            "text": comment.text,
                            "is_reply": comment.is_reply,
                            "parent_id": comment.parent.id if comment.parent else None,
                        }
                    )
                messages.success(request, "تمت إضافة التعليق بنجاح.")
            return redirect("deal_detail", deal_id=deal.id)

        if is_party:
            text = request.POST.get("message", "").strip()
            file = request.FILES.get("file")
            if text or file:
                try:
                    validate_public_attachment(file)
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                    if _is_ajax(request):
                        return _ajax_response(request, exc.messages[0], "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)
                message = DealMessage.objects.create(
                    deal=deal,
                    sender=request.user,
                    text=text,
                    file=file,
                )
                if _is_ajax(request):
                    return JsonResponse(
                        {
                            "status": "ok",
                            "id": message.id,
                            "text": message.text,
                            "time": message.created_at.strftime("%H:%M"),
                            "avatar": safe_file_url(request.user.profile.avatar),
                            "username": request.user.username,
                            "file_url": reverse("deal_message_attachment", args=[message.id]) if message.file else "",
                        }
                    )

            if "approve_deal" in request.POST and not deal.buyer:
                if request.user == deal.seller:
                    messages.error(request, "لا يمكنك شراء صفقتك الخاصة.")
                    if _is_ajax(request):
                        return _ajax_response(request, "لا يمكنك شراء صفقتك الخاصة.", "error", 400)
                else:
                    with transaction.atomic():
                        locked_deal = Deal.objects.select_for_update().get(id=deal.id)
                        transition = execute_deal_command(
                            "reserve_deal",
                            deal=locked_deal,
                            actor=request.user,
                            request=request,
                            metadata={"source": "deal_detail"},
                        )
                        if transition.allowed:
                            locked_deal.buyer = request.user
                            locked_deal.buyer_approved = True
                            locked_deal.save(update_fields=["buyer", "buyer_approved", "updated_at"])
                            deal = locked_deal
                    if not transition.allowed:
                        messages.warning(request, "تعذر حجز الصفقة بسبب حالتها الحالية.")
                        if _is_ajax(request):
                            return _ajax_response(request, "تعذر حجز الصفقة بسبب حالتها الحالية.", "error", 400)
                        return redirect("deal_detail", deal_id=deal.id)
                    messages.success(request, "تم تأكيد الصفقة.")
                    if _is_ajax(request):
                        return _ajax_response(request, "تم تأكيد الصفقة.")

            elif "mark_shipped" in request.POST and request.user == deal.seller:
                if not (hasattr(deal, "payment") and deal.payment.status == "escrow_held"):
                    return _escrow_required_response(request, deal)
                try:
                    validate_public_attachment(request.FILES.get("shipping_proof"))
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                    if _is_ajax(request):
                        return _ajax_response(request, exc.messages[0], "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)
                with transaction.atomic():
                    locked_deal = Deal.objects.select_for_update().get(id=deal.id)
                    transition = execute_deal_command(
                        "start_delivery",
                        deal=locked_deal,
                        actor=request.user,
                        request=request,
                        metadata={"source": "deal_detail"},
                    )
                    if transition.allowed:
                        locked_deal.seller_shipped = True
                        locked_deal.shipping_proof = request.FILES.get("shipping_proof")
                        locked_deal.tracking_number = request.POST.get("tracking_number", "").strip()
                        locked_deal.save(update_fields=[
                            "seller_shipped",
                            "shipping_proof",
                            "tracking_number",
                            "updated_at",
                        ])
                        deal = locked_deal
                if not transition.allowed:
                    messages.warning(request, "لا يمكن بدء التسليم في الحالة الحالية للصفقة.")
                    if _is_ajax(request):
                        return _ajax_response(request, "لا يمكن بدء التسليم في الحالة الحالية للصفقة.", "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)
                messages.success(request, "تم تأكيد الشحن.")
                if deal.buyer:
                    create_notification(
                        recipient=deal.buyer,
                        notif_type="shipped",
                        title=f"🚚 تم شحن طلبك — {deal.product_title}",
                        body=f"قام البائع {deal.seller.username} بتأكيد الشحن.",
                        url=f"/deal/{deal.id}/",
                    )
                if _is_ajax(request):
                    return _ajax_response(request, "تم تأكيد الشحن.")

            elif "confirm_delivery" in request.POST and request.user == deal.buyer:
                if not (hasattr(deal, "payment") and deal.payment.status == "escrow_held"):
                    return _escrow_required_response(request, deal)

                create_notification(
                    recipient=deal.seller,
                    notif_type="delivered",
                    title=f"✅ تأكيد الاستلام — {deal.product_title}",
                    body=f"أكد {deal.buyer.username} استلام المنتج.",
                    url=f"/deal/{deal.id}/",
                )

                if hasattr(deal, "payment") and deal.payment.status == "escrow_held":
                    from .payments import PaymentStateError, release_payment_for_deal

                    try:
                        payment, _, _, _ = release_payment_for_deal(deal, buyer_confirmed=True)
                    except PaymentStateError:
                        error_message = "تعذر تحرير المبلغ لأن حالة الدفع لم تعد مناسبة."
                        messages.warning(request, error_message)
                        if _is_ajax(request):
                            return _ajax_response(request, error_message, "error", 400)
                    else:
                        success_message = (
                            f"✅ تم تأكيد الاستلام وتحرير ${payment.amount} للبائع {deal.seller.username}."
                        )
                        messages.success(request, success_message)
                        if _is_ajax(request):
                            return _ajax_response(request, success_message)
                else:
                    return _escrow_required_response(request, deal)

            elif "open_dispute" in request.POST and request.user == deal.buyer:
                if not (hasattr(deal, "payment") and deal.payment.status == "escrow_held"):
                    return _escrow_required_response(request, deal)
                dispute_reason = request.POST.get("dispute_reason", "").strip()
                if not dispute_reason:
                    messages.error(request, "يرجى كتابة سبب النزاع.")
                    if _is_ajax(request):
                        return _ajax_response(request, "يرجى كتابة سبب النزاع.", "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)

                try:
                    validate_public_attachment(request.FILES.get("dispute_evidence"))
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                    if _is_ajax(request):
                        return _ajax_response(request, exc.messages[0], "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)
                with transaction.atomic():
                    locked_deal = Deal.objects.select_for_update().get(id=deal.id)
                    transition = execute_deal_command(
                        "open_dispute",
                        deal=locked_deal,
                        actor=request.user,
                        request=request,
                        metadata={"source": "deal_detail", "reason": dispute_reason},
                    )
                    if transition.allowed:
                        locked_deal.dispute_reason = dispute_reason
                        locked_deal.dispute_evidence = request.FILES.get("dispute_evidence")
                        locked_deal.save(update_fields=["dispute_reason", "dispute_evidence", "updated_at"])
                        deal = locked_deal
                if not transition.allowed:
                    messages.warning(request, "لا يمكن فتح نزاع في الحالة الحالية للصفقة.")
                    if _is_ajax(request):
                        return _ajax_response(request, "لا يمكن فتح نزاع في الحالة الحالية للصفقة.", "error", 400)
                    return redirect("deal_detail", deal_id=deal.id)
                for admin in User.objects.filter(is_staff=True):
                    create_notification(
                        recipient=admin,
                        notif_type="dispute",
                        title=f"⚠️ نزاع جديد — {deal.product_title}",
                        body=f"فتح {deal.buyer.username} نزاعاً على الصفقة #{deal.id}.",
                        url=f"/escrow/{deal.id}/",
                    )
                messages.success(request, "تم فتح النزاع وسيتم مراجعته من الإدارة.")
                if _is_ajax(request):
                    return _ajax_response(request, "تم فتح النزاع وسيتم مراجعته من الإدارة.")

            return redirect("deal_detail", deal_id=deal_id)

    user_has_reviewed = False
    if request.user.is_authenticated and deal.status == "completed" and request.user == deal.buyer:
        user_has_reviewed = Review.objects.filter(deal=deal, reviewer=request.user).exists()

    return render(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "images": images,
            "comments": comments,
            "deal_messages": messages_list,
            "is_party": is_party,
            "is_friend_with_seller": is_friend_with_seller,
            "friend_request_sent": friend_request_sent,
            "user_has_reviewed": user_has_reviewed,
            **build_deal_share_context(request, deal, share_price=deal.price or deal.starting_price),
        },
    )


@login_required(login_url="login")
@require_POST
def confirm_deal(request, deal_id):
    """تأكيد الصفقة من كلا الطرفين (delegates to the secured implementation)."""
    return _secure_confirm_deal(request, deal_id)


@login_required(login_url="login")
@require_POST
def delete_deal(request, deal_id):
    """حذف العرض من قبل صاحبه."""
    deal = get_object_or_404(Deal, id=deal_id)

    if request.user != deal.seller:
        messages.error(request, "ليس لديك صلاحية حذف هذا العرض.")
        return redirect("deal_detail", deal_id=deal.id)

    if deal.status != "new":
        messages.error(request, "لا يمكن حذف عرض بعد قبول مشتري.")
        return redirect("deal_detail", deal_id=deal.id)

    deal.delete()
    messages.success(request, "تم حذف العرض بنجاح.")
    return redirect("listings")


def deal_auction_detail(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)
    bids = deal.bids.all().select_related("bidder__profile").order_by("-amount", "-created_at")
    is_expired = bool(
        (deal.auction_ends_at and deal.auction_ends_at < timezone.now())
        or deal.status in {"expired", "cancelled"}
    )
    highest_bid = bids.first() if bids.exists() else None
    share_price = highest_bid.amount if highest_bid else deal.starting_price

    return render(
        request,
        "deal_auction_detail.html",
        {
            "deal": deal,
            "bids": bids,
            "highest_bid": highest_bid,
            "is_expired": is_expired,
            **build_deal_share_context(request, deal, share_price=share_price),
        },
    )


@login_required(login_url="login")
def submit_bid(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)

    if not deal.is_auction:
        message = "هذه الصفقة ليست مزادًا."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 400)
        return redirect("deal_detail", deal_id=deal.id)

    if deal.status != "new":
        message = "هذا المزاد لم يعد متاحاً لاستقبال عروض جديدة."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 400)
        return redirect("deal_auction_detail", deal_id=deal.id)

    if deal.auction_ends_at and deal.auction_ends_at < timezone.now():
        message = "عذراً، انتهت المزايدة."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 400)
        return redirect("deal_auction_detail", deal_id=deal.id)

    if request.user == deal.seller:
        message = "لا يمكنك تقديم عرض على صفقتك الخاصة."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 400)
        return redirect("deal_auction_detail", deal_id=deal.id)

    if request.method == "POST":
        amount_str = request.POST.get("amount", "").strip()
        message_text = request.POST.get("message", "").strip()

        if not amount_str:
            message = "يرجى إدخال قيمة العرض."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_auction_detail", deal_id=deal.id)

        try:
            amount = Decimal(amount_str)
        except InvalidOperation:
            message = "قيمة العرض غير صحيحة."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_auction_detail", deal_id=deal.id)

        highest_bid = deal.bids.first()
        min_amount = (
            highest_bid.amount + deal.min_bid_increment if highest_bid else deal.starting_price
        )

        if amount < min_amount:
            message = f"العرض يجب أن يكون على الأقل ${min_amount}"
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_auction_detail", deal_id=deal.id)

        Bid.objects.create(deal=deal, bidder=request.user, amount=amount, message=message_text)
        success_message = f"تم تقديم عرضك: ${amount}"
        messages.success(request, success_message)
        if _is_ajax(request):
            return _ajax_response(request, success_message)

    return redirect("deal_auction_detail", deal_id=deal.id)


@login_required(login_url="login")
@require_POST
def accept_bid(request, bid_id):
    bid = get_object_or_404(Bid, id=bid_id)

    # All writes run inside one transaction with row locks, so a concurrent
    # accept_bid request (or the finalize_expired_auctions task) can never
    # double-sell the same auction. The legacy status write is kept because
    # the engine has no seller-permitted command from the "expired" state.
    with transaction.atomic():
        locked_deal = Deal.objects.select_for_update().get(id=bid.deal_id)
        locked_bid = Bid.objects.select_for_update().get(id=bid.id)

        if not locked_deal.is_auction:
            message = "لا يمكن قبول عرض لأن هذه الصفقة ليست مزادًا."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_detail", deal_id=locked_deal.id)

        if request.user != locked_deal.seller:
            message = "فقط البائع يمكنه قبول العروض."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 403)
            return redirect("deal_auction_detail", deal_id=locked_deal.id)

        if locked_deal.status not in {"new", "expired"} or locked_bid.is_accepted:
            message = "تم التعامل مع هذا العرض مسبقاً."
            messages.warning(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "warning", 400)
            return redirect("deal_auction_detail", deal_id=locked_deal.id)

        if locked_bid.bidder_id == locked_deal.seller_id:
            message = "لا يمكن قبول عرض البائع على مزاده الخاص."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_auction_detail", deal_id=locked_deal.id)

        if locked_deal.bids.filter(is_accepted=True).exclude(id=locked_bid.id).exists():
            message = "تم قبول عرض آخر على هذا المزاد مسبقاً."
            messages.warning(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "warning", 409)
            return redirect("deal_auction_detail", deal_id=locked_deal.id)

        locked_deal.bids.exclude(id=locked_bid.id).update(is_rejected=True)
        locked_bid.is_accepted = True
        locked_bid.save()

        locked_deal.buyer = locked_bid.bidder
        locked_deal.price = locked_bid.amount
        locked_deal.status = "reserved"
        locked_deal.save()

    create_notification(
        recipient=locked_bid.bidder,
        notif_type="bid_won",
        title=f"🎉 فزت بالمزايدة — {locked_deal.product_title}",
        body=f"تم قبول عرضك بمبلغ ${locked_bid.amount}.",
        url=f"/deal/{locked_deal.id}/",
    )

    success_message = f"تم قبول عرض {locked_bid.bidder.username} بمبلغ ${locked_bid.amount}"
    messages.success(request, success_message)
    if _is_ajax(request):
        return _ajax_response(request, success_message)
    return redirect("deal_detail", deal_id=locked_deal.id)


@login_required(login_url="login")
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(DealComment, id=comment_id)
    if request.user == comment.author or request.user.is_staff:
        deal_id = comment.deal.id
        comment.delete()
        messages.success(request, "تم حذف التعليق.")
        return redirect("deal_detail", deal_id=deal_id)

    messages.error(request, "غير مسموح لك بحذف هذا التعليق.")
    return redirect("deal_detail", deal_id=comment.deal.id)


@login_required(login_url="login")
def create_deal(request):
    """إنشاء صفقة جديدة مع نظام تصنيفات ذكي."""
    valid_categories = {c[0] for c in Deal.CATEGORY_CHOICES}
    valid_delivery_types = {d[0] for d in Deal.DELIVERY_CHOICES}

    # Map categories to their default delivery types
    category_delivery_defaults = {
        "games": "digital",
        "accounts": "digital",
        "services": "service",
        "electronics": "shipping",
        "digital": "digital",
        "physical": "shipping",
        "other": "shipping",
    }

    if request.method == "POST":
        # Collect all form data for preservation on error
        form_data = {
            "product_title": request.POST.get("product_title", "").strip(),
            "product_description": request.POST.get("product_description", "").strip(),
            "category": request.POST.get("category", "other").strip(),
            "delivery_type": request.POST.get("delivery_type", "").strip(),
            "platform": request.POST.get("platform", "").strip(),
            "delivery_time": request.POST.get("delivery_time", "").strip(),
            "deal_type": request.POST.get("deal_type", "fixed"),
            "price": request.POST.get("price", "").strip(),
            "starting_price": request.POST.get("starting_price", "").strip(),
            "min_bid_increment": request.POST.get("min_bid_increment", "5.00").strip(),
            "auction_ends_at": request.POST.get("auction_ends_at", "").strip(),
        }

        product_title = form_data["product_title"]
        product_description = form_data["product_description"]
        category = form_data["category"]
        is_auction = form_data["deal_type"] == "auction"

        # Validate category
        if category not in valid_categories:
            category = "other"

        # Determine delivery type from category if not explicitly set
        delivery_type = form_data["delivery_type"]
        if not delivery_type or delivery_type not in valid_delivery_types:
            delivery_type = category_delivery_defaults.get(category, "shipping")

        ctx = {"form_data": form_data}

        if not product_title or len(product_title) < 5:
            messages.error(request, "يرجى إدخال عنوان المنتج، 5 أحرف على الأقل.")
            return render(request, "create_deal_form.html", ctx)
        if not product_description:
            messages.error(request, "يرجى إدخال وصف المنتج.")
            return render(request, "create_deal_form.html", ctx)

        # Parse optional category-specific fields
        platform = form_data["platform"][:100] if form_data["platform"] else ""
        delivery_time_val = None
        if form_data["delivery_time"]:
            try:
                delivery_time_val = int(form_data["delivery_time"])
                if delivery_time_val <= 0 or delivery_time_val > 365:
                    delivery_time_val = None
            except (ValueError, TypeError):
                delivery_time_val = None

        try:
            if is_auction:
                starting_price = form_data["starting_price"]
                auction_ends_at = form_data["auction_ends_at"]
                min_bid_increment = form_data["min_bid_increment"]

                if not starting_price:
                    messages.error(request, "يرجى تحديد سعر البداية للمزايدة.")
                    return render(request, "create_deal_form.html", ctx)

                starting_price_dec = Decimal(starting_price)
                if starting_price_dec <= 0:
                    messages.error(request, "سعر البداية يجب أن يكون أكبر من صفر.")
                    return render(request, "create_deal_form.html", ctx)

                ends_dt = None
                if auction_ends_at:
                    from django.utils.dateparse import parse_datetime

                    ends_dt = parse_datetime(auction_ends_at)
                    if ends_dt and timezone.is_naive(ends_dt):
                        ends_dt = timezone.make_aware(ends_dt, timezone.get_current_timezone())
                    if ends_dt and ends_dt <= timezone.now():
                        messages.error(request, "تاريخ انتهاء المزايدة يجب أن يكون في المستقبل.")
                        return render(request, "create_deal_form.html", ctx)

                try:
                    increment = Decimal(min_bid_increment)
                    if increment <= 0:
                        increment = Decimal("5.00")
                except InvalidOperation:
                    increment = Decimal("5.00")

                deal = Deal.objects.create(
                    seller=request.user,
                    product_title=product_title,
                    product_description=product_description,
                    category=category,
                    delivery_type=delivery_type,
                    platform=platform,
                    delivery_time=delivery_time_val,
                    is_auction=True,
                    starting_price=starting_price_dec,
                    price=starting_price_dec,
                    auction_ends_at=ends_dt,
                    min_bid_increment=increment,
                    status="new",
                )
            else:
                price = form_data["price"]
                if not price:
                    messages.error(request, "يرجى تحديد السعر.")
                    return render(request, "create_deal_form.html", ctx)

                try:
                    price_dec = Decimal(price)
                except InvalidOperation:
                    messages.error(request, "السعر المدخل غير صحيح.")
                    return render(request, "create_deal_form.html", ctx)

                if price_dec <= 0:
                    messages.error(request, "السعر يجب أن يكون أكبر من صفر.")
                    return render(request, "create_deal_form.html", ctx)

                deal = Deal.objects.create(
                    seller=request.user,
                    product_title=product_title,
                    product_description=product_description,
                    category=category,
                    delivery_type=delivery_type,
                    platform=platform,
                    delivery_time=delivery_time_val,
                    price=price_dec,
                    is_auction=False,
                    status="new",
                )

            images = request.FILES.getlist("images")
            if len(images) > 10:
                messages.warning(request, "تم رفع أول 10 صور فقط.")
                images = images[:10]

            allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
            for image in images:
                if image.content_type in allowed_types:
                    DealImage.objects.create(deal=deal, image=image)

            messages.success(request, "تم إنشاء الصفقة بنجاح.")
            return redirect("deal_auction_detail" if is_auction else "deal_detail", deal_id=deal.id)
        except Exception:
            messages.error(request, "حدث خطأ أثناء إنشاء الصفقة. حاول مجدداً.")
            return render(request, "create_deal_form.html", ctx)

    return render(request, "create_deal_form.html")


@login_required(login_url="login")
def create_review(request, deal_id):
    """إضافة تقييم بعد اكتمال الصفقة."""
    deal = get_object_or_404(Deal, id=deal_id)

    if deal.status != "completed":
        message = "يمكنك التقييم فقط بعد اكتمال الصفقة."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 400)
        return redirect("deal_detail", deal_id=deal.id)

    if request.user != deal.buyer:
        message = "المشتري فقط يمكنه تقييم البائع."
        messages.error(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "error", 403)
        return redirect("deal_detail", deal_id=deal.id)

    if Review.objects.filter(deal=deal, reviewer=request.user).exists():
        message = "لقد قيّمت هذه الصفقة بالفعل."
        messages.warning(request, message)
        if _is_ajax(request):
            return _ajax_response(request, message, "warning", 400)
        return redirect("deal_detail", deal_id=deal.id)

    if request.method == "POST":
        rating = request.POST.get("rating")
        comment = request.POST.get("comment", "").strip()

        try:
            rating_val = int(rating)
            if not (1 <= rating_val <= 5):
                raise ValueError
        except (TypeError, ValueError):
            message = "قيمة التقييم غير صحيحة."
            messages.error(request, message)
            if _is_ajax(request):
                return _ajax_response(request, message, "error", 400)
            return redirect("deal_detail", deal_id=deal.id)

        Review.objects.create(
            deal=deal,
            reviewer=request.user,
            rated_user=deal.seller,
            rating=rating_val,
            comment=comment,
        )
        success_message = "شكراً لك، تمت إضافة تقييمك بنجاح."
        messages.success(request, success_message)
        if _is_ajax(request):
            return _ajax_response(request, success_message)
        return redirect("deal_detail", deal_id=deal.id)

    return redirect("deal_detail", deal_id=deal.id)
