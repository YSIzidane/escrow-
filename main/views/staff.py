# ==================== Staff & Admin Views ====================
from functools import wraps
from datetime import timedelta
import mimetypes
import os

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import (
    AdminActionLog, Deal, DealMessage, Payment, PaymentAuditLog, PrivateMessage,
    SupportTicket, TicketReply, EscrowRoom, Notification, Profile, Room,
    TradeExchange, TransactionInvoice, WithdrawalRequest
)
from ..services.admin_roles import (
    ADMIN_ROLE_SPECS,
    get_user_role_keys,
    has_any_admin_role,
    has_role_or_legacy_staff,
)
from ..i18n import get_request_language, get_translation
from ..utils import model_table_exists
from ..validators import validate_public_attachment
from .notifications import create_notification


def _harden_staff_response(response):
    add_never_cache_headers(response)
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["X-Frame-Options"] = "DENY"
    response["Referrer-Policy"] = "same-origin"
    return response


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "ليس لديك صلاحية الوصول لهذه الصفحة.")
            return redirect('home')
        response = view_func(request, *args, **kwargs)
        return _harden_staff_response(response)
    return wrapper


def role_required(role_key):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not has_role_or_legacy_staff(request.user, role_key):
                messages.error(request, "You do not have the required role for this page.")
                return redirect('admin_dashboard')
            response = view_func(request, *args, **kwargs)
            return _harden_staff_response(response)
        return wrapper
    return decorator


def role_any_required(*role_keys):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not (request.user.is_superuser or any(has_role_or_legacy_staff(request.user, role_key) for role_key in role_keys)):
                messages.error(request, "You do not have the required role for this page.")
                return redirect('admin_dashboard')
            response = view_func(request, *args, **kwargs)
            return _harden_staff_response(response)
        return wrapper
    return decorator


def superuser_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_superuser:
            messages.error(request, "Only the platform owner can manage admin accounts.")
            return redirect('admin_dashboard')
        response = view_func(request, *args, **kwargs)
        return _harden_staff_response(response)
    return wrapper


def admin_dashboard_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not has_any_admin_role(request.user):
            messages.error(request, "You do not have permission to open the admin dashboard.")
            return redirect('home')
        response = view_func(request, *args, **kwargs)
        return _harden_staff_response(response)
    return wrapper


