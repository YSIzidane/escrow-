STATE_DRAFT = "draft"
STATE_OPEN = "open"
STATE_MATCHED = "matched"
STATE_PAYMENT_PENDING = "payment_pending"
STATE_ESCROW_HELD = "escrow_held"
STATE_IN_DELIVERY = "in_delivery"
STATE_DELIVERED = "delivered"
STATE_COMPLETED = "completed"
STATE_DISPUTED = "disputed"
STATE_REFUNDED = "refunded"
STATE_CANCELLED = "cancelled"

CANONICAL_STATES = {
    STATE_DRAFT,
    STATE_OPEN,
    STATE_MATCHED,
    STATE_PAYMENT_PENDING,
    STATE_ESCROW_HELD,
    STATE_IN_DELIVERY,
    STATE_DELIVERED,
    STATE_COMPLETED,
    STATE_DISPUTED,
    STATE_REFUNDED,
    STATE_CANCELLED,
}

ALLOWED_TRANSITIONS = {
    STATE_DRAFT: {STATE_OPEN, STATE_CANCELLED},
    STATE_OPEN: {STATE_MATCHED, STATE_PAYMENT_PENDING, STATE_ESCROW_HELD, STATE_CANCELLED},
    STATE_MATCHED: {STATE_PAYMENT_PENDING, STATE_ESCROW_HELD, STATE_CANCELLED},
    STATE_PAYMENT_PENDING: {STATE_ESCROW_HELD, STATE_CANCELLED, STATE_REFUNDED},
    STATE_ESCROW_HELD: {STATE_IN_DELIVERY, STATE_DELIVERED, STATE_COMPLETED, STATE_DISPUTED, STATE_REFUNDED},
    STATE_IN_DELIVERY: {STATE_DELIVERED, STATE_COMPLETED, STATE_DISPUTED, STATE_REFUNDED},
    STATE_DELIVERED: {STATE_COMPLETED, STATE_DISPUTED, STATE_REFUNDED},
    STATE_DISPUTED: {STATE_COMPLETED, STATE_REFUNDED, STATE_CANCELLED},
    STATE_COMPLETED: set(),
    STATE_REFUNDED: {STATE_OPEN, STATE_CANCELLED},
    STATE_CANCELLED: set(),
}

LEGACY_STATUS_TO_ENGINE = {
    "new": STATE_OPEN,
    "expired": STATE_CANCELLED,
    "reserved": STATE_MATCHED,
    "shipped": STATE_IN_DELIVERY,
    "delivered": STATE_DELIVERED,
    "completed": STATE_COMPLETED,
    "disputed": STATE_DISPUTED,
    "cancelled": STATE_CANCELLED,
}

ENGINE_TO_LEGACY_STATUS = {
    STATE_DRAFT: "new",
    STATE_OPEN: "new",
    STATE_MATCHED: "reserved",
    STATE_PAYMENT_PENDING: "reserved",
    STATE_ESCROW_HELD: "reserved",
    STATE_IN_DELIVERY: "shipped",
    STATE_DELIVERED: "delivered",
    STATE_COMPLETED: "completed",
    STATE_DISPUTED: "disputed",
    STATE_REFUNDED: "new",
    STATE_CANCELLED: "cancelled",
}


def payment_state_for(deal):
    try:
        return deal.payment.status
    except Exception:
        return ""


def get_engine_state(deal):
    legacy_state = LEGACY_STATUS_TO_ENGINE.get(deal.status, STATE_OPEN)
    payment_state = payment_state_for(deal)

    if legacy_state in {STATE_COMPLETED, STATE_DISPUTED, STATE_CANCELLED, STATE_IN_DELIVERY, STATE_DELIVERED}:
        return legacy_state
    if payment_state == "released":
        return STATE_COMPLETED
    if payment_state == "refunded":
        return STATE_REFUNDED
    if payment_state == "escrow_held":
        return STATE_ESCROW_HELD
    if payment_state in {"pending", "pending_manual_verification", "failed"}:
        return STATE_PAYMENT_PENDING
    return legacy_state


def legacy_status_for(engine_state):
    return ENGINE_TO_LEGACY_STATUS[engine_state]


def can_transition(from_state, to_state):
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())
