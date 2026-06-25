from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):
    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"

    TYPE_CHOICES = [
        ("payment", "Payment"),
        ("shipped", "Shipping"),
        ("delivered", "Delivered"),
        ("dispute", "Dispute"),
        ("bid_won", "Bid won"),
        ("message", "Message"),
        ("ticket", "Ticket"),
        ("withdrawal", "Withdrawal"),
    ]
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_CRITICAL, "Critical"),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    deal = models.ForeignKey(
        "Deal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    notif_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    action = models.CharField(max_length=80, blank=True)
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    channel = models.CharField(max_length=20, default="in_app")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["deal", "priority", "-created_at"]),
            models.Index(fields=["action", "priority"]),
        ]

    def __str__(self):
        return f"Notification for {self.recipient.username} - {self.notif_type}"
