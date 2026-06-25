# ==================== Chat & Room Views ====================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..deal_engine import build_deal_room_context, execute as execute_deal_command
from ..i18n import get_request_language
from ..models import (
    Deal,
    DealEvidence,
    EscrowMessage,
    EscrowRoom,
    Friendship,
    PrivateMessage,
    Room,
    RoomMessage,
    RoomParticipant,
    TradeExchange,
)
from ..services.admin_roles import has_any_admin_role, has_role_or_legacy_staff
from ..services.verification import render_verification_badge
from ..utils import safe_file_url
from ..validators import validate_public_attachment
from .notifications import create_notification


@login_required(login_url="login")
def chat_hub(request):
    friends = _accepted_friends_for(request.user)
    return render(request, "chat_hub.html", {
        "friends": friends,
        "friends_count": friends.count(),
    })


def _accepted_friends_for(user):
    return (
        User.objects.filter(
            Q(friendships_received__from_user=user, friendships_received__status="accepted")
            | Q(friendships_sent__to_user=user, friendships_sent__status="accepted")
        )
        .distinct()
        .select_related("profile")
        .annotate(published_deals_count=Count("seller_deals", distinct=True))
        .order_by("username")
    )


@login_required(login_url="login")
def private_chat(request, friend_id):
    friend = get_object_or_404(User, id=friend_id)
    if request.user == friend:
        messages.error(request, "لا يمكنك فتح محادثة مع نفسك.")
        return redirect("chat_hub")

    is_friend = Friendship.objects.filter(
        (Q(from_user=request.user, to_user=friend) | Q(from_user=friend, to_user=request.user)),
        status="accepted",
    ).exists()
    if not is_friend:
        messages.error(request, "يجب أن تكونا صديقين لفتح المحادثة الخاصة.")
        return redirect("friends_list")

    messages_list = PrivateMessage.objects.filter(
        Q(sender=request.user, receiver=friend) | Q(sender=friend, receiver=request.user)
    ).order_by("created_at")

    if request.method == "POST":
        text = request.POST.get("message", "").strip()
        file = request.FILES.get("file")
        if not text and not file:
            return redirect("private_chat", friend_id=friend_id)
        if text and len(text) > 2000:
            messages.error(request, "الرسالة طويلة جدا. الحد الأقصى هو 2000 حرف.")
            return redirect("private_chat", friend_id=friend_id)

        try:
            validate_public_attachment(file)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("private_chat", friend_id=friend_id)

        msg = PrivateMessage.objects.create(sender=request.user, receiver=friend, text=text, file=file)
        create_notification(
            recipient=friend,
            notif_type="message",
            title=f"رسالة جديدة من {request.user.username}",
            body=f"{text[:50]}..." if text else "أرسل لك ملفا مرفقا.",
            url=f"/chat/{request.user.id}/",
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "status": "ok",
                    "id": msg.id,
                    "text": msg.text,
                    "time": msg.created_at.strftime("%H:%M"),
                    "avatar": safe_file_url(request.user.profile.avatar),
                    "is_me": True,
                    "username": request.user.username,
                    "verification_badge": render_verification_badge(request.user.profile),
                    "file_url": reverse("private_message_attachment", args=[msg.id]) if msg.file else "",
                }
            )
        return redirect("private_chat", friend_id=friend_id)

    return render(
        request,
        "private_chat.html",
        {"friend": friend, "friends": _accepted_friends_for(request.user), "chat_messages": messages_list},
    )


def _get_room_by_code(code):
    room = get_object_or_404(
        Room.objects.select_related("creator__profile").prefetch_related("participants__user__profile"),
        code__iexact=code,
    )
    RoomParticipant.objects.get_or_create(
        room=room,
        user=room.creator,
        defaults={"role": "owner"},
    )
    return room


def _ensure_room_access(request, room):
    if room.can_user_access(request.user):
        return None
    messages.error(request, "هذه الغرفة خاصة ولا يمكنك دخولها إلا إذا دعاك صاحبها.")
    return redirect("join_room")


