"""
Django Signals — بث الإشعارات اللحظية عبر WebSocket
عند إنشاء إشعار جديد، يتم بثه فوراً لقناة المستخدم
"""
from django.db.models.signals import post_migrate, post_save
from django.core.cache import cache
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .services.admin_roles import ensure_admin_role_groups


@receiver(post_save, sender='main.Notification')
def broadcast_notification(sender, instance, created, **kwargs):
    """يُبث عدد الإشعارات الجديد + تفاصيلها لحظياً عند إنشاء إشعار جديد"""
    cache_key = f"unread_notification_count:{instance.recipient_id}"
    if not created:
        cache.delete(cache_key)
        return

    channel_layer = get_channel_layer()
    group_name = f"notifications_{instance.recipient_id}"
    unread_count = sender.objects.filter(
        recipient=instance.recipient, is_read=False
    ).count()
    cache.set(cache_key, unread_count, 10)

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "send_notification",
            "count": unread_count,
            "title": instance.title or "",
            "body": instance.body or "",
            "url": instance.url or "",
        }
    )


@receiver(post_migrate)
def setup_admin_roles(sender, **kwargs):
    if getattr(sender, "name", "") != "main":
        return
    ensure_admin_role_groups()
