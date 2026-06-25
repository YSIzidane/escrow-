from .states import (
    STATE_DELIVERED,
    STATE_DISPUTED,
    STATE_DRAFT,
    STATE_ESCROW_HELD,
    STATE_IN_DELIVERY,
    STATE_MATCHED,
    STATE_OPEN,
    STATE_PAYMENT_PENDING,
)

ROLE_ADMIN = "admin"
ROLE_BUYER = "buyer"
ROLE_SELLER = "seller"
ROLE_SYSTEM = "system"
ROLE_VISITOR = "visitor"

COMMAND_ROLES = {
    "publish": {
        STATE_DRAFT: {ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
    },
    "reserve_deal": {
        STATE_OPEN: {ROLE_BUYER, ROLE_ADMIN},
    },
    "payment_pending": {
        STATE_OPEN: {ROLE_BUYER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_MATCHED: {ROLE_BUYER, ROLE_ADMIN, ROLE_SYSTEM},
    },
    "payment_held": {
        STATE_OPEN: {ROLE_BUYER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_MATCHED: {ROLE_BUYER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_PAYMENT_PENDING: {ROLE_BUYER, ROLE_ADMIN, ROLE_SYSTEM},
    },
    "start_delivery": {
        STATE_ESCROW_HELD: {ROLE_SELLER, ROLE_ADMIN},
    },
    "mark_delivered": {
        STATE_ESCROW_HELD: {ROLE_BUYER, ROLE_ADMIN},
        STATE_IN_DELIVERY: {ROLE_BUYER, ROLE_ADMIN},
    },
    "confirm_delivery": {
        STATE_ESCROW_HELD: {ROLE_BUYER, ROLE_ADMIN},
        STATE_IN_DELIVERY: {ROLE_BUYER, ROLE_ADMIN},
        STATE_DELIVERED: {ROLE_BUYER, ROLE_ADMIN},
    },
    "complete": {
        STATE_ESCROW_HELD: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_IN_DELIVERY: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_DELIVERED: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_DISPUTED: {ROLE_ADMIN, ROLE_SYSTEM},
    },
    "open_dispute": {
        STATE_ESCROW_HELD: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN},
        STATE_IN_DELIVERY: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN},
        STATE_DELIVERED: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN},
    },
    "refund": {
        STATE_PAYMENT_PENDING: {ROLE_ADMIN, ROLE_SYSTEM},
        STATE_ESCROW_HELD: {ROLE_ADMIN, ROLE_SYSTEM},
        STATE_IN_DELIVERY: {ROLE_ADMIN, ROLE_SYSTEM},
        STATE_DELIVERED: {ROLE_ADMIN, ROLE_SYSTEM},
        STATE_DISPUTED: {ROLE_ADMIN, ROLE_SYSTEM},
    },
    "cancel": {
        STATE_DRAFT: {ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_OPEN: {ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_MATCHED: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_PAYMENT_PENDING: {ROLE_BUYER, ROLE_SELLER, ROLE_ADMIN, ROLE_SYSTEM},
        STATE_DISPUTED: {ROLE_ADMIN, ROLE_SYSTEM},
    },
    "reopen": {
        "refunded": {ROLE_ADMIN, ROLE_SYSTEM},
    },
}


def actor_role_for(deal, actor):
    if actor is None:
        return ROLE_SYSTEM
    if not getattr(actor, "is_authenticated", False):
        return ROLE_VISITOR
    if getattr(actor, "is_superuser", False) or getattr(actor, "is_staff", False):
        return ROLE_ADMIN
    if deal.seller_id == actor.id:
        return ROLE_SELLER
    if deal.buyer_id == actor.id:
        return ROLE_BUYER
    if deal.buyer_id is None:
        return ROLE_BUYER
    return ROLE_VISITOR


def can_actor_run(command, state, deal, actor):
    role = actor_role_for(deal, actor)
    return role in COMMAND_ROLES.get(command, {}).get(state, set()), role