def _system_room_message(room, user, text):
    RoomMessage.objects.create(room=room, sender=user, text=text)


def _notify_trade_dispute(room, reason):
    for staff_user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            recipient=staff_user,
            notif_type="dispute",
            title=f"نزاع تبديل في الغرفة {room.code}",
            body=(reason or "طلب أحد الطرفين تدخل الإدارة.")[:240],
            url=f"/rooms/{room.code}/",
        )


def _notify_trade_partner(room, actor, title, body):
    recipients = (
        participant.user
        for participant in room.participants.select_related("user")
        if participant.user_id != actor.id
    )
    for recipient in recipients:
        create_notification(
            recipient=recipient,
            notif_type="message",
            title=title,
            body=body[:240],
            url=f"/rooms/{room.code}/",
        )


@login_required(login_url="login")
def create_room(request):
    if request.method == "POST":
        room_type = request.POST.get("type")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        if room_type not in ["buy", "sell", "trade"]:
            messages.error(request, "نوع الغرفة غير صحيح.")
            return render(request, "create_room.html", {"form_data": request.POST})
        if not title:
            messages.error(request, "يرجى كتابة عنوان واضح للغرفة.")
            return render(request, "create_room.html", {"form_data": request.POST})
        if len(title) > 120:
            messages.error(request, "عنوان الغرفة طويل جدًا.")
            return render(request, "create_room.html", {"form_data": request.POST})
        if len(description) > 1000:
            messages.error(request, "وصف الغرفة طويل جدًا.")
            return render(request, "create_room.html", {"form_data": request.POST})

        with transaction.atomic():
            room = Room.objects.create(
                creator=request.user,
                room_type=room_type,
                title=title,
                description=description,
            )
            RoomParticipant.objects.get_or_create(
                room=room,
                user=request.user,
                defaults={"role": "owner"},
            )

        messages.success(request, f"تم إنشاء الغرفة بنجاح. رمز الدعوة: {room.code}")
        return redirect("room_detail", room.code)
    return render(request, "create_room.html")


@login_required(login_url="login")
def join_room(request):
    initial_code = request.GET.get("code", "").strip().upper()
    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        if not code:
            messages.error(request, "يرجى إدخال رمز الغرفة.")
            return render(request, "join_room.html", {"initial_code": initial_code})

        room = get_object_or_404(Room.objects.select_related("creator"), code__iexact=code)
        RoomParticipant.objects.get_or_create(
            room=room,
            user=room.creator,
            defaults={"role": "owner"},
        )
        if room.user_is_participant(request.user):
            messages.info(request, "أنت بالفعل داخل هذه الغرفة.")
            return redirect("room_detail", room.code)
        if not room.is_active:
            messages.error(request, "هذه الغرفة مغلقة من طرف صاحبها.")
            return render(request, "join_room.html", {"initial_code": code})
        if not room.has_space_for_guest():
            messages.error(request, "هذه الغرفة مكتملة ولا تقبل أكثر من طرفين خاصين.")
            return render(request, "join_room.html", {"initial_code": code})

        RoomParticipant.objects.create(room=room, user=request.user, role="member")
        if room.creator_id != request.user.id:
            create_notification(
                recipient=room.creator,
                notif_type="message",
                title=f"انضم {request.user.username} إلى الغرفة {room.code}",
                body=f"تم دخول العضو المدعو إلى غرفة {room.display_title}.",
                url=f"/rooms/{room.code}/",
            )
        return redirect("room_detail", room.code)
    return render(request, "join_room.html", {"initial_code": initial_code})


