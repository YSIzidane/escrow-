COMMAND_EVENT_TYPES = {
    "publish": "deal_published",
    "reserve_deal": "deal_reserved",
    "payment_pending": "payment_pending",
    "payment_held": "payment_held",
    "start_delivery": "delivery_started",
    "mark_delivered": "delivery_marked",
    "confirm_delivery": "delivery_confirmed",
    "complete": "deal_completed",
    "open_dispute": "dispute_opened",
    "refund": "payment_refunded",
    "cancel": "deal_cancelled",
    "reopen": "deal_reopened",
}


def event_type_for(command):
    return COMMAND_EVENT_TYPES.get(command, command)
