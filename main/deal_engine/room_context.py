from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .permissions import ROLE_ADMIN, ROLE_BUYER, ROLE_SELLER, actor_role_for
from .states import (
    STATE_CANCELLED,
    STATE_COMPLETED,
    STATE_DELIVERED,
    STATE_DISPUTED,
    STATE_ESCROW_HELD,
    STATE_IN_DELIVERY,
    STATE_MATCHED,
    STATE_OPEN,
    STATE_PAYMENT_PENDING,
    STATE_REFUNDED,
    get_engine_state,
)


LABELS = {
    "ar": {
        "action.pay.title": "الإجراء المطلوب الآن: إكمال الدفع",
        "action.pay.body": "الصفقة محجوزة لك. ادفع الآن حتى تنتقل الأموال إلى الضمان وتبدأ حماية المنصة.",
        "action.pay.button": "ادفع الآن",
        "action.delivery.title": "الإجراء المطلوب الآن: بدء التسليم",
        "action.delivery.body": "المبلغ محتجز في الضمان. أرسل تفاصيل التسليم أو ارفع إثباتًا ليظهر للمشتري داخل الغرفة.",
        "action.delivery.button": "تأكيد بدء التسليم",
        "action.confirm.title": "الإجراء المطلوب الآن: تأكيد الاستلام",
        "action.confirm.body": "راجع المنتج أو الخدمة. عند التأكيد سيتم تحرير المبلغ للبائع وتغلق الصفقة.",
        "action.confirm.button": "أكد الاستلام وحرر المبلغ",
        "action.dispute.title": "الإجراء المطلوب الآن: مراجعة النزاع",
        "action.dispute.body": "النزاع مفتوح. راجع الأدلة والمحادثة قبل اتخاذ قرار مالي.",
        "action.dispute.button": "راجع من لوحة الإدارة",
        "action.waiting_seller.title": "بانتظار البائع",
        "action.waiting_seller.body": "تم تأمين المبلغ. ننتظر من البائع بدء التسليم أو إضافة إثبات.",
        "action.waiting_buyer.title": "بانتظار المشتري",
        "action.waiting_buyer.body": "تم بدء التسليم. ننتظر تأكيد الاستلام أو فتح نزاع عند وجود مشكلة.",
        "action.completed.title": "الصفقة مكتملة",
        "action.completed.body": "تم إغلاق الصفقة وتسجيل الأحداث في السجل الدائم.",
        "action.refunded.title": "تم الاسترداد",
        "action.refunded.body": "تم رد المبلغ للمشتري وتوثيق العملية في سجل الصفقة.",
        "action.cancelled.title": "الصفقة ملغاة",
        "action.cancelled.body": "تم إيقاف الصفقة ولا توجد إجراءات مطلوبة الآن.",
        "action.default.title": "لا يوجد إجراء مطلوب منك الآن",
        "action.default.body": "تابع حالة الصفقة والرسائل. سيظهر الإجراء التالي هنا تلقائيًا عند تغير الحالة.",
        "deadline.payment": "مهلة الدفع",
        "deadline.delivery": "مهلة بدء التسليم",
        "deadline.confirm": "مهلة تأكيد الاستلام",
        "deadline.dispute": "مهلة الرد على النزاع",
        "deadline.none": "لا توجد مهلة نشطة",
        "deadline.overdue": "انتهت المهلة",
        "deadline.days": "{days} يوم",
        "deadline.hours": "{hours} ساعة",
        "deadline.minutes": "{minutes} دقيقة",
        "step.agreement": "الاتفاق",
        "step.payment": "الدفع",
        "step.delivery": "التسليم",
        "step.resolution": "الإغلاق",
        "event.created": "تم إنشاء الصفقة",
        "event.deal_reserved": "تم حجز الصفقة",
        "event.payment_pending": "بدأت مراجعة الدفع",
        "event.payment_held": "تم حجز المبلغ في الضمان",
        "event.delivery_started": "بدأ التسليم",
        "event.delivery_marked": "تم تعليم التسليم",
        "event.delivery_confirmed": "تم تأكيد الاستلام",
        "event.deal_completed": "اكتملت الصفقة",
        "event.dispute_opened": "تم فتح نزاع",
        "event.payment_refunded": "تم استرداد المبلغ",
        "event.deal_cancelled": "تم إلغاء الصفقة",
        "event.deal_reopened": "تمت إعادة فتح الصفقة",
        "event.transition": "تحديث حالة الصفقة",
        "evidence.delivery": "إثبات التسليم",
        "evidence.dispute": "دليل النزاع",
        "evidence.admin": "دليل إداري",
        "evidence.unknown": "دليل",
        "role.admin": "الإدارة",
        "role.buyer": "المشتري",
        "role.seller": "البائع",
        "role.system": "النظام",
        "role.visitor": "زائر",
    },
    "en": {
        "action.pay.title": "Required action: complete payment",
        "action.pay.body": "This deal is reserved for you. Pay now so funds move into escrow protection.",
        "action.pay.button": "Pay now",
        "action.delivery.title": "Required action: start delivery",
        "action.delivery.body": "Funds are held in escrow. Add delivery details or proof for the buyer.",
        "action.delivery.button": "Confirm delivery started",
        "action.confirm.title": "Required action: confirm receipt",
        "action.confirm.body": "Review the item or service. Confirming releases the funds and closes the deal.",
        "action.confirm.button": "Confirm receipt and release",
        "action.dispute.title": "Required action: review dispute",
        "action.dispute.body": "A dispute is open. Review evidence and messages before making a financial decision.",
        "action.dispute.button": "Review in admin panel",
        "action.waiting_seller.title": "Waiting for seller",
        "action.waiting_seller.body": "The funds are protected. Waiting for the seller to start delivery or add proof.",
        "action.waiting_buyer.title": "Waiting for buyer",
        "action.waiting_buyer.body": "Delivery has started. Waiting for receipt confirmation or a dispute if something is wrong.",
        "action.completed.title": "Deal completed",
        "action.completed.body": "The deal is closed and the activity is recorded in the permanent log.",
        "action.refunded.title": "Refunded",
        "action.refunded.body": "The buyer was refunded and the operation was recorded in the deal log.",
        "action.cancelled.title": "Deal cancelled",
        "action.cancelled.body": "This deal has stopped. No action is required now.",
        "action.default.title": "No action required from you",
        "action.default.body": "Follow the deal status and messages. The next action will appear here automatically.",
        "deadline.payment": "Payment deadline",
        "deadline.delivery": "Delivery-start deadline",
        "deadline.confirm": "Receipt confirmation deadline",
        "deadline.dispute": "Dispute response deadline",
        "deadline.none": "No active deadline",
        "deadline.overdue": "Deadline expired",
        "deadline.days": "{days} day",
        "deadline.hours": "{hours} hr",
        "deadline.minutes": "{minutes} min",
        "step.agreement": "Agreement",
        "step.payment": "Payment",
        "step.delivery": "Delivery",
        "step.resolution": "Close",
        "event.created": "Deal created",
        "event.deal_reserved": "Deal reserved",
        "event.payment_pending": "Payment review started",
        "event.payment_held": "Funds held in escrow",
        "event.delivery_started": "Delivery started",
        "event.delivery_marked": "Delivery marked",
        "event.delivery_confirmed": "Receipt confirmed",
        "event.deal_completed": "Deal completed",
        "event.dispute_opened": "Dispute opened",
        "event.payment_refunded": "Payment refunded",
        "event.deal_cancelled": "Deal cancelled",
        "event.deal_reopened": "Deal reopened",
        "event.transition": "Deal status updated",
        "evidence.delivery": "Delivery proof",
        "evidence.dispute": "Dispute evidence",
        "evidence.admin": "Admin evidence",
        "evidence.unknown": "Evidence",
        "role.admin": "Admin",
        "role.buyer": "Buyer",
        "role.seller": "Seller",
        "role.system": "System",
        "role.visitor": "Visitor",
    },
}