@login_required(login_url="login")
def room_detail(request, code):
    room = _get_room_by_code(code)
    denied = _ensure_room_access(request, room)
    if denied:
        return denied

    participants = list(room.participants.select_related("user__profile"))
    participant_roles = {participant.user_id: participant.role for participant in participants}
    is_owner = room.user_is_owner(request.user)
    can_manage_room = is_owner or request.user.is_superuser
    is_staff_view = request.user.is_staff or request.user.is_superuser

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.method == "POST":
        if not room.is_active:
            message = "تم إغلاق الغرفة ولا يمكن إرسال رسائل جديدة."
            if is_ajax:
                return JsonResponse({"status": "error", "message": message}, status=400)
            messages.warning(request, message)
            return redirect("room_detail", room.code)

        msg = request.POST.get("message", "").strip()
        if msg:
            if len(msg) > 2000:
                if is_ajax:
                    return JsonResponse({"status": "error", "message": "الرسالة طويلة جدًا."}, status=400)
                messages.error(request, "الرسالة طويلة جدًا.")
            else:
                rm = RoomMessage.objects.create(room=room, sender=request.user, text=msg)
                if is_ajax:
                    return JsonResponse(
                        {
                            "status": "ok",
                            "text": rm.text,
                            "time": rm.created_at.strftime("%H:%M"),
                            "avatar": safe_file_url(request.user.profile.avatar),
                            "id": rm.id,
                            "user_id": request.user.id,
                            "username": request.user.username,
                            "role": participant_roles.get(request.user.id, "member"),
                        }
                    )
        if is_ajax:
            return JsonResponse({"status": "error", "message": "تعذر إرسال الرسالة."}, status=400)
        return redirect("room_detail", room.code)

    messages_list = room.messages.all().select_related("sender__profile").order_by("created_at")
    invite_url = request.build_absolute_uri(f"/rooms/join/?code={room.code}")
    trade_exchange = None
    trade_participant_key = ""
    trade_user_ready = False
    trade_user_received = False
    trade_can_edit = False
    if room.room_type == "trade":
        trade_exchange, _ = TradeExchange.objects.get_or_create(room=room)
        trade_participant_key = trade_exchange.participant_key_for(request.user)
        trade_user_ready = (
            bool(trade_exchange.owner_ready_at)
            if trade_participant_key == "owner"
            else bool(trade_exchange.member_ready_at)
            if trade_participant_key == "member"
            else False
        )
        trade_user_received = (
            bool(trade_exchange.owner_received_at)
            if trade_participant_key == "owner"
            else bool(trade_exchange.member_received_at)
            if trade_participant_key == "member"
            else False
        )
        trade_can_edit = trade_exchange.status not in {
            TradeExchange.STATUS_READY,
            TradeExchange.STATUS_RECEIVING,
            TradeExchange.STATUS_COMPLETED,
            TradeExchange.STATUS_DISPUTED,
        }
    return render(
        request,
        "room.html",
        {
            "room": room,
            "room_messages": messages_list,
            "participants": participants,
            "participant_roles": participant_roles,
            "is_owner": is_owner,
            "can_manage_room": can_manage_room,
            "is_staff_view": is_staff_view,
            "invite_url": invite_url,
            "trade_exchange": trade_exchange,
            "trade_participant_key": trade_participant_key,
            "trade_user_ready": trade_user_ready,
            "trade_user_received": trade_user_received,
            "trade_can_edit": trade_can_edit,
        },
    )


