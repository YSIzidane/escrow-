import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from main.services.verification import render_verification_badge
from main.services.admin_roles import has_any_admin_role
from main.utils import safe_file_url

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    يستمع لإشعارات المستخدم ويبثها لحظياً عبر WebSocket
    """
    async def connect(self):
        user = self.scope.get("user")
        if user and user.is_authenticated:
            self.group_name = f"notifications_{user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_notification(self, event):
        """يُستدعى عندما يُبث إشعار جديد من الـ signal"""
        await self.send(text_data=json.dumps({
            "type": "notification",
            "count": event.get("count", 0),
            "title": event.get("title", ""),
            "body": event.get("body", ""),
            "url": event.get("url", ""),
        }))


class EscrowChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket لدردشة غرف Escrow
    """
    async def connect(self):
        self.deal_id = self.scope["url_route"]["kwargs"]["deal_id"]
        self.group_name = f"escrow_chat_{self.deal_id}"
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            await self.close()
            return

        # تحقق من صلاحيات الوصول
        has_access = await self._check_access(user, self.deal_id)
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """استقبال رسالة وبثها لجميع المتصلين بالغرفة"""
        data = json.loads(text_data)
        text = data.get("text", "").strip()
        if not text:
            return

        user = self.scope["user"]
        msg = await self._save_message(user, self.deal_id, text)
        if msg:
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat_message",
                "id": msg["id"],
                "text": msg["text"],
                "time": msg["time"],
                "avatar": msg["avatar"],
                "username": msg["username"],
                "is_admin": msg["is_admin"],
                "sender_id": msg["sender_id"],
            })

    async def chat_message(self, event):
        """إرسال الرسالة لجميع المتصلين"""
        user = self.scope["user"]
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "id": event["id"],
            "text": event["text"],
            "time": event["time"],
            "avatar": event["avatar"],
            "username": event["username"],
            "is_admin": event["is_admin"],
            "is_me": event["sender_id"] == user.id,
        }))

    @database_sync_to_async
    def _check_access(self, user, deal_id):
        from main.models import Deal
        try:
            deal = Deal.objects.get(id=deal_id)
            return (
                user == deal.buyer
                or user == deal.seller
                or user.is_superuser
                or has_any_admin_role(user, {"operations_admin", "finance_admin"})
            )
        except Deal.DoesNotExist:
            return False

    @database_sync_to_async
    def _save_message(self, user, deal_id, text):
        from main.models import Deal, EscrowRoom, EscrowMessage
        try:
            deal = Deal.objects.get(id=deal_id)
            room, _ = EscrowRoom.objects.get_or_create(deal=deal)
            msg = EscrowMessage.objects.create(
                room=room, sender=user, text=text,
                is_admin=user.is_superuser or has_any_admin_role(
                    user, {"operations_admin", "finance_admin"}
                )
            )
            return {
                "id": msg.id,
                "text": msg.text,
                "time": msg.created_at.strftime('%H:%M'),
                "avatar": safe_file_url(user.profile.avatar),
                "username": user.username,
                "is_admin": msg.is_admin,
                "sender_id": user.id,
            }
        except Deal.DoesNotExist:
            logger.warning("EscrowChat: attempted to save message for non-existent deal %s.", deal_id)
            return None
        except Exception:
            logger.exception("EscrowChat: failed to save message for deal %s by user %s.", deal_id, user.id)
            return None


class PrivateChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket للدردشة الخاصة بين الأصدقاء
    """
    async def connect(self):
        self.friend_id = self.scope["url_route"]["kwargs"]["friend_id"]
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            await self.close()
            return

        # اسم مجموعة ثابت بين المستخدمين (بترتيب IDs)
        ids = sorted([user.id, int(self.friend_id)])
        self.group_name = f"private_chat_{ids[0]}_{ids[1]}"

        has_access = await self._check_friendship(user, int(self.friend_id))
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        text = data.get("text", "").strip()
        if not text:
            return

        user = self.scope["user"]
        msg = await self._save_message(user, int(self.friend_id), text)
        if msg:
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat_message",
                "id": msg["id"],
                "text": msg["text"],
                "time": msg["time"],
                "avatar": msg["avatar"],
                "username": msg["username"],
                "verification_badge": msg["verification_badge"],
                "file_url": msg["file_url"],
                "sender_id": msg["sender_id"],
            })

    async def chat_message(self, event):
        user = self.scope["user"]
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "id": event["id"],
            "text": event["text"],
            "time": event["time"],
            "avatar": event["avatar"],
            "username": event["username"],
            "verification_badge": event["verification_badge"],
            "file_url": event["file_url"],
            "is_me": event["sender_id"] == user.id,
        }))

    @database_sync_to_async
    def _check_friendship(self, user, friend_id):
        from main.models import Friendship
        from django.db.models import Q
        return Friendship.objects.filter(
            (Q(from_user=user, to_user_id=friend_id) | Q(from_user_id=friend_id, to_user=user)),
            status='accepted'
        ).exists()

    @database_sync_to_async
    def _save_message(self, user, friend_id, text):
        from main.models import PrivateMessage
        try:
            friend = User.objects.get(id=friend_id)
            msg = PrivateMessage.objects.create(
                sender=user, receiver=friend, text=text
            )
            return {
                "id": msg.id,
                "text": msg.text,
                "time": msg.created_at.strftime('%H:%M'),
                "avatar": safe_file_url(user.profile.avatar),
                "username": user.username,
                "verification_badge": render_verification_badge(user.profile),
                "file_url": "",
                "sender_id": user.id,
            }
        except User.DoesNotExist:
            logger.warning("PrivateChat: attempted to message non-existent user %s.", friend_id)
            return None
        except Exception:
            logger.exception("PrivateChat: failed to save message from user %s to friend %s.", user.id, friend_id)
            return None
