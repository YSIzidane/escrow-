from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/escrow/(?P<deal_id>\d+)/$', consumers.EscrowChatConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<friend_id>\d+)/$', consumers.PrivateChatConsumer.as_asgi()),
]