def _language(language: str | None) -> str:
    return "en" if language == "en" else "ar"


def _label(language: str | None, key: str, **values) -> str:
    language = _language(language)
    text = LABELS[language].get(key, LABELS["en"].get(key, key))
    return text.format(**values) if values else text


def _payment_for(deal):
    return getattr(deal, "payment", None)


def _event_queryset(deal):
    return deal.events.select_related("actor").order_by("-created_at", "-id")


def _last_event_at(deal, event_types):
    event = _event_queryset(deal).filter(event_type__in=event_types).first()
    return event.created_at if event else None


def _format_remaining(delta, language):
    total_seconds = max(0, int(delta.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = max(1, (total_seconds % 3600) // 60)
    if days:
        return _label(language, "deadline.days", days=days)
    if hours:
        return _label(language, "deadline.hours", hours=hours)
    return _label(language, "deadline.minutes", minutes=minutes)


DEADLINE_LABEL_KEYS = {
    "payment": "deadline.payment",
    "delivery": "deadline.delivery",
    "receipt": "deadline.confirm",
    "dispute_response": "deadline.dispute",
}


def _deadline_from_record(deadline, language):
    now = timezone.now()
    due_at = deadline.due_at
    duration_seconds = int((deadline.metadata or {}).get("duration_seconds") or 0)
    if not duration_seconds:
        duration_seconds = max(1, int((due_at - deadline.created_at).total_seconds()))
    elapsed = max(0, int((now - deadline.created_at).total_seconds()))
    progress = min(100, int((elapsed / max(1, duration_seconds)) * 100))
    is_overdue = now >= due_at
    remaining_label = _label(language, "deadline.overdue") if is_overdue else _format_remaining(due_at - now, language)
    label_key = DEADLINE_LABEL_KEYS.get(deadline.deadline_type, "deadline.none")
    return {
        "active": True,
        "label": _label(language, label_key),
        "remaining_label": remaining_label,
        "due_at": due_at,
        "progress": progress,
        "is_overdue": is_overdue,
    }


def _deadline_context(deal, state, language):
    try:
        active_deadline = deal.deadlines.filter(status="active").order_by("due_at", "id").first()
    except Exception:
        active_deadline = None
    if active_deadline:
        return _deadline_from_record(active_deadline, language)

    payment = _payment_for(deal)
    now = timezone.now()
    rules = {
        STATE_PAYMENT_PENDING: (
            "deadline.payment",
            payment.created_at if payment else deal.updated_at,
            timedelta(minutes=30),
        ),
        STATE_ESCROW_HELD: (
            "deadline.delivery",
            _last_event_at(deal, ["payment_held"]) or getattr(payment, "held_at", None) or deal.updated_at,
            timedelta(hours=48),
        ),
        STATE_IN_DELIVERY: (
            "deadline.confirm",
            _last_event_at(deal, ["delivery_started"]) or deal.updated_at,
            timedelta(hours=24),
        ),
        STATE_DISPUTED: (
            "deadline.dispute",
            _last_event_at(deal, ["dispute_opened"]) or deal.updated_at,
            timedelta(hours=24),
        ),
    }
    if state not in rules:
        return {
            "active": False,
            "label": _label(language, "deadline.none"),
            "remaining_label": "",
            "due_at": None,
            "progress": 0,
            "is_overdue": False,
        }

    label_key, starts_at, duration = rules[state]
    due_at = starts_at + duration
    elapsed = max(0, (now - starts_at).total_seconds())
    total = max(1, duration.total_seconds())
    progress = min(100, int((elapsed / total) * 100))
    is_overdue = now >= due_at
    remaining_label = _label(language, "deadline.overdue") if is_overdue else _format_remaining(due_at - now, language)
    return {
        "active": True,
        "label": _label(language, label_key),
        "remaining_label": remaining_label,
        "due_at": due_at,
        "progress": progress,
        "is_overdue": is_overdue,
    }


def _step_status(state, step):
    if step == "agreement":
        if state in {STATE_OPEN}:
            return "active"
        return "done"
    if step == "payment":
        if state in {STATE_MATCHED, STATE_PAYMENT_PENDING}:
            return "active"
        if state in {STATE_ESCROW_HELD, STATE_IN_DELIVERY, STATE_DELIVERED, STATE_COMPLETED, STATE_DISPUTED, STATE_REFUNDED}:
            return "done"
        return ""
    if step == "delivery":
        if state in {STATE_ESCROW_HELD, STATE_IN_DELIVERY}:
            return "active"
        if state in {STATE_DELIVERED, STATE_COMPLETED}:
            return "done"
        if state == STATE_DISPUTED:
            return "danger"
        return ""
    if state == STATE_DISPUTED:
        return "danger"
    if state in {STATE_COMPLETED, STATE_REFUNDED, STATE_CANCELLED}:
        return "done"
    if state == STATE_DELIVERED:
        return "active"
    return ""


def _timeline_steps(state, language):
    steps = [
        ("agreement", "step.agreement", "fa-handshake"),
        ("payment", "step.payment", "fa-vault"),
        ("delivery", "step.delivery", "fa-truck-fast"),
        ("resolution", "step.resolution", "fa-flag-checkered"),
    ]
    return [
        {
            "key": key,
            "label": _label(language, label_key),
            "icon": icon,
            "status": _step_status(state, key),
        }
        for key, label_key, icon in steps
    ]


def _room_action(deal, actor, state, role, language):
    if state in {STATE_MATCHED, STATE_PAYMENT_PENDING} and role == ROLE_BUYER:
        return {
            "kind": "link",
            "tone": "gold",
            "icon": "fa-credit-card",
            "title": _label(language, "action.pay.title"),
            "body": _label(language, "action.pay.body"),
            "button": _label(language, "action.pay.button"),
            "href": reverse("create_payment", args=[deal.id]),
        }
    if state == STATE_ESCROW_HELD and role == ROLE_SELLER and not deal.seller_shipped:
        return {
            "kind": "delivery_form",
            "tone": "gold",
            "icon": "fa-truck-fast",
            "title": _label(language, "action.delivery.title"),
            "body": _label(language, "action.delivery.body"),
            "button": _label(language, "action.delivery.button"),
        }
    if state == STATE_ESCROW_HELD and role == ROLE_BUYER:
        return {
            "kind": "waiting",
            "tone": "info",
            "icon": "fa-clock",
            "title": _label(language, "action.waiting_seller.title"),
            "body": _label(language, "action.waiting_seller.body"),
        }
    if state in {STATE_IN_DELIVERY, STATE_DELIVERED} and role == ROLE_BUYER:
        return {
            "kind": "confirm_form",
            "tone": "success",
            "icon": "fa-circle-check",
            "title": _label(language, "action.confirm.title"),
            "body": _label(language, "action.confirm.body"),
            "button": _label(language, "action.confirm.button"),
        }
    if state in {STATE_IN_DELIVERY, STATE_DELIVERED} and role == ROLE_SELLER:
        return {
            "kind": "waiting",
            "tone": "info",
            "icon": "fa-clock",
            "title": _label(language, "action.waiting_buyer.title"),
            "body": _label(language, "action.waiting_buyer.body"),
        }
    if state == STATE_DISPUTED and role == ROLE_ADMIN:
        return {
            "kind": "admin_review",
            "tone": "danger",
            "icon": "fa-scale-balanced",
            "title": _label(language, "action.dispute.title"),
            "body": _label(language, "action.dispute.body"),
            "button": _label(language, "action.dispute.button"),
        }
    if state == STATE_COMPLETED:
        return {
            "kind": "done",
            "tone": "success",
            "icon": "fa-circle-check",
            "title": _label(language, "action.completed.title"),
            "body": _label(language, "action.completed.body"),
        }
    if state == STATE_REFUNDED:
        return {
            "kind": "done",
            "tone": "warning",
            "icon": "fa-rotate-left",
            "title": _label(language, "action.refunded.title"),
            "body": _label(language, "action.refunded.body"),
        }
    if state == STATE_CANCELLED:
        return {
            "kind": "done",
            "tone": "danger",
            "icon": "fa-ban",
            "title": _label(language, "action.cancelled.title"),
            "body": _label(language, "action.cancelled.body"),
        }
    return {
        "kind": "waiting",
        "tone": "neutral",
        "icon": "fa-wave-square",
        "title": _label(language, "action.default.title"),
        "body": _label(language, "action.default.body"),
    }


def _event_label(event, language):
    return _label(language, f"event.{event.event_type}") if f"event.{event.event_type}" in LABELS[_language(language)] else _label(language, "event.transition")


def _role_label(role, language):
    return _label(language, f"role.{role}")


def _activity_feed(deal, language, limit=8):
    items = [
        {
            "label": _label(language, "event.created"),
            "actor": getattr(deal.seller, "username", ""),
            "role": _role_label(ROLE_SELLER, language),
            "created_at": deal.created_at,
            "tone": "neutral",
            "icon": "fa-plus",
        }
    ]
    for event in reversed(list(_event_queryset(deal)[:limit])):
        role = actor_role_for(deal, event.actor) if event.actor else "system"
        items.append(
            {
                "label": _event_label(event, language),
                "actor": event.actor.username if event.actor else _role_label("system", language),
                "role": _role_label(role, language),
                "created_at": event.created_at,
                "tone": "danger" if event.event_type == "dispute_opened" else "success" if event.to_state == STATE_COMPLETED else "neutral",
                "icon": "fa-scale-balanced" if event.event_type == "dispute_opened" else "fa-check",
            }
        )
    return sorted(items, key=lambda item: item["created_at"], reverse=True)[:limit]


def _evidence_feed(deal, language, limit=8):
    items = []
    try:
        evidence_queryset = deal.evidence_items.select_related("uploader").order_by("-created_at", "-id")[:limit]
    except Exception:
        return items

    for evidence in evidence_queryset:
        try:
            url = evidence.file.url
        except Exception:
            url = ""
        items.append(
            {
                "label": _label(language, f"evidence.{evidence.evidence_type}")
                if f"evidence.{evidence.evidence_type}" in LABELS[_language(language)]
                else _label(language, "evidence.unknown"),
                "url": url,
                "hash": evidence.short_hash,
                "original_name": evidence.original_name,
                "uploader": evidence.uploader.username if evidence.uploader else _role_label("system", language),
                "created_at": evidence.created_at,
                "is_archived": bool(evidence.archived_at),
            }
        )
    return items


def build_deal_room_context(deal, actor, language="ar"):
    state = get_engine_state(deal)
    role = actor_role_for(deal, actor)
    return {
        "engine_state": state,
        "actor_role": role,
        "actor_role_label": _role_label(role, language),
        "room_action": _room_action(deal, actor, state, role, language),
        "room_deadline": _deadline_context(deal, state, language),
        "room_steps": _timeline_steps(state, language),
        "room_activity": _activity_feed(deal, language),
        "room_evidence": _evidence_feed(deal, language),
    }