def _serve_protected_file(field_file):
    if not field_file or not getattr(field_file, "name", ""):
        raise Http404("Requested file does not exist.")

    guessed_content_type, _ = mimetypes.guess_type(field_file.name)
    content_type = guessed_content_type or "application/octet-stream"
    response = FileResponse(
        field_file.open("rb"),
        filename=os.path.basename(field_file.name),
        as_attachment=not content_type.startswith("image/"),
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["X-Frame-Options"] = "DENY"
    response["Referrer-Policy"] = "same-origin"
    return response


def _log_admin_action(*, actor, target_user, action, role_key="", role_name="", reason=""):
    AdminActionLog.objects.create(
        actor=actor,
        target_user=target_user,
        action=action,
        role_key=role_key,
        role_name=role_name,
        reason=reason,
    )


def _create_withdrawal_notification(withdrawal, title, body):
    create_notification(
        withdrawal.user,
        'withdrawal',
        title,
        body,
        reverse('request_withdrawal'),
    )


def _build_admin_control_context(user, current_page):
    role_keys = set(get_user_role_keys(user))
    if user.is_superuser:
        role_keys = set(ADMIN_ROLE_SPECS.keys())

    current_role_specs = []
    if user.is_superuser:
        current_role_specs.append(
            {
                'key': 'platform_owner',
                'name': 'Platform Owner',
                'description': 'Full administrative access across support, finance, users, and operations.',
            }
        )

    for role_key, spec in ADMIN_ROLE_SPECS.items():
        if role_key in role_keys:
            current_role_specs.append(
                {
                    'key': role_key,
                    'name': spec['name'],
                    'description': spec['description'],
                }
            )

    return {
        'admin_role_keys': role_keys,
        'current_role_specs': current_role_specs,
        'has_support_access': user.is_superuser or 'support_admin' in role_keys,
        'has_finance_access': user.is_superuser or 'finance_admin' in role_keys,
        'has_operations_access': user.is_superuser or 'operations_admin' in role_keys,
        'has_security_access': user.is_superuser or 'security_admin' in role_keys,
        'admin_current_page': current_page,
    }


def _is_report_ticket(ticket):
    return ticket.subject.startswith('[REPORT]')


def _can_review_ticket(user, ticket):
    if user.is_superuser or has_role_or_legacy_staff(user, 'support_admin'):
        return True
    return has_role_or_legacy_staff(user, 'security_admin') and _is_report_ticket(ticket)


@staff_required
@role_required('security_admin')
def admin_security_reports(request):
    admin_context = _build_admin_control_context(request.user, 'security')
    is_ar = get_request_language(request) == 'ar'
    labels = {
        'ticket_kind': 'بلاغ مستخدم' if is_ar else 'User report',
        'deal_kind': 'نزاع صفقة' if is_ar else 'Deal dispute',
        'trade_kind': 'نزاع تبديل' if is_ar else 'Trade-room dispute',
        'open_ticket': 'فتح البلاغ' if is_ar else 'Open ticket',
        'review_escrow': 'مراجعة الضمان' if is_ar else 'Review escrow',
        'open_room': 'فتح الغرفة' if is_ar else 'Open room',
        'escrow': 'ضمان' if is_ar else 'Escrow',
        'room': 'غرفة' if is_ar else 'Room',
        'deal_disputed': 'تم وضع الصفقة في حالة نزاع.' if is_ar else 'Deal was marked as disputed.',
        'trade_disputed': 'طلب أحد المشاركين تدخل الإدارة.' if is_ar else 'A room participant requested admin intervention.',
    }
    type_filter = request.GET.get('type', '').strip()
    status_filter = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()
    role_keys = set(admin_context['admin_role_keys'])
    can_open_support = request.user.is_superuser or bool({'support_admin', 'security_admin'} & role_keys)
    can_open_escrow = request.user.is_superuser or bool({'operations_admin', 'finance_admin', 'security_admin'} & role_keys)

    ticket_reports = SupportTicket.objects.filter(subject__startswith='[REPORT]').select_related(
        'user__profile', 'assigned_to', 'deal'
    )
    deal_disputes = Deal.objects.filter(Q(status='disputed') | ~Q(dispute_reason='')).select_related(
        'seller__profile', 'buyer__profile'
    )
    trade_disputes = TradeExchange.objects.filter(
        Q(status=TradeExchange.STATUS_DISPUTED) | ~Q(dispute_reason='')
    ).select_related('room__creator__profile', 'disputed_by__profile')

    if status_filter == 'open':
        ticket_reports = ticket_reports.exclude(status__in=['resolved', 'closed'])
        deal_disputes = deal_disputes.filter(status='disputed', dispute_resolved=False)
        trade_disputes = trade_disputes.filter(status=TradeExchange.STATUS_DISPUTED)
    elif status_filter == 'resolved':
        ticket_reports = ticket_reports.filter(status__in=['resolved', 'closed'])
        deal_disputes = deal_disputes.filter(Q(dispute_resolved=True) | ~Q(status='disputed'))
        trade_disputes = trade_disputes.exclude(status=TradeExchange.STATUS_DISPUTED)

    if search_query:
        ticket_reports = ticket_reports.filter(
            Q(ticket_number__icontains=search_query)
            | Q(subject__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(deal__product_title__icontains=search_query)
        )
        deal_disputes = deal_disputes.filter(
            Q(product_title__icontains=search_query)
            | Q(dispute_reason__icontains=search_query)
            | Q(seller__username__icontains=search_query)
            | Q(buyer__username__icontains=search_query)
        )
        trade_disputes = trade_disputes.filter(
            Q(room__code__icontains=search_query)
            | Q(room__title__icontains=search_query)
            | Q(dispute_reason__icontains=search_query)
            | Q(room__creator__username__icontains=search_query)
            | Q(disputed_by__username__icontains=search_query)
        )

    rows = []
    if type_filter in {'', 'tickets'}:
        for ticket in ticket_reports.order_by('-created_at')[:80]:
            is_open = ticket.status not in {'resolved', 'closed'}
            subject = ticket.subject.replace('[REPORT]', '', 1).strip() or ticket.subject
            rows.append({
                'kind': 'ticket',
                'kind_label': labels['ticket_kind'],
                'icon': 'fa-flag',
                'title': subject,
                'summary': ticket.description,
                'reporter': ticket.user.username,
                'target': ticket.deal.product_title if ticket.deal else ticket.get_category_display(),
                'status_label': ticket.get_status_display(),
                'status_class': 'is-danger' if is_open else 'is-success',
                'priority_label': ticket.get_priority_display(),
                'priority_class': 'is-danger' if ticket.priority == 'urgent' else 'is-warning' if ticket.priority == 'high' else '',
                'created_at': ticket.created_at,
                'reference': ticket.ticket_number,
                'url': reverse('staff_ticket_detail', args=[ticket.id]) if can_open_support else '',
                'action_label': labels['open_ticket'],
            })

    if type_filter in {'', 'deals'}:
        for deal in deal_disputes.order_by('-updated_at')[:80]:
            is_open = deal.status == 'disputed' and not deal.dispute_resolved
            rows.append({
                'kind': 'deal',
                'kind_label': labels['deal_kind'],
                'icon': 'fa-handshake',
                'title': deal.product_title,
                'summary': deal.dispute_reason or labels['deal_disputed'],
                'reporter': deal.buyer.username if deal.buyer else '-',
                'target': deal.seller.username,
                'status_label': deal.get_status_display(),
                'status_class': 'is-danger' if is_open else 'is-success',
                'priority_label': labels['escrow'],
                'priority_class': 'is-warning',
                'created_at': deal.updated_at,
                'reference': f'#{deal.id}',
                'url': reverse('escrow_room', args=[deal.id]) if can_open_escrow else reverse('deal_detail', args=[deal.id]),
                'action_label': labels['review_escrow'],
            })

    if type_filter in {'', 'trades'}:
        for exchange in trade_disputes.order_by('-updated_at')[:80]:
            is_open = exchange.status == TradeExchange.STATUS_DISPUTED
            rows.append({
                'kind': 'trade',
                'kind_label': labels['trade_kind'],
                'icon': 'fa-exchange-alt',
                'title': exchange.room.display_title,
                'summary': exchange.dispute_reason or labels['trade_disputed'],
                'reporter': exchange.disputed_by.username if exchange.disputed_by else '-',
                'target': exchange.room.creator.username,
                'status_label': exchange.get_status_display(),
                'status_class': 'is-danger' if is_open else 'is-success',
                'priority_label': labels['room'],
                'priority_class': 'is-warning',
                'created_at': exchange.disputed_at or exchange.updated_at,
                'reference': exchange.room.code,
                'url': reverse('room_detail', args=[exchange.room.code]),
                'action_label': labels['open_room'],
            })

    rows = sorted(rows, key=lambda row: row['created_at'], reverse=True)[:120]
    stats = {
        'total_open': (
            SupportTicket.objects.filter(subject__startswith='[REPORT]').exclude(status__in=['resolved', 'closed']).count()
            + Deal.objects.filter(status='disputed', dispute_resolved=False).count()
            + TradeExchange.objects.filter(status=TradeExchange.STATUS_DISPUTED).count()
        ),
        'ticket_reports': SupportTicket.objects.filter(subject__startswith='[REPORT]').count(),
        'deal_disputes': Deal.objects.filter(Q(status='disputed') | ~Q(dispute_reason='')).count(),
        'trade_disputes': TradeExchange.objects.filter(
            Q(status=TradeExchange.STATUS_DISPUTED) | ~Q(dispute_reason='')
        ).count(),
    }
    max_stat = max(stats['ticket_reports'], stats['deal_disputes'], stats['trade_disputes'], 1)
    stats_chart = [
        {
            'label': labels['ticket_kind'],
            'value': stats['ticket_reports'],
            'percent': int((stats['ticket_reports'] / max_stat) * 100),
            'icon': 'fa-flag',
            'class': 'is-ticket',
        },
        {
            'label': labels['deal_kind'],
            'value': stats['deal_disputes'],
            'percent': int((stats['deal_disputes'] / max_stat) * 100),
            'icon': 'fa-handshake',
            'class': 'is-deal',
        },
        {
            'label': labels['trade_kind'],
            'value': stats['trade_disputes'],
            'percent': int((stats['trade_disputes'] / max_stat) * 100),
            'icon': 'fa-exchange-alt',
            'class': 'is-trade',
        },
    ]

    return render(request, 'admin_security_reports.html', {
        'report_rows': rows,
        'stats': stats,
        'stats_chart': stats_chart,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search_query': search_query,
        'can_open_support': can_open_support,
        'can_open_escrow': can_open_escrow,
        **admin_context,
    })


@login_required(login_url='login')
def private_message_attachment(request, message_id):
    message = get_object_or_404(
        PrivateMessage.objects.select_related('sender', 'receiver'),
        id=message_id,
    )
    if request.user not in {message.sender, message.receiver}:
        raise Http404("You do not have access to this attachment.")
    if not message.file:
        raise Http404("No attachment is available for this message.")
    return _serve_protected_file(message.file)


@login_required(login_url='login')
def ticket_attachment(request, ticket_id):
    ticket = get_object_or_404(
        SupportTicket.objects.select_related('user'),
        id=ticket_id,
    )
    if request.user != ticket.user and not _can_review_ticket(request.user, ticket):
        raise Http404("You do not have access to this attachment.")
    if not ticket.attachment:
        raise Http404("No attachment is available for this ticket.")
    return _serve_protected_file(ticket.attachment)


@login_required(login_url='login')
def ticket_reply_attachment(request, reply_id):
    reply = get_object_or_404(
        TicketReply.objects.select_related('ticket__user'),
        id=reply_id,
    )
    if request.user != reply.ticket.user and not _can_review_ticket(request.user, reply.ticket):
        raise Http404("You do not have access to this attachment.")
    if not reply.attachment:
        raise Http404("No attachment is available for this reply.")
    return _serve_protected_file(reply.attachment)


@login_required(login_url='login')
def deal_message_attachment(request, message_id):
    message = get_object_or_404(
        DealMessage.objects.select_related('deal__buyer', 'deal__seller'),
        id=message_id,
    )
    can_view_as_admin = request.user.is_superuser or has_any_admin_role(
        request.user, {'operations_admin', 'finance_admin', 'security_admin'}
    )
    if request.user not in {message.deal.buyer, message.deal.seller} and not can_view_as_admin:
        raise Http404("You do not have access to this attachment.")
    if not message.file:
        raise Http404("No attachment is available for this message.")
    return _serve_protected_file(message.file)


@staff_required
@role_required('operations_admin')
def escrow_dashboard(request):
    admin_context = _build_admin_control_context(request.user, 'escrow')
    status_filter = request.GET.get('status', '')
    rooms = EscrowRoom.objects.select_related(
        'deal__buyer__profile', 'deal__seller__profile', 'deal__payment',
    ).order_by('-created_at')
    if status_filter == 'escrow_held':
        rooms = rooms.filter(deal__payment__status='escrow_held')
    elif status_filter == 'released':
        rooms = rooms.filter(deal__payment__status='released')
    elif status_filter == 'refunded':
        rooms = rooms.filter(deal__payment__status='refunded')
    elif status_filter == 'pending':
        rooms = rooms.filter(deal__payment__status='pending')
    stats = {
        'total': EscrowRoom.objects.count(),
        'held': EscrowRoom.objects.filter(deal__payment__status='escrow_held').count(),
        'released': EscrowRoom.objects.filter(deal__payment__status='released').count(),
        'refunded': EscrowRoom.objects.filter(deal__payment__status='refunded').count(),
    }
    return render(request, 'escrow_dashboard.html', {
        'rooms': rooms,
        'stats': stats,
        'status_filter': status_filter,
        **admin_context,
    })


@staff_required
@role_required('support_admin')
def staff_dashboard(request):
    admin_context = _build_admin_control_context(request.user, 'support')
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('q', '').strip()
    tickets = SupportTicket.objects.all().select_related('user__profile', 'assigned_to')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)
    if category_filter:
        tickets = tickets.filter(category=category_filter)
    if search_query:
        tickets = tickets.filter(
            Q(ticket_number__icontains=search_query)
            | Q(subject__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(user__username__icontains=search_query)
        )
    stats = {
        'open': SupportTicket.objects.filter(status='open').count(),
        'in_progress': SupportTicket.objects.filter(status='in_progress').count(),
        'resolved': SupportTicket.objects.filter(status='resolved').count(),
        'urgent': SupportTicket.objects.filter(priority='urgent').count(),
        'reports': SupportTicket.objects.filter(subject__startswith='[REPORT]').count(),
    }
    return render(request, 'support/staff_dashboard.html', {
        'tickets': tickets, 'stats': stats,
        'status_filter': status_filter, 'priority_filter': priority_filter, 'category_filter': category_filter,
        'search_query': search_query,
        **admin_context,
    })


@staff_required
@role_required('support_admin')
def admin_rooms_list(request):
    admin_context = _build_admin_control_context(request.user, 'rooms')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    search_query = request.GET.get('q', '').strip()

    rooms = Room.objects.select_related('creator__profile').annotate(
        participant_total=Count('participants', distinct=True),
        message_total=Count('messages', distinct=True),
    ).order_by('-created_at')

    if status_filter == 'active':
        rooms = rooms.filter(is_active=True)
    elif status_filter == 'closed':
        rooms = rooms.filter(is_active=False)

    if type_filter in {'buy', 'sell', 'trade'}:
        rooms = rooms.filter(room_type=type_filter)

    if search_query:
        rooms = rooms.filter(
            Q(code__icontains=search_query)
            | Q(title__icontains=search_query)
            | Q(creator__username__icontains=search_query)
            | Q(participants__user__username__icontains=search_query)
        ).distinct()

    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        action = request.POST.get('action')
        room = get_object_or_404(Room, id=room_id)

        if action == 'close' and room.is_active:
            room.is_active = False
            room.closed_at = timezone.now()
            room.save(update_fields=['is_active', 'closed_at'])
            messages.success(request, f"تم إغلاق الغرفة {room.code} من لوحة الإدارة.")
        elif action == 'reopen' and not room.is_active:
            room.is_active = True
            room.closed_at = None
            room.save(update_fields=['is_active', 'closed_at'])
            messages.success(request, f"تمت إعادة فتح الغرفة {room.code}.")
        elif action == 'delete':
            if not request.user.is_superuser:
                messages.error(request, "حذف الغرف نهائيًا متاح فقط لصاحب المنصة.")
            else:
                room.delete()
                messages.warning(request, "تم حذف الغرفة نهائيًا من النظام.")
        return redirect('admin_rooms_list')

    stats = {
        'total': Room.objects.count(),
        'active': Room.objects.filter(is_active=True).count(),
        'closed': Room.objects.filter(is_active=False).count(),
        'today': Room.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count(),
    }
    return render(request, 'admin_rooms.html', {
        'rooms': rooms[:100],
        'stats': stats,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        **admin_context,
    })


@staff_required
@role_any_required('support_admin', 'security_admin')
def staff_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    if not _can_review_ticket(request.user, ticket):
        messages.error(request, "Security admins can review report tickets only.")
        return redirect('admin_security_reports')
    replies = ticket.replies.all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'reply':
            msg = request.POST.get('message', '').strip()
            attachment = request.FILES.get('attachment')
            if msg:
                try:
                    validate_public_attachment(attachment)
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                    return redirect('staff_ticket_detail', ticket_id=ticket.id)
                TicketReply.objects.create(ticket=ticket, sender=request.user, message=msg, attachment=attachment, is_staff_reply=True)
                create_notification(
                    recipient=ticket.user, notif_type='ticket',
                    title=f'🎫 رد جديد على تذكرة #{ticket.ticket_number}',
                    body='قام الدعم الفني بالرد على تذكرتك.',
                    url=f'/support/ticket/{ticket.id}/',
                )
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
                    ticket.save()
                messages.success(request, "تم إرسال الرد!")
        elif action == 'change_status':
            new_status = request.POST.get('status')
            if new_status in ['open', 'in_progress', 'resolved', 'closed']:
                ticket.status = new_status
                ticket.save()
                messages.success(request, f"تم تغيير حالة التذكرة إلى: {ticket.get_status_display()}")
        elif action == 'change_priority':
            new_priority = request.POST.get('priority')
            if new_priority in ['low', 'medium', 'high', 'urgent']:
                ticket.priority = new_priority
                ticket.save()
                messages.success(request, "تم تحديث الأولوية!")
        elif action == 'assign':
            ticket.assigned_to = request.user
            ticket.save()
            messages.success(request, "تم تعيين التذكرة لك!")
        elif action == 'close_ticket':
            ticket.status = 'closed'
            ticket.save()
            messages.success(request, "تم إغلاق التذكرة.")
        elif action == 'delete_ticket':
            ticket.status = 'closed'
            ticket.save(update_fields=['status'])
            messages.success(request, "تم حذف التذكرة نهائياً.")
            return redirect('staff_dashboard')
        return redirect('staff_ticket_detail', ticket_id=ticket.id)
    return render(request, 'support/staff_ticket_detail.html', {'ticket': ticket, 'replies': replies})


@admin_dashboard_required
def admin_dashboard(request):
    admin_context = _build_admin_control_context(request.user, 'dashboard')
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    last_7_start = (now - timedelta(days=6)).date()
    last_30_start = (now - timedelta(days=29)).date()
    has_invoice_table = model_table_exists(TransactionInvoice)
    released_payments = Payment.objects.filter(status='released')
    role_keys = admin_context['admin_role_keys']

    weekly_deals_raw = (
        Deal.objects.filter(created_at__date__gte=last_7_start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Count('id'))
    )
    weekly_deals_map = {row['day']: row['total'] for row in weekly_deals_raw}
    weekly_deal_labels = []
    weekly_deal_values = []
    for offset in range(7):
        day = last_7_start + timedelta(days=offset)
        weekly_deal_labels.append(day.strftime("%d/%m"))
        weekly_deal_values.append(weekly_deals_map.get(day, 0))

    monthly_payments_raw = (
        released_payments.filter(released_at__date__gte=last_30_start)
        .annotate(day=TruncDate('released_at'))
        .values('day')
        .annotate(total=Sum('amount'))
    )
    monthly_payments_map = {row['day']: float(row['total'] or 0) for row in monthly_payments_raw}
    payment_activity_labels = []
    payment_activity_values = []
    for offset in range(30):
        day = last_30_start + timedelta(days=offset)
        payment_activity_labels.append(day.strftime("%d/%m"))
        payment_activity_values.append(monthly_payments_map.get(day, 0))

    stripe_configured = all(
        [
            getattr(settings, "STRIPE_PUBLIC_KEY", "") not in ("", "pk_test_..."),
            getattr(settings, "STRIPE_SECRET_KEY", "") not in ("", "sk_test_..."),
            getattr(settings, "STRIPE_WEBHOOK_SECRET", "") not in ("", "whsec_..."),
        ]
    )
    security_checks = [
        {'label': 'DEBUG', 'ok': not settings.DEBUG, 'value': 'Off' if not settings.DEBUG else 'On'},
        {'label': 'HTTPS redirect', 'ok': settings.SECURE_SSL_REDIRECT, 'value': 'Enabled' if settings.SECURE_SSL_REDIRECT else 'Disabled'},
        {'label': 'Secure session cookie', 'ok': settings.SESSION_COOKIE_SECURE, 'value': 'Enabled' if settings.SESSION_COOKIE_SECURE else 'Disabled'},
        {'label': 'Secure CSRF cookie', 'ok': settings.CSRF_COOKIE_SECURE, 'value': 'Enabled' if settings.CSRF_COOKIE_SECURE else 'Disabled'},
        {'label': 'Session SameSite', 'ok': str(settings.SESSION_COOKIE_SAMESITE).lower() in {'lax', 'strict'}, 'value': settings.SESSION_COOKIE_SAMESITE},
    ]
    system_checks = [
        {'label': 'Site URL', 'ok': bool(getattr(settings, 'SITE_URL', '').strip()), 'value': getattr(settings, 'SITE_URL', '').strip() or 'Not configured'},
        {'label': 'Redis transport', 'ok': bool(getattr(settings, 'REDIS_URL', '').strip()), 'value': 'Configured' if getattr(settings, 'REDIS_URL', '').strip() else 'In-memory fallback'},
        {'label': 'Email delivery', 'ok': bool(getattr(settings, 'EMAIL_HOST_USER', '').strip()), 'value': getattr(settings, 'EMAIL_HOST_USER', '').strip() or 'Console / missing SMTP'},
        {'label': 'Stripe', 'ok': stripe_configured, 'value': 'Configured' if stripe_configured else 'Not configured'},
        {'label': 'Storage', 'ok': True, 'value': 'S3 object storage' if getattr(settings, 'USE_S3_STORAGE', False) else 'Local media storage'},
    ]

    context = {
        'total_users': User.objects.count(),
        'new_users_week': User.objects.filter(date_joined__gte=week_ago).count(),
        'staff_users': User.objects.filter(is_staff=True).count(),
        'total_deals': Deal.objects.count(),
        'active_deals': Deal.objects.filter(status__in=['new', 'reserved', 'shipped']).count(),
        'completed_deals': Deal.objects.filter(status='completed').count(),
        'disputed_deals': Deal.objects.filter(status='disputed').count(),
        'total_revenue': Payment.objects.filter(status='released').aggregate(s=Sum('amount'))['s'] or 0,
        'total_commission': Payment.objects.filter(status='released').aggregate(s=Sum('fee_amount'))['s'] or 0,
        'invoice_count': TransactionInvoice.objects.count() if has_invoice_table else 0,
        'escrow_held': Payment.objects.filter(status='escrow_held').aggregate(s=Sum('amount'))['s'] or 0,
        'open_tickets': SupportTicket.objects.filter(status='open').count(),
        'urgent_tickets': SupportTicket.objects.filter(status='open', priority='urgent').count(),
        'active_private_rooms': Room.objects.filter(is_active=True).count(),
        'closed_private_rooms': Room.objects.filter(is_active=False).count(),
        'pending_kyc': Profile.objects.filter(kyc_status='pending').count(),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='pending').count(),
        'pending_manual_payments': Payment.objects.filter(payment_method='ccp', status='pending_manual_verification').count(),
        'recent_deals': Deal.objects.select_related('seller', 'buyer').order_by('-created_at')[:8],
        'recent_tickets': SupportTicket.objects.select_related('user').order_by('-created_at')[:6],
        'recent_admin_actions': AdminActionLog.objects.select_related('actor', 'target_user')[:6],
        'recent_payment_audits': PaymentAuditLog.objects.select_related('payment__deal', 'admin').order_by('-created_at')[:6],
        'recent_withdrawal_reviews': WithdrawalRequest.objects.select_related('user__profile', 'reviewed_by').exclude(status='pending').order_by('-reviewed_at', '-created_at')[:6],
        'deals_by_status': list(Deal.objects.values('status').annotate(c=Count('id'))),
        'weekly_deal_labels': weekly_deal_labels,
        'weekly_deal_values': weekly_deal_values,
        'payment_activity_labels': payment_activity_labels,
        'payment_activity_values': payment_activity_values,
        'security_checks': security_checks,
        'system_checks': system_checks,
        **admin_context,
    }
    return render(request, 'admin_dashboard.html', context)


@superuser_required
def admin_users_list(request):
    admin_context = _build_admin_control_context(request.user, 'users')
    has_invoice_table = model_table_exists(TransactionInvoice)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        role_key = request.POST.get('role_key')
        target_user = get_object_or_404(User, id=user_id)

        if target_user == request.user and action in {'revoke_staff', 'deactivate'}:
            messages.error(request, "You cannot remove your own admin access or deactivate yourself here.")
            return redirect('admin_users_list')

        if action == 'grant_staff':
            target_user.is_staff = True
            target_user.save(update_fields=['is_staff'])
            _log_admin_action(actor=request.user, target_user=target_user, action='grant_staff')
            messages.success(request, f"{target_user.username} now has admin access.")
        elif action == 'revoke_staff':
            target_user.is_staff = False
            admin_groups = list(Group.objects.filter(name__in=[spec['name'] for spec in ADMIN_ROLE_SPECS.values()]))
            if admin_groups:
                target_user.groups.remove(*admin_groups)
            target_user.save(update_fields=['is_staff'])
            _log_admin_action(actor=request.user, target_user=target_user, action='revoke_staff')
            messages.warning(request, f"Admin access removed from {target_user.username}.")
        elif action == 'activate':
            target_user.is_active = True
            target_user.save(update_fields=['is_active'])
            _log_admin_action(actor=request.user, target_user=target_user, action='activate')
            messages.success(request, f"Account {target_user.username} activated.")
        elif action == 'deactivate':
            target_user.is_active = False
            target_user.save(update_fields=['is_active'])
            _log_admin_action(actor=request.user, target_user=target_user, action='deactivate')
            messages.warning(request, f"Account {target_user.username} deactivated.")
        elif action in {'assign_role', 'remove_role'} and role_key in ADMIN_ROLE_SPECS:
            group = Group.objects.get(name=ADMIN_ROLE_SPECS[role_key]['name'])
            if action == 'assign_role':
                target_user.groups.add(group)
                target_user.is_staff = True
                target_user.save(update_fields=['is_staff'])
                _log_admin_action(
                    actor=request.user,
                    target_user=target_user,
                    action='assign_role',
                    role_key=role_key,
                    role_name=group.name,
                )
                messages.success(request, f"Role {group.name} assigned to {target_user.username}.")
            else:
                target_user.groups.remove(group)
                remaining_admin_groups = target_user.groups.filter(
                    name__in=[spec['name'] for spec in ADMIN_ROLE_SPECS.values()]
                ).exists()
                if not remaining_admin_groups:
                    target_user.is_staff = False
                    target_user.save(update_fields=['is_staff'])
                _log_admin_action(
                    actor=request.user,
                    target_user=target_user,
                    action='remove_role',
                    role_key=role_key,
                    role_name=group.name,
                )
                messages.warning(request, f"Role {group.name} removed from {target_user.username}.")

        return redirect('admin_users_list')

    search_query = request.GET.get('q', '').strip()
    staff_filter = request.GET.get('staff', '')
    users = User.objects.select_related('profile').prefetch_related('groups').order_by('-date_joined')

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    if staff_filter == 'staff':
        users = users.filter(is_staff=True)
    elif staff_filter == 'regular':
        users = users.filter(is_staff=False)
    elif staff_filter == 'inactive':
        users = users.filter(is_active=False)

    role_names = [spec['name'] for spec in ADMIN_ROLE_SPECS.values()]
    user_rows = []
    for user in users[:80]:
        group_names = [group.name for group in user.groups.all()]
        user_rows.append({
            'user': user,
            'group_names': group_names,
            'role_keys': get_user_role_keys(user),
            'admin_group_names': [name for name in group_names if name in role_names],
        })

    context = {
        'user_rows': user_rows,
        'search_query': search_query,
        'staff_filter': staff_filter,
        'role_specs': ADMIN_ROLE_SPECS,
        'staff_count': User.objects.filter(is_staff=True).count(),
        'active_count': User.objects.filter(is_active=True).count(),
        'inactive_count': User.objects.filter(is_active=False).count(),
        'invoice_count': TransactionInvoice.objects.count() if has_invoice_table else 0,
        **admin_context,
    }
    return render(request, 'admin_users.html', context)


@staff_required
@role_required('operations_admin')
def admin_kyc_list(request):
    admin_context = _build_admin_control_context(request.user, 'kyc')
    kyc_profiles = Profile.objects.exclude(kyc_status='unsubmitted').order_by('-user__date_joined')
    status_filter = request.GET.get('status', '')
    if status_filter:
        kyc_profiles = kyc_profiles.filter(kyc_status=status_filter)
    if request.method == 'POST':
        profile_id = request.POST.get('profile_id')
        action = request.POST.get('action')
        prof = get_object_or_404(Profile, id=profile_id)
        if action == 'approve':
            prof.kyc_status = 'approved'
            prof.is_verified = True
            messages.success(request, f"تم توثيق حساب {prof.user.username} بنجاح.")
        elif action == 'reject':
            prof.kyc_status = 'rejected'
            prof.is_verified = False
            messages.warning(request, f"تم رفض توثيق حساب {prof.user.username}.")
        prof.save()
        return redirect('admin_kyc_list')
    return render(request, 'admin_kyc.html', {
        'kyc_profiles': kyc_profiles,
        'status_filter': status_filter,
        **admin_context,
    })


@staff_required
@role_required('operations_admin')
def admin_kyc_document(request, profile_id):
    prof = get_object_or_404(Profile.objects.select_related('user'), id=profile_id)
    if not prof.kyc_document:
        raise Http404("No KYC document is available for this profile.")
    return _serve_protected_file(prof.kyc_document)


@staff_required
@role_required('finance_admin')
def admin_withdrawals_list(request):
    admin_context = _build_admin_control_context(request.user, 'withdrawals')
    withdrawals = WithdrawalRequest.objects.select_related('user__profile', 'reviewed_by').order_by('-created_at')
    status_filter = request.GET.get('status', '').strip()
    method_filter = request.GET.get('method', '').strip()
    search_query = request.GET.get('q', '').strip()
    if status_filter in {'pending', 'processed', 'rejected'}:
        withdrawals = withdrawals.filter(status=status_filter)
    if method_filter in {'paypal', 'bank', 'crypto'}:
        withdrawals = withdrawals.filter(method=method_filter)
    if search_query:
        filters = (
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(details__icontains=search_query)
            | Q(payout_reference__icontains=search_query)
        )
        if search_query.isdigit():
            filters |= Q(id=int(search_query))
        withdrawals = withdrawals.filter(filters)
    stats = {
        'total': WithdrawalRequest.objects.count(),
        'pending': WithdrawalRequest.objects.filter(status='pending').count(),
        'processed': WithdrawalRequest.objects.filter(status='processed').count(),
        'rejected': WithdrawalRequest.objects.filter(status='rejected').count(),
        'pending_amount': WithdrawalRequest.objects.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0,
    }
    if request.method == 'POST':
        req_id = request.POST.get('req_id', '').strip()
        action = request.POST.get('action', '').strip()
        payout_reference = request.POST.get('payout_reference', '').strip()
        admin_note = request.POST.get('admin_note', '').strip()
        rejection_reason = request.POST.get('rejection_reason', '').strip()
        if not req_id:
            messages.error(request, "The withdrawal request could not be identified.")
            return redirect('admin_withdrawals_list')
        with transaction.atomic():
            w_req = get_object_or_404(
                WithdrawalRequest.objects.select_for_update(),
                id=req_id,
            )
            if w_req.status != 'pending':
                messages.warning(request, f"Withdrawal request #{w_req.id} has already been reviewed.")
                return redirect('admin_withdrawals_list')
            if action == 'process':
                if not payout_reference:
                    messages.error(request, "Please enter the payout reference before confirming the transfer.")
                    return redirect('admin_withdrawals_list')
                w_req.status = 'processed'
                w_req.reviewed_by = request.user
                w_req.reviewed_at = timezone.now()
                w_req.payout_reference = payout_reference
                w_req.admin_note = admin_note
                w_req.rejection_reason = ''
                w_req.save()
                _create_withdrawal_notification(
                    w_req,
                    "Withdrawal approved",
                    f"Your withdrawal request for ${w_req.amount} was approved. Reference: {payout_reference}.",
                )
                messages.success(request, f"Withdrawal request #{w_req.id} was marked as transferred.")
                return redirect('admin_withdrawals_list')
            elif action == 'reject':
                if not rejection_reason:
                    messages.error(request, "Please enter the rejection reason before returning the funds.")
                    return redirect('admin_withdrawals_list')
                w_req.status = 'rejected'
                w_req.reviewed_by = request.user
                w_req.reviewed_at = timezone.now()
                w_req.rejection_reason = rejection_reason
                w_req.admin_note = admin_note
                w_req.payout_reference = ''
                w_req.save()
                profile = Profile.objects.select_for_update().get(user=w_req.user)
                profile.balance += w_req.amount
                profile.save()
                _create_withdrawal_notification(
                    w_req,
                    "Withdrawal returned",
                    f"Your withdrawal request for ${w_req.amount} was rejected and the balance was returned to your wallet.",
                )
                messages.warning(request, f"Withdrawal request #{w_req.id} was rejected and the balance was restored.")
                return redirect('admin_withdrawals_list')
            messages.error(request, "Unsupported withdrawal action.")
            return redirect('admin_withdrawals_list')
    return render(request, 'admin_withdrawals.html', {
        'withdrawals': withdrawals,
        'status_filter': status_filter,
        'method_filter': method_filter,
        'search_query': search_query,
        'stats': stats,
        **admin_context,
    })


@staff_required
@role_required('finance_admin')
def staff_payment_proof(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, payment_method='ccp')
    if not payment.proof_file:
        raise Http404("No proof file is available for this payment.")
    return _serve_protected_file(payment.proof_file)


@staff_required
@role_required('finance_admin')
def staff_pending_payments(request):
    """عرض الدفعات المعلقة لمراجعة المشرفين."""
    admin_context = _build_admin_control_context(request.user, 'payments')
    search_query = request.GET.get('q', '').strip()
    payments = Payment.objects.filter(
        payment_method='ccp',
        status='pending_manual_verification',
    ).select_related('deal__seller__profile', 'deal__buyer__profile', 'payer__profile').order_by('-created_at')
    if search_query:
        filters = (
            Q(deal__product_title__icontains=search_query)
            | Q(payer__username__icontains=search_query)
            | Q(deal__seller__username__icontains=search_query)
            | Q(reference_number__icontains=search_query)
            | Q(transaction_id__icontains=search_query)
            | Q(transfer_code__icontains=search_query)
        )
        if search_query.isdigit():
            filters |= Q(deal__id=int(search_query)) | Q(id=int(search_query))
        payments = payments.filter(filters)
    stats = {
        'pending_count': Payment.objects.filter(payment_method='ccp', status='pending_manual_verification').count(),
        'pending_amount': Payment.objects.filter(payment_method='ccp', status='pending_manual_verification').aggregate(total=Sum('amount'))['total'] or 0,
        'rejected_total': Payment.objects.filter(payment_method='ccp').exclude(rejection_count=0).count(),
    }

    return render(request, 'staff/pending_payments.html', {
        'payments': payments,
        'pending_count': payments.count(),
        'search_query': search_query,
        'stats': stats,
        **admin_context,
    })


@staff_required
@role_required('finance_admin')
@require_POST
def staff_approve_ccp(request, payment_id):
    """الموافقة على دفعة CCP - يمر عبر المنطق المشترك."""
    from ..services.payment_service import process_successful_payment

    review_note = request.POST.get('review_note', '').strip()
    if not review_note:
        messages.error(request, "يجب إدخال ملاحظة مراجعة قبل قبول الدفعة.")
        return redirect('staff_pending_payments')

    payment = get_object_or_404(
        Payment.objects.select_related('deal', 'payer'),
        id=payment_id,
        payment_method='ccp',
    )

    with transaction.atomic():
        locked_deal = Deal.objects.select_for_update().get(id=payment.deal_id)
        locked_payment = Payment.objects.select_for_update().get(id=payment.id)

        if locked_payment.status != 'pending_manual_verification':
            messages.warning(request, "هذه الدفعة ليست في انتظار المراجعة.")
            return redirect('staff_pending_payments')

        approved_payment, _ = process_successful_payment(
            deal=locked_deal,
            buyer=locked_payment.payer,
            transaction_id=locked_payment.transaction_id,
            payment_method='ccp',
        )

        PaymentAuditLog.objects.create(
            payment=approved_payment,
            admin=request.user,
            action='approved',
            reason=review_note,
        )

    # Notify buyer
    create_notification(
        recipient=payment.payer,
        notif_type='payment',
        title=f'✅ تم قبول الدفع — صفقة #{payment.deal.id}',
        body=f'تم التحقق من إثبات الدفع بنجاح! المبلغ ${payment.amount} الآن محتجز في الضمان.',
        url=f'/escrow/{payment.deal.id}/',
    )

    messages.success(request, f"✅ تم قبول الدفعة #{payment.id} وفتح غرفة الضمان.")
    return redirect('staff_pending_payments')


@staff_required
@role_required('finance_admin')
@require_POST
def staff_reject_ccp(request, payment_id):
    from .payments import clear_unheld_payment_reservation

    """رفض دفعة CCP مع تسجيل السبب."""
    MAX_RETRIES = 3

    payment = get_object_or_404(Payment, id=payment_id, payment_method='ccp')

    if payment.status != 'pending_manual_verification':
        messages.warning(request, "هذه الدفعة ليست في انتظار المراجعة.")
        return redirect('staff_pending_payments')

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, "يجب إدخال سبب الرفض.")
        return redirect('staff_pending_payments')

    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().get(id=payment.id)
        locked_deal = Deal.objects.select_for_update().get(id=locked_payment.deal_id)
        locked_payment.rejection_count += 1
        locked_payment.rejection_reason = reason

        if locked_payment.rejection_count >= MAX_RETRIES:
            locked_payment.status = 'failed_max_retries'
            locked_payment.save()
            clear_unheld_payment_reservation(locked_deal, locked_payment)

            # Notify buyer of final rejection
            create_notification(
                recipient=locked_payment.payer,
                notif_type='payment',
                title=f'❌ تم رفض الدفع نهائياً — صفقة #{locked_payment.deal.id}',
                body=f'تم رفض إثبات الدفع {MAX_RETRIES} مرات. تم إلغاء العملية. السبب: {reason}',
                url=f'/deal/{locked_payment.deal.id}/',
            )
            messages.warning(request, f"تم رفض الدفعة #{payment.id} نهائياً (تجاوز الحد الأقصى {MAX_RETRIES} محاولات).")
        else:
            locked_payment.status = 'pending'
            locked_payment.proof_file = None
            locked_payment.reference_number = None
            locked_payment.save()
            clear_unheld_payment_reservation(locked_deal, locked_payment)

            remaining = MAX_RETRIES - locked_payment.rejection_count
            # Notify buyer to re-upload
            create_notification(
                recipient=locked_payment.payer,
                notif_type='payment',
                title=f'⚠️ تم رفض إثبات الدفع — صفقة #{locked_payment.deal.id}',
                body=f'السبب: {reason}. يرجى رفع إثبات جديد. لديك {remaining} محاولة متبقية.',
                url=f'/pay/{locked_payment.deal.id}/',
            )
            messages.info(request, f"تم رفض الدفعة #{payment.id} وإعلام المشتري ({remaining} محاولة متبقية).")

    # Audit log
    PaymentAuditLog.objects.create(
        payment=payment,
        admin=request.user,
        action='rejected',
        reason=reason,
    )

    return redirect('staff_pending_payments')


