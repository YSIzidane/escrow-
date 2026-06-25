from .core import (
    home, about, how_it_works, listings_view, search_user, set_site_language, health_check, performance_vitals,
    public_media_file,
    privacy_policy, terms_policy, returns_policy,
    view_403, view_404, view_500, view_503,
)
from .auth import (
    login_page, register_page, logout_page,
    legacy_login_redirect, legacy_register_redirect, legacy_logout_redirect,
)
from .deals import (
    create_deal, deal_detail, deal_room, confirm_deal, delete_deal,
    deal_auction_detail, submit_bid, accept_bid, create_review, delete_comment,
)
from .social import (
    profile, user_profile,
    send_friend_request, accept_friend_request, friends_list, request_withdrawal,
)
from .chat import (
    chat_hub, private_chat,
    create_room, join_room, room_detail, close_room, reopen_room, delete_room,
    trade_room_action, escrow_room,
)
from .payments import (
    create_payment, payment_confirm, payment_success_page,
    payment_release, payment_refund, payment_cancel, payment_success,
    stripe_webhook, ccp_checkout_submit, invoice_detail,
)
from .staff import (
    staff_required, escrow_dashboard, staff_dashboard, staff_ticket_detail,
    admin_dashboard, admin_security_reports, my_tickets, create_ticket, ticket_detail,
    admin_kyc_list, admin_kyc_document, admin_withdrawals_list, admin_rooms_list,
    admin_users_list,
    private_message_attachment, ticket_attachment, ticket_reply_attachment, deal_message_attachment,
    staff_payment_proof, staff_pending_payments, staff_approve_ccp, staff_reject_ccp,
)
from .notifications import (
    create_notification, notifications_page, mark_notification_read, delete_notification,
    poll_notifications, poll_escrow_room, poll_room_chat, poll_private_chat, poll_deal_chat,
)

__all__ = [
    # Core
    "home", "about", "how_it_works", "listings_view", "search_user", "set_site_language", "health_check", "performance_vitals",
    "public_media_file",
    "privacy_policy", "terms_policy", "returns_policy",
    "view_403", "view_404", "view_500", "view_503",
    # Auth
    "login_page", "register_page", "logout_page",
    "legacy_login_redirect", "legacy_register_redirect", "legacy_logout_redirect",
    # Deals
    "create_deal", "deal_detail", "deal_room", "confirm_deal", "delete_deal",
    "deal_auction_detail", "submit_bid", "accept_bid", "create_review", "delete_comment",
    # Social
    "profile", "user_profile",
    "send_friend_request", "accept_friend_request", "friends_list", "request_withdrawal",
    # Chat
    "chat_hub", "private_chat",
    "create_room", "join_room", "room_detail", "close_room", "reopen_room", "delete_room",
    "trade_room_action", "escrow_room",
    # Payments
    "create_payment", "payment_confirm", "payment_success_page",
    "payment_release", "payment_refund", "payment_cancel", "payment_success",
    "stripe_webhook", "invoice_detail",
    # Staff
    "staff_required", "escrow_dashboard", "staff_dashboard", "staff_ticket_detail",
    "admin_dashboard", "admin_security_reports", "my_tickets", "create_ticket", "ticket_detail",
    "admin_kyc_list", "admin_kyc_document", "admin_withdrawals_list", "admin_rooms_list", "admin_users_list",
    "private_message_attachment", "ticket_attachment", "ticket_reply_attachment", "deal_message_attachment",
    "staff_payment_proof", "staff_pending_payments", "staff_approve_ccp", "staff_reject_ccp",
    # Notifications
    "create_notification", "notifications_page", "mark_notification_read", "delete_notification",
    "poll_notifications", "poll_escrow_room", "poll_room_chat", "poll_private_chat", "poll_deal_chat",
]
