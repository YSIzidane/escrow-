from django.db import models
from django.contrib.auth.models import User
from .deals import Deal


class EscrowRoom(models.Model):
    deal = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name='escrow_room')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"غرفة Escrow — صفقة #{self.deal.id}"


class EscrowMessage(models.Model):
    room = models.ForeignKey(EscrowRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"رسالة من {self.sender.username} في غرفة صفقة #{self.room.deal.id}"
