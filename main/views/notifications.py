from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.urls import reverse

from ..models import (
    Notification, Room, RoomMessage,
    Friendship, PrivateMessage,
    Deal, DealMessage, EscrowRoom,
)
from ..services.admin_roles import has_any_admin_role
from ..services.verification import render_verification_badge
from ..utils import safe_file_url


def _notification_count_cache_key(user_id):
    return f"unread_notification_count:{user_id}"


def create_notification(
    recipient,
    notif_type,
    title,
    body='',
    url='',
    *,
    deal=None,
    actor=None,
    action='',
    priority='normal',
    channel='in_app',
    metadata=None,
):
    """دالة مساعدة لإنشاء إشعار"""
    notification = Notification.objects.create(
        recipient=recipient, notif_type=notif_type,
        title=title, body=body, url=url,
        deal=deal, actor=actor, action=action,
        priority=priority, channel=channel,
        metadata=metadata or {},
    )
    return notification


@login_required(login_url='login')
def notifications_page(request):
    notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    if request.method == 'POST' and request.POST.get('action') == 'mark_all_read':
        notifs.update(is_read=True)
        cache.delete(_notification_count_cache_key(request.user.pk))
        return redirect('notifications')
    unread_count = notifs.filter(is_read=False).count()
    total_count = notifs.count()
    return render(request, 'notifications.html', {
        'notifications': notifs[:50],
        'unread_count': unread_count,
        'total_count': total_count,
    })


@login_required(login_url='login')
@require_POST
def mark_notification_read(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.is_read = True
    notif.save()
    cache.delete(_notification_count_cache_key(request.user.pk))
    return redirect(notif.url or 'notifications')


@login_required(login_url='login')
@require_POST
def delete_notification(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.delete()
    cache.delete(_notification_count_cache_key(request.user.pk))
    return redirect('notifications')


@login_required(login_url='login')
def poll_notifications(request):
    cache_key = _notification_count_cache_key(request.user.pk)
    count = cache.get(cache_key)
    if count is None:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        cache.set(cache_key, count, 10)
    return JsonResponse({'count': count, 'unread_count': count})


@login_required(login_url='login')
def poll_escrow_room(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)
    is_admin = request.user.is_superuser or has_any_admin_role(
        request.user, {"operations_admin", "finance_admin"}
    )
    if request.user != deal.buyer and request.user != deal.seller and not is_admin:
        return JsonResponse({'messages': []})
    room = getattr(deal, 'escrow_room', None)
    if not room:
        return JsonResponse({'messages': []})
    after_id = int(request.GET.get('after', 0))
    msgs = room.messages.filter(id__gt=after_id).select_related('sender__profile')
    data = [{
        'id': m.id, 'text': m.text, 'time': m.created_at.strftime('%H:%M'),
        'avatar': safe_file_url(m.sender.profile.avatar), 'is_me': m.sender == request.user,
        'is_admin': m.is_admin, 'username': m.sender.username,
    } for m in msgs]
    return JsonResponse({'messages': data})


@login_required(login_url='login')
def poll_room_chat(request, code):
    room = get_object_or_404(Room, code__iexact=code)
    if not room.can_user_access(request.user):
        return JsonResponse({'messages': []}, status=403)
    after_id = request.GET.get('after', '0')
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0
    msgs = RoomMessage.objects.filter(room=room, id__gt=after_id).select_related('sender__profile').order_by('created_at')
    data = [{
        'id': m.id, 'text': m.text, 'time': m.created_at.strftime('%H:%M'),
        'avatar': safe_file_url(m.sender.profile.avatar), 'is_me': m.sender == request.user,
        'username': m.sender.username, 'user_id': m.sender_id,
    } for m in msgs]
    return JsonResponse({'messages': data})


@login_required(login_url='login')
def poll_private_chat(request, friend_id):
    friend = get_object_or_404(User, id=friend_id)
    if request.user == friend:
        return JsonResponse({'messages': []})
    is_friend = Friendship.objects.filter(
        (Q(from_user=request.user, to_user=friend) | Q(from_user=friend, to_user=request.user)),
        status='accepted'
    ).exists()
    if not is_friend:
        return JsonResponse({'messages': []})
    after_id = request.GET.get('after', '0')
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0
    msgs = PrivateMessage.objects.filter(
        (Q(sender=request.user, receiver=friend) | Q(sender=friend, receiver=request.user)),
        id__gt=after_id,
    ).select_related('sender__profile').order_by('created_at')
    data = [{
        'id': m.id, 'text': m.text, 'time': m.created_at.strftime('%H:%M'),
        'avatar': safe_file_url(m.sender.profile.avatar), 'is_me': m.sender == request.user,
        'username': m.sender.username,
        'file_url': reverse('private_message_attachment', args=[m.id]) if m.file else '',
        'verification_badge': render_verification_badge(m.sender.profile),
    } for m in msgs]
    return JsonResponse({'messages': data})


@login_required(login_url='login')
def poll_deal_chat(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)
    is_admin = request.user.is_superuser or has_any_admin_role(
        request.user, {"operations_admin", "finance_admin"}
    )
    if request.user != deal.buyer and request.user != deal.seller and not is_admin:
        return JsonResponse({'messages': []}, status=403)

    after_id = request.GET.get('after', '0')
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    msgs = DealMessage.objects.filter(
        deal=deal,
        id__gt=after_id,
    ).select_related('sender__profile').order_by('created_at')
    data = [{
        'id': m.id,
        'text': m.text,
        'time': m.created_at.strftime('%H:%M'),
        'avatar': safe_file_url(m.sender.profile.avatar),
        'is_me': m.sender == request.user,
        'username': m.sender.username,
        'file_url': reverse('deal_message_attachment', args=[m.id]) if m.file else '',
        'verification_badge': render_verification_badge(m.sender.profile),
    } for m in msgs]
    return JsonResponse({'messages': data})