@login_required(login_url="login")
@require_POST
def trade_room_action(request, code):
    room = _get_room_by_code(code)
    denied = _ensure_room_access(request, room)
    if denied:
        return denied

    if room.room_type != "trade":
        messages.error(request, "هذا المسار مخصص لغرف التبديل فقط.")
        return redirect("room_detail", room.code)

    if not room.is_active:
        messages.warning(request, "لا يمكن تحديث تبديل داخل غرفة مغلقة.")
        return redirect("room_detail", room.code)

    exchange, _ = TradeExchange.objects.get_or_create(room=room)
    participant_key = exchange.participant_key_for(request.user)
    if participant_key not in {"owner", "member"}:
        messages.error(request, "الإدارة يمكنها المتابعة فقط عند وجود نزاع، ولا تؤكد خطوات التبديل نيابة عن الأطراف.")
        return redirect("room_detail", room.code)

    participant_count = room.participants.count()
    action = request.POST.get("action", "")

    if action == "update_item":
        if exchange.status in {TradeExchange.STATUS_READY, TradeExchange.STATUS_RECEIVING}:
            messages.warning(request, "لا يمكن تعديل وصف التبديل بعد جاهزية الطرفين. افتح نزاعًا إذا تغيّر الاتفاق.")
            return redirect("room_detail", room.code)
        description = request.POST.get("item_description", "").strip()
        if not description:
            messages.error(request, "اكتب وصف الشيء الذي ستقدمه في التبديل.")
            return redirect("room_detail", room.code)
        if len(description) > 1200:
            messages.error(request, "الوصف طويل جدًا. اختصره إلى 1200 حرف.")
            return redirect("room_detail", room.code)
        exchange.set_item_for(participant_key, description)
        exchange.save()
        _system_room_message(room, request.user, "تم تحديث وصف عنصر التبديل.")
        messages.success(request, "تم حفظ وصف التبديل.")

    elif action == "mark_ready":
        if participant_count < Room.MAX_PARTICIPANTS:
            messages.warning(request, "انتظر دخول الطرف الثاني قبل تأكيد الجاهزية.")
            return redirect("room_detail", room.code)
        already_ready = (
            bool(exchange.owner_ready_at) if participant_key == "owner" else bool(exchange.member_ready_at)
        )
        if already_ready:
            messages.info(request, "تم تسجيل جاهزيتك مسبقًا.")
            return redirect("room_detail", room.code)
        own_description = (
            exchange.owner_item_description if participant_key == "owner" else exchange.member_item_description
        ).strip()
        if not own_description:
            messages.error(request, "أضف وصف ما ستقدمه أولًا، ثم أكد الجاهزية.")
            return redirect("room_detail", room.code)
        exchange.mark_ready_for(participant_key)
        exchange.save()
        _system_room_message(room, request.user, "أكد الجاهزية للتبديل.")
        _notify_trade_partner(
            room,
            request.user,
            f"{request.user.username} جاهز للتبديل",
            f"أكد {request.user.username} جاهزيته داخل غرفة التبديل {room.code}.",
        )
        messages.success(request, "تم تأكيد جاهزيتك. عندما يؤكد الطرفان يمكن بدء التسليم.")

    elif action == "confirm_received":
        if not exchange.both_ready:
            messages.warning(request, "لا يمكن تأكيد الاستلام قبل جاهزية الطرفين.")
            return redirect("room_detail", room.code)
        already_received = (
            bool(exchange.owner_received_at) if participant_key == "owner" else bool(exchange.member_received_at)
        )
        if already_received:
            messages.info(request, "تم تسجيل تأكيد الاستلام مسبقًا.")
            return redirect("room_detail", room.code)
        exchange.confirm_received_for(participant_key)
        exchange.save()
        if exchange.status == TradeExchange.STATUS_COMPLETED:
            _system_room_message(room, request.user, "اكتمل التبديل تلقائيًا بعد تأكيد الاستلام من الطرفين.")
            _notify_trade_partner(
                room,
                request.user,
                "اكتمل التبديل بنجاح",
                f"اكتمل التبديل في الغرفة {room.code} بعد تأكيد الاستلام من الطرفين.",
            )
            messages.success(request, "اكتمل التبديل بنجاح وتم إغلاق الغرفة تلقائيًا.")
        else:
            _system_room_message(room, request.user, "أكد استلام ما اتفق عليه.")
            _notify_trade_partner(
                room,
                request.user,
                f"{request.user.username} أكد الاستلام",
                f"أكد {request.user.username} استلام ما اتفق عليه في غرفة التبديل {room.code}.",
            )
            messages.success(request, "تم تسجيل تأكيد الاستلام. ننتظر تأكيد الطرف الآخر.")

    elif action == "report_issue":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "اكتب سبب طلب تدخل الإدارة.")
            return redirect("room_detail", room.code)
        if len(reason) > 1500:
            messages.error(request, "سبب النزاع طويل جدًا. اختصره إلى 1500 حرف.")
            return redirect("room_detail", room.code)
        exchange.open_dispute(request.user, reason)
        exchange.save()
        _system_room_message(room, request.user, "فتح نزاع تبديل وطلب تدخل الإدارة.")
        _notify_trade_dispute(room, reason)
        _notify_trade_partner(
            room,
            request.user,
            "تم فتح نزاع تبديل",
            f"فتح {request.user.username} نزاعًا في غرفة التبديل {room.code}.",
        )
        messages.warning(request, "تم فتح النزاع وإشعار الإدارة للتدخل.")

    else:
        messages.error(request, "إجراء التبديل غير معروف.")

    return redirect("room_detail", room.code)