# ==================== Support Tickets (User-facing) ====================
@login_required(login_url='login')
def my_tickets(request):
    tickets = (
        SupportTicket.objects
        .filter(user=request.user)
        .select_related('deal')
        .annotate(reply_count=Count('replies'))
    )
    ticket_stats = {
        'total': tickets.count(),
        'open': tickets.filter(status='open').count(),
        'in_progress': tickets.filter(status='in_progress').count(),
        'resolved': tickets.filter(status='resolved').count(),
        'urgent': tickets.filter(priority='urgent').count(),
    }
    return render(request, 'support/my_tickets.html', {
        'tickets': tickets,
        'ticket_stats': ticket_stats,
    })


@login_required(login_url='login')
def create_ticket(request):
    mode = (request.GET.get('mode') or request.POST.get('mode') or '').strip().lower()
    is_report_mode = mode == 'report'
    user_deals = Deal.objects.filter(Q(seller=request.user) | Q(buyer=request.user)).order_by('-created_at')
    prefill_deal = None
    raw_deal_id = (request.GET.get('deal_id') or request.POST.get('deal_id') or '').strip()
    if raw_deal_id:
        try:
            prefill_deal = Deal.objects.select_related('seller__profile', 'buyer__profile').get(id=raw_deal_id)
        except Deal.DoesNotExist:
            prefill_deal = None

    report_target_user = None
    raw_reported_user_id = (request.GET.get('reported_user_id') or request.POST.get('reported_user_id') or '').strip()
    if raw_reported_user_id:
        try:
            report_target_user = User.objects.select_related('profile').get(id=raw_reported_user_id)
        except User.DoesNotExist:
            report_target_user = None

    context = {
        'user_deals': user_deals,
        'is_report_mode': is_report_mode,
        'mode': mode,
        'prefill_deal': prefill_deal,
        'report_target_user': report_target_user,
    }

    if request.method == 'POST':
        language = get_request_language(request)
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'other')
        priority = request.POST.get('priority', 'high' if is_report_mode else 'medium')
        deal_id = request.POST.get('deal_id')
        attachment = request.FILES.get('attachment')

        if not subject or not description:
            messages.error(request, get_translation('support.create.required_error', language))
            return render(request, 'support/create_ticket.html', context)

        allowed_priorities = {choice[0] for choice in SupportTicket.PRIORITY_CHOICES}
        if priority not in allowed_priorities:
            priority = 'high' if is_report_mode else 'medium'

        deal = None
        if deal_id:
            try:
                if is_report_mode:
                    deal = Deal.objects.get(id=deal_id)
                else:
                    deal = Deal.objects.get(Q(id=deal_id) & (Q(seller=request.user) | Q(buyer=request.user)))
            except Deal.DoesNotExist:
                deal = None

        if is_report_mode:
            if not subject.startswith('[REPORT]'):
                subject = f'[REPORT] {subject}'
            if category == 'other':
                category = 'deal' if deal else 'account'
            report_context = []
            if report_target_user:
                report_context.append(f'Reported user: {report_target_user.username}')
            if deal:
                report_context.append(f'Related deal: #{deal.id} - {deal.product_title}')
            if report_context:
                description = f"{description}\n\n--- REPORT CONTEXT ---\n" + "\n".join(report_context)

        try:
            validate_public_attachment(attachment)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, 'support/create_ticket.html', context)

        ticket = SupportTicket.objects.create(
            user=request.user,
            subject=subject,
            description=description,
            category=category,
            deal=deal,
            attachment=attachment,
            priority=priority,
        )
        if is_report_mode:
            prefix = get_translation('support.report.success_prefix', language)
        else:
            prefix = get_translation('support.create.success_prefix', language)
        messages.success(request, f'{prefix} {ticket.ticket_number}')
        return redirect('ticket_detail', ticket_id=ticket.id)

    return render(request, 'support/create_ticket.html', context)


@login_required(login_url='login')
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
    replies = ticket.replies.all()
    if request.method == 'POST':
        language = get_request_language(request)
        msg = request.POST.get('message', '').strip()
        attachment = request.FILES.get('attachment')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if msg:
            try:
                validate_public_attachment(attachment)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect('ticket_detail', ticket_id=ticket.id)
            TicketReply.objects.create(ticket=ticket, sender=request.user, message=msg, attachment=attachment, is_staff_reply=False)
            if ticket.assigned_to:
                create_notification(
                    recipient=ticket.assigned_to, notif_type='ticket',
                    title=f'رد جديد من {request.user.username} - #{ticket.ticket_number}',
                    body=f'{msg[:50]}...', url=f'/staff/ticket/{ticket.id}/',
                )
            if is_ajax:
                from django.http import JsonResponse
                return JsonResponse({'status': 'ok', 'message': msg, 'sender': request.user.username})
            messages.success(request, get_translation('support.detail.reply_success', language))
        return redirect('ticket_detail', ticket_id=ticket.id)
    return render(request, 'support/ticket_detail.html', {'ticket': ticket, 'replies': replies})
