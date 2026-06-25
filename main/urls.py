from django.urls import path
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from .views import (
    accept_bid, create_deal, deal_auction_detail, delete_comment, home,
    poll_notifications, deal_room, confirm_deal,
    deal_detail, delete_deal, profile, create_room, join_room, room_detail,
    close_room, reopen_room, delete_room, trade_room_action, search_user, listings_view, about, send_friend_request,
    accept_friend_request, friends_list, private_chat, submit_bid, user_profile,
    chat_hub, create_payment, payment_success, payment_cancel, stripe_webhook,
    create_ticket, ticket_detail, my_tickets, staff_dashboard,
    staff_ticket_detail, payment_confirm, payment_release, payment_refund,
    payment_success_page, escrow_room, poll_escrow_room, escrow_dashboard,
    notifications_page, mark_notification_read, delete_notification, poll_notifications, admin_dashboard,
    admin_security_reports,
    create_review, poll_room_chat, poll_private_chat, poll_deal_chat, set_site_language,
    health_check, performance_vitals,
    view_403, view_404, view_500, view_503, privacy_policy, terms_policy, returns_policy,
    request_withdrawal, admin_kyc_list, admin_kyc_document, admin_users_list, admin_withdrawals_list,
    invoice_detail, admin_rooms_list,
    private_message_attachment, ticket_attachment, ticket_reply_attachment, deal_message_attachment,
    ccp_checkout_submit, staff_payment_proof, staff_pending_payments, staff_approve_ccp, staff_reject_ccp,
    how_it_works, legacy_login_redirect, legacy_register_redirect, legacy_logout_redirect,
    public_media_file,
)