@login_required(login_url="login")
@require_POST
def close_room(request, code):
    room = _get_room_by_code(code)
    if not (room.user_is_owner(request.user) or request.user.is_superuser):
        messages.error(request, "فقط صاحب الغرفة يمكنه إغلاقها.")
        return redirect("room_detail", room.code)
    if room.is_active:
        room.is_active = False
        room.closed_at = timezone.now()
        room.save(update_fields=["is_active", "closed_at"])
        messages.success(request, "تم إغلاق الغرفة بنجاح.")
    else:
        messages.info(request, "الغرفة مغلقة بالفعل.")
    return redirect("room_detail", room.code)


@login_required(login_url="login")
@require_POST
def reopen_room(request, code):
    room = _get_room_by_code(code)
    if not (room.user_is_owner(request.user) or request.user.is_superuser):
        messages.error(request, "فقط صاحب الغرفة يمكنه إعادة فتحها.")
        return redirect("room_detail", room.code)
    if room.room_type == "trade" and hasattr(room, "trade_exchange"):
        if room.trade_exchange.status == TradeExchange.STATUS_COMPLETED:
            messages.warning(request, "لا يمكن إعادة فتح غرفة تبديل مكتملة.")
            return redirect("room_detail", room.code)
    room.is_active = True
    room.closed_at = None
    room.save(update_fields=["is_active", "closed_at"])
    messages.success(request, "تمت إعادة فتح الغرفة.")
    return redirect("room_detail", room.code)


@login_required(login_url="login")
@require_POST
def delete_room(request, code):
    room = _get_room_by_code(code)
    if not (room.user_is_owner(request.user) or request.user.is_superuser):
        messages.error(request, "فقط صاحب الغرفة يمكنه حذفها.")
        return redirect("room_detail", room.code)
    room.delete()
    messages.success(request, "تم حذف الغرفة نهائيًا.")
    return redirect("chat_hub")


def _create_deal_evidence(*, deal, uploader, evidence_type, file_obj, metadata=None):
    if not file_obj:
        return None
    try:
        file_obj.seek(0)
    except Exception:
        pass
    return DealEvidence.objects.create(
        deal=deal,
        uploader=uploader,
        evidence_type=evidence_type,
        file=file_obj,
        metadata=metadata or {},
    )


