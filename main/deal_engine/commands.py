from dataclasses import dataclass

from django.db import transaction

from main.models import DealEvent, DealTransitionLog

from .deadlines import sync_deadline_for_transition
from .events import event_type_for
from .exceptions import InvalidTransition, PermissionDeniedForTransition
from .permissions import can_actor_run
from .states import can_transition, get_engine_state, legacy_status_for

COMMAND_TARGET_STATES = {
    "publish": "open",
    "reserve_deal": "matched",
    "payment_pending": "payment_pending",
    "payment_held": "escrow_held",
    "start_delivery": "in_delivery",
    "mark_delivered": "delivered",
    "confirm_delivery": "completed",
    "complete": "completed",
    "open_dispute": "disputed",
    "refund": "refunded",
    "cancel": "cancelled",
    "reopen": "open",
}


@dataclass(frozen=True)
class DealTransitionResult:
    allowed: bool
    command: str
    from_state: str
    to_state: str
    actor_role: str
    reason: str = ""
    event_id: int | None = None
    log_id: int | None = None


def _request_metadata(request):
    if request is None:
        return "", ""
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.META.get("REMOTE_ADDR", "")
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip_address or "", user_agent or ""


def _record_attempt(*, deal, actor, command, from_state, to_state, allowed, reason, metadata, request):
    ip_address, user_agent = _request_metadata(request)
    return DealTransitionLog.objects.create(
        deal=deal,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        command=command,
        from_state=from_state,
        to_state=to_state,
        allowed=allowed,
        reason=reason,
        metadata=metadata or {},
        ip_address=ip_address or None,
        user_agent=user_agent,
    )


def _record_event(*, deal, actor, command, from_state, to_state, metadata, request):
    ip_address, user_agent = _request_metadata(request)
    return DealEvent.objects.create(
        deal=deal,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type_for(command),
        from_state=from_state,
        to_state=to_state,
        metadata=metadata or {},
        ip_address=ip_address or None,
        user_agent=user_agent,
    )


def execute(command, *, deal, actor=None, metadata=None, request=None, save=True, raise_on_error=False):
    if command not in COMMAND_TARGET_STATES:
        raise InvalidTransition("unknown_command")

    metadata = metadata or {}
    error_to_raise = None

    with transaction.atomic():
        from_state = get_engine_state(deal)
        to_state = COMMAND_TARGET_STATES[command]
        role_allowed, actor_role = can_actor_run(command, from_state, deal, actor)

        if not can_transition(from_state, to_state):
            log = _record_attempt(
                deal=deal,
                actor=actor,
                command=command,
                from_state=from_state,
                to_state=to_state,
                allowed=False,
                reason="invalid_transition",
                metadata=metadata,
                request=request,
            )
            result = DealTransitionResult(False, command, from_state, to_state, actor_role, "invalid_transition", None, log.id)
            if raise_on_error:
                error_to_raise = InvalidTransition("invalid_transition", result)
            else:
                return result
        elif not role_allowed:
            log = _record_attempt(
                deal=deal,
                actor=actor,
                command=command,
                from_state=from_state,
                to_state=to_state,
                allowed=False,
                reason="permission_denied",
                metadata=metadata,
                request=request,
            )
            result = DealTransitionResult(False, command, from_state, to_state, actor_role, "permission_denied", None, log.id)
            if raise_on_error:
                error_to_raise = PermissionDeniedForTransition("permission_denied", result)
            else:
                return result
        else:
            result = None

        if error_to_raise is not None:
            pass
        elif save:
            next_legacy_status = legacy_status_for(to_state)
            if deal.status != next_legacy_status:
                deal.status = next_legacy_status
                deal.save(update_fields=["status", "updated_at"])

        if error_to_raise is None:
            event = _record_event(
                deal=deal,
                actor=actor,
                command=command,
                from_state=from_state,
                to_state=to_state,
                metadata=metadata,
                request=request,
            )
            sync_deadline_for_transition(deal=deal, event=event, to_state=to_state)
            log = _record_attempt(
                deal=deal,
                actor=actor,
                command=command,
                from_state=from_state,
                to_state=to_state,
                allowed=True,
                reason="",
                metadata=metadata,
                request=request,
            )
            result = DealTransitionResult(True, command, from_state, to_state, actor_role, "", event.id, log.id)

    if error_to_raise is not None:
        raise error_to_raise
    return result