urlpatterns = [
    # Main Pages
    path('', home, name='home'),
    path('health/', health_check, name='health_check'),
    path('performance/vitals/', performance_vitals, name='performance_vitals'),
    path('language/', set_site_language, name='set_site_language'),
    path('deal-room/', deal_room, name='my_deals'),
    path('deal/confirm/<int:deal_id>/', confirm_deal, name='confirm_deal'),
    path('deal/<int:deal_id>/', deal_detail, name='deal_detail'),
    path('withdraw/', request_withdrawal, name='request_withdrawal'),
    
    # Redirect legacy auth URLs to allauth endpoints
    path('login/', legacy_login_redirect, name='login'),
    path('register/', legacy_register_redirect, name='register'),
    path('logout/', legacy_logout_redirect, name='logout'),
    path('deal/create/', create_deal, name='create_deal'),
    path('deal/delete/<int:deal_id>/', delete_deal, name='delete_deal'),
    path('deal/auction/<int:deal_id>/', deal_auction_detail, name='deal_auction_detail'),
    path('deal/bid/submit/<int:deal_id>/', submit_bid, name='submit_bid'),
    path('bid/accept/<int:bid_id>/', accept_bid, name='accept_bid'),

    # Profile & Users
    path('profile/', profile, name='profile'),
    path('user/<int:user_id>/', user_profile, name='user_profile'),
    path('search/', search_user, name='search'),

    # Rooms
    path('rooms/create/', create_room, name='create_room'),
    path('rooms/join/', join_room, name='join_room'),
    path('rooms/<str:code>/', room_detail, name='room_detail'),
    path('rooms/<str:code>/close/', close_room, name='close_room'),
    path('rooms/<str:code>/reopen/', reopen_room, name='reopen_room'),
    path('rooms/<str:code>/delete/', delete_room, name='delete_room'),
    path('rooms/<str:code>/trade/', trade_room_action, name='trade_room_action'),

    # Friends
    path('friend/request/<int:user_id>/', send_friend_request, name='send_friend_request'),
    path('friend/accept/<int:request_id>/', accept_friend_request, name='accept_friend_request'),
    path('friends/', friends_list, name='friends_list'),

    # Chat
    path('chat/<int:friend_id>/', private_chat, name='private_chat'),
    path('chat/<int:friend_id>/poll/', poll_private_chat, name='poll_private_chat'),
    path('chat/message/<int:message_id>/attachment/', private_message_attachment, name='private_message_attachment'),
    path('chat/', chat_hub, name='chat_hub'),

    # Polling (AJAX)
    path('deal/<int:deal_id>/poll/', poll_deal_chat, name='poll_deal_chat'),

    # Escrow Rooms
    path('escrow/<int:deal_id>/', escrow_room, name='escrow_room'),
    path('escrow/<int:deal_id>/poll/', poll_escrow_room, name='poll_escrow_room'),
    path('rooms/<str:code>/poll/', poll_room_chat, name='poll_room_chat'),

    # Payments — Escrow System
    path('pay/<int:deal_id>/', create_payment, name='create_payment'),
    path('pay/<int:deal_id>/confirm/', payment_confirm, name='payment_confirm'),
    path('pay/<int:deal_id>/ccp/', ccp_checkout_submit, name='ccp_checkout_submit'),
    path('pay/<int:deal_id>/success/', payment_success_page, name='payment_success_page'),
    path('pay/<int:deal_id>/release/', payment_release, name='payment_release'),
    path('pay/<int:deal_id>/refund/', payment_refund, name='payment_refund'),
    path('invoices/<int:invoice_id>/', invoice_detail, name='invoice_detail'),
    path('payment/cancel/', payment_cancel, name='payment_cancel'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),

    # Support Tickets
    path('support/', my_tickets, name='my_tickets'),
    path('support/create/', create_ticket, name='create_ticket'),
    path('support/ticket/<int:ticket_id>/', ticket_detail, name='ticket_detail'),
    path('support/ticket/<int:ticket_id>/attachment/', ticket_attachment, name='ticket_attachment'),
    path('support/reply/<int:reply_id>/attachment/', ticket_reply_attachment, name='ticket_reply_attachment'),

    path('deal/message/<int:message_id>/attachment/', deal_message_attachment, name='deal_message_attachment'),

    # Staff Dashboard
    path('staff/', staff_dashboard, name='staff_dashboard'),
    path('staff/ticket/<int:ticket_id>/', staff_ticket_detail, name='staff_ticket_detail'),
    path('staff/pending-payments/', staff_pending_payments, name='staff_pending_payments'),
    path('staff/payment/<int:payment_id>/proof/', staff_payment_proof, name='staff_payment_proof'),
    path('staff/payment/<int:payment_id>/approve/', staff_approve_ccp, name='staff_approve_ccp'),
    path('staff/payment/<int:payment_id>/reject/', staff_reject_ccp, name='staff_reject_ccp'),
    path('escrow/', escrow_dashboard, name='escrow_dashboard'),
    # Info Pages
    path('deals/', listings_view, name='listings'),
    path('about/', about, name='about'),
    path('how-it-works/', how_it_works, name='how_it_works'),
    path('comment/delete/<int:comment_id>/', delete_comment, name='delete_comment'),
    #notifications
    path('notifications/', notifications_page, name='notifications'),
    path('notifications/<int:notif_id>/read/', mark_notification_read, name='mark_notification_read'),
    path('notifications/<int:notif_id>/delete/', delete_notification, name='delete_notification'),
    path('notifications/poll/', poll_notifications, name='poll_notifications'),
    #admin
    path('admin-panel/', admin_dashboard, name='admin_dashboard'),
    path('admin-panel/security/', admin_security_reports, name='admin_security_reports'),
    path('admin-panel/users/', admin_users_list, name='admin_users_list'),
    path('admin-panel/kyc/', admin_kyc_list, name='admin_kyc_list'),
    path('admin-panel/kyc/<int:profile_id>/document/', admin_kyc_document, name='admin_kyc_document'),
    path('admin-panel/withdrawals/', admin_withdrawals_list, name='admin_withdrawals_list'),
    path('admin-panel/rooms/', admin_rooms_list, name='admin_rooms_list'),
    # Review
    path('deal/<int:deal_id>/review/', create_review, name='create_review'),

    # سياسات و القوانين
    path('privacy/', privacy_policy, name='privacy'),
    path('terms/', terms_policy, name='terms'),
    path('returns/', returns_policy, name='returns'),
]

# Development-only error page previews.
if settings.DEBUG:
    urlpatterns += [
        path('403/', view_403, name='preview_403'),
        path('404/', view_404, name='preview_404'),
        path('500/', view_500, name='preview_500'),
        path('503/', view_503, name='preview_503'),
        path('test-403/', view_403, name='test_403'),
        path('test-404/', view_404, name='test_404'),
        path('test-500/', view_500, name='test_500'),
        path('test-503/', view_503, name='test_503'),
    ]

# Serve static files in development from STATICFILES_DIRS and app static dirs.
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

if not settings.DEBUG and not getattr(settings, "USE_S3_STORAGE", False):
    urlpatterns += [
        path("media/<path:relative_path>", public_media_file, name="public_media_file"),
    ]