@login_required(login_url="login")
def escrow_room(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)
    can_view_as_admin = request.user.is_superuser or has_any_admin_role(
        request.user, {"operations_admin", "finance_admin", "security_admin"}
    )
    can_run_finance_actions = request.user.is_superuser or has_role_or_legacy_staff(
        request.user, "finance_admin"
    )
    can_run_operations_actions = request.user.is_superuser or has_role_or_legacy_staff(
        request.user, "operations_admin"
    )
    is_admin = can_view_as_admin
    if request.user != deal.buyer and request.user != deal.seller and not is_admin:
        messages.error(request, "ليس لديك صلاحية الدخول لهذه الغرفة.")
        return redirect("home")

    room, _ = EscrowRoom.objects.get_or_create(deal=deal)
    messages_list = room.messages.select_related("sender__profile").all()
    payment = getattr(deal, "payment", None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "send_message":
            text = request.POST.get("text", "").strip()
            if text:
                EscrowMessage.objects.create(room=room, sender=request.user, text=text, is_admin=is_admin)

        elif action == "mark_shipped" and request.user == deal.seller:
            if not (payment and payment.status == "escrow_held"):
                messages.warning(request, "يجب أن يكون المبلغ محتجزًا في الضمان قبل بدء التسليم.")
            else:
                proof_file = request.FILES.get("shipping_proof")
                try:
                    validate_public_attachment(proof_file)
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                else:
                    with transaction.atomic():
                        locked_deal = Deal.objects.select_for_update().get(id=deal.id)
                        transition = execute_deal_command(
                            "start_delivery",
                            deal=locked_deal,
                            actor=request.user,
                            request=request,
                            metadata={"source": "escrow_room"},
                        )
                        if transition.allowed:
                            locked_deal.seller_shipped = True
                            locked_deal.shipping_proof = proof_file
                            locked_deal.tracking_number = request.POST.get("tracking_number", "").strip()
                            locked_deal.save(
                                update_fields=[
                                    "seller_shipped",
                                    "shipping_proof",
                                    "tracking_number",
                                    "updated_at",
                                ]
                            )
                            _create_deal_evidence(
                                deal=locked_deal,
                                uploader=request.user,
                                evidence_type=DealEvidence.TYPE_DELIVERY,
                                file_obj=proof_file,
                                metadata={
                                    "source": "escrow_room",
                                    "tracking_number": locked_deal.tracking_number,
                                    "transition_event_id": transition.event_id,
                                },
                            )
                    if transition.allowed:
                        EscrowMessage.objects.create(
                            room=room,
                            sender=request.user,
                            text="بدأ البائع مرحلة التسليم وأرفق التفاصيل داخل غرفة الضمان.",
                            is_admin=False,
                        )
                        if deal.buyer:
                            create_notification(
                                recipient=deal.buyer,
                                notif_type="shipped",
                                title=f"تم بدء التسليم — {deal.product_title}",
                                body=f"أضاف البائع {deal.seller.username} تفاصيل التسليم داخل غرفة الضمان.",
                                url=f"/escrow/{deal.id}/",
                                deal=deal,
                                actor=request.user,
                                action="delivery_started",
                                priority="high",
                                metadata={"source": "escrow_room"},
                            )
                        messages.success(request, "تم تسجيل بدء التسليم داخل غرفة الصفقة.")
                    else:
                        messages.warning(request, "لا يمكن بدء التسليم في الحالة الحالية للصفقة.")

        elif action == "confirm_delivery" and request.user == deal.buyer:
            if not (payment and payment.status == "escrow_held"):
                messages.warning(request, "لا يمكن تأكيد الاستلام لأن المبلغ ليس محتجزًا في الضمان.")
            else:
                from .payments import PaymentStateError, release_payment_for_deal

                try:
                    released_payment, _, _, _ = release_payment_for_deal(deal, buyer_confirmed=True)
                except PaymentStateError:
                    messages.warning(request, "تعذر تحرير المبلغ لأن حالة الدفع لم تعد مناسبة.")
                else:
                    EscrowMessage.objects.create(
                        room=room,
                        sender=request.user,
                        text=f"أكد المشتري الاستلام وتم تحرير ${released_payment.amount} للبائع.",
                        is_admin=False,
                    )
                    create_notification(
                        recipient=deal.seller,
                        notif_type="delivered",
                        title=f"تم تأكيد الاستلام — {deal.product_title}",
                        body=f"أكد {deal.buyer.username} الاستلام وتم تحرير المبلغ.",
                        url=f"/escrow/{deal.id}/",
                        deal=deal,
                        actor=request.user,
                        action="receipt_confirmed",
                        priority="high",
                        metadata={"source": "escrow_room"},
                    )
                    messages.success(request, "تم تأكيد الاستلام وتحرير المبلغ للبائع.")

        elif action == "open_dispute" and (request.user == deal.buyer or request.user == deal.seller):
            if not (payment and payment.status == "escrow_held"):
                messages.warning(request, "يمكن فتح النزاع فقط عندما يكون المبلغ محتجزًا في الضمان.")
            else:
                dispute_reason = request.POST.get("dispute_reason", "").strip()
                evidence_file = request.FILES.get("dispute_evidence")
                if not dispute_reason:
                    messages.error(request, "يرجى كتابة سبب واضح للنزاع.")
                else:
                    try:
                        validate_public_attachment(evidence_file)
                    except ValidationError as exc:
                        messages.error(request, exc.messages[0])
                    else:
                        with transaction.atomic():
                            locked_deal = Deal.objects.select_for_update().get(id=deal.id)
                            transition = execute_deal_command(
                                "open_dispute",
                                deal=locked_deal,
                                actor=request.user,
                                request=request,
                                metadata={"source": "escrow_room", "reason": dispute_reason},
                            )
                            if transition.allowed:
                                locked_deal.dispute_reason = dispute_reason
                                locked_deal.dispute_evidence = evidence_file
                                locked_deal.save(update_fields=["dispute_reason", "dispute_evidence", "updated_at"])
                                _create_deal_evidence(
                                    deal=locked_deal,
                                    uploader=request.user,
                                    evidence_type=DealEvidence.TYPE_DISPUTE,
                                    file_obj=evidence_file,
                                    metadata={
                                        "source": "escrow_room",
                                        "reason": dispute_reason,
                                        "transition_event_id": transition.event_id,
                                    },
                                )
                        if transition.allowed:
                            EscrowMessage.objects.create(
                                room=room,
                                sender=request.user,
                                text="تم فتح نزاع وإرفاق السبب داخل غرفة الضمان. ستتم مراجعة الأدلة من الإدارة.",
                                is_admin=False,
                            )
                            for admin in User.objects.filter(is_staff=True):
                                create_notification(
                                    recipient=admin,
                                    notif_type="dispute",
                                    title=f"نزاع صفقة جديد — {deal.product_title}",
                                    body=f"فتح {request.user.username} نزاعًا على الصفقة #{deal.id}.",
                                    url=f"/escrow/{deal.id}/",
                                    deal=deal,
                                    actor=request.user,
                                    action="dispute_opened",
                                    priority="critical",
                                    metadata={"source": "escrow_room"},
                                )
                            messages.success(request, "تم فتح النزاع وتوثيق السبب والأدلة.")
                        else:
                            messages.warning(request, "لا يمكن فتح نزاع في الحالة الحالية للصفقة.")

        elif action == "release" and can_run_finance_actions:
            if payment and payment.status == "escrow_held":
                from .payments import PaymentStateError, release_payment_for_deal

                try:
                    payment, _, _, _ = release_payment_for_deal(
                        deal,
                        audit_admin=request.user,
                        audit_reason="Admin release from escrow room.",
                    )
                except PaymentStateError:
                    messages.warning(request, "المبلغ غير محتجز أو تم تحريره مسبقًا.")
                else:
                    EscrowMessage.objects.create(
                        room=room,
                        sender=request.user,
                        text=f"✅ [الإدارة] تم تحرير المبلغ ${payment.amount} للبائع {deal.seller.username}.",
                        is_admin=True,
                    )
                    messages.success(request, "تم تحرير المبلغ للبائع عبر النظام.")
            else:
                current_status = payment.status if payment else "no_payment"
                EscrowMessage.objects.create(
                    room=room,
                    sender=request.user,
                    text=f"⚠️ [النظام] رُفض طلب التحرير — حالة الدفع الحالية: {current_status}. يجب أن يكون المبلغ محتجزًا في Escrow أولًا.",
                    is_admin=True,
                )
                messages.error(request, f"لا يمكن تحرير المبلغ. حالة الدفع الحالية: {current_status}. يجب أن يكون المبلغ محتجزًا في Escrow.")

        elif action == "delete_room" and can_run_operations_actions:
            if payment and payment.status in ("released", "refunded"):
                room.delete()
                messages.success(request, "تم حذف غرفة الصفقة.")
                return redirect("deal_detail", deal_id=deal.id)
            messages.warning(request, "لا يمكن حذف الغرفة قبل إتمام الدفع أو استرداده.")

        elif action == "refund" and can_run_finance_actions:
            if payment and payment.status in ("escrow_held", "pending"):
                import stripe

                from .payments import PaymentStateError, refund_payment_for_deal

                try:
                    payment, _ = refund_payment_for_deal(
                        deal,
                        audit_admin=request.user,
                        audit_reason="Admin refund from escrow room.",
                    )
                except PaymentStateError as exc:
                    if str(exc) == "unmappable_reference":
                        messages.error(request, "مرجع الدفع الحالي لا يسمح بتنفيذ استرداد Stripe بأمان.")
                    elif str(exc) == "stripe_not_configured":
                        messages.error(request, "تم حظر الاسترداد لأن Stripe غير مفعل بشكل صحيح. لم يتم تغيير حالة الدفع.")
                    elif str(exc) == "missing_reference":
                        messages.error(request, "تم حظر الاسترداد لأن مرجع عملية Stripe مفقود.")
                    else:
                        messages.warning(request, "لا يمكن استرداد هذا الدفع عبر النظام.")
                except stripe.error.StripeError:
                    messages.error(request, "فشل استرداد المبلغ من Stripe. لم يتم تغيير حالة الصفقة.")
                else:
                    EscrowMessage.objects.create(
                        room=room,
                        sender=request.user,
                        text=f"↩️ [الإدارة] تم استرداد المبلغ ${payment.amount} للمشتري.",
                        is_admin=True,
                    )
                    messages.success(request, "تم استرداد المبلغ للمشتري عبر النظام.")
            else:
                current_status = payment.status if payment else "no_payment"
                EscrowMessage.objects.create(
                    room=room,
                    sender=request.user,
                    text=f"⚠️ [النظام] رُفض طلب الاسترداد — حالة الدفع الحالية: {current_status}. يجب أن يكون المبلغ محتجزًا أو معلقًا.",
                    is_admin=True,
                )
                messages.error(request, f"لا يمكن استرداد المبلغ. حالة الدفع الحالية: {current_status}.")

        elif action == "cancel_deal" and (can_run_operations_actions or can_run_finance_actions):
            if deal.status not in ("completed", "cancelled"):
                if payment and payment.status in ("escrow_held", "pending"):
                    from .payments import refund_payment_for_deal

                    try:
                        refund_payment_for_deal(
                            deal,
                            audit_admin=request.user,
                            audit_reason="Admin cancelled the deal and refunded the buyer.",
                        )
                    except Exception as exc:
                        messages.warning(request, f"تم الإلغاء، لكن حدث خطأ في الاسترداد: {str(exc)}")

                deal.status = "cancelled"
                deal.save()
                EscrowMessage.objects.create(
                    room=room,
                    sender=request.user,
                    text="🚫 [الإدارة] تم إلغاء الصفقة من قبل الإدارة.",
                    is_admin=True,
                )
                messages.success(request, "تم إلغاء الصفقة بنجاح.")
            else:
                messages.warning(request, "لا يمكن إلغاء صفقة مكتملة أو ملغاة مسبقًا.")

        return redirect("escrow_room", deal_id=deal.id)

    language = get_request_language(request)
    room_command_context = build_deal_room_context(deal, request.user, language)

    return render(
        request,
        "escrow_room.html",
        {
            "deal": deal,
            "room": room,
            "messages_list": messages_list,
            "payment": payment,
            "is_admin": is_admin,
            "can_run_finance_actions": can_run_finance_actions,
            "can_run_operations_actions": can_run_operations_actions,
            **room_command_context,
        },
    )
