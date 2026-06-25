from django.contrib.auth.models import User
from django.db import models

from ..validators import validate_public_attachment
from .deals import Deal


class SupportTicket(models.Model):
    PRIORITY_CHOICES = [
        ("low", "منخفض"),
        ("medium", "متوسط"),
        ("high", "عالي"),
        ("urgent", "عاجل"),
    ]
    STATUS_CHOICES = [
        ("open", "مفتوحة"),
        ("in_progress", "قيد المعالجة"),
        ("resolved", "محلولة"),
        ("closed", "مغلقة"),
    ]
    CATEGORY_CHOICES = [
        ("payment", "مشكلة دفع"),
        ("deal", "مشكلة صفقة"),
        ("account", "مشكلة حساب"),
        ("technical", "مشكلة تقنية"),
        ("other", "أخرى"),
    ]

    ticket_number = models.CharField(max_length=20, unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    deal = models.ForeignKey(Deal, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    subject = models.CharField(max_length=200)
    description = models.TextField()
    attachment = models.FileField(
        upload_to="tickets/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            import secrets

            for _ in range(10):
                candidate = f"TKT-{secrets.randbelow(900000) + 100000}"
                if not SupportTicket.objects.filter(ticket_number=candidate).exists():
                    self.ticket_number = candidate
                    break
            else:
                raise ValueError("Could not generate a unique ticket number.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.ticket_number}] {self.subject}"


class TicketReply(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="replies")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    attachment = models.FileField(
        upload_to="ticket_replies/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    is_staff_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"رد على {self.ticket.ticket_number}"
