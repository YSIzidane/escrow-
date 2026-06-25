from django.contrib.auth.models import User
from django.db import models


class AdminActionLog(models.Model):
    ACTION_CHOICES = [
        ("grant_staff", "Grant staff"),
        ("revoke_staff", "Revoke staff"),
        ("assign_role", "Assign role"),
        ("remove_role", "Remove role"),
        ("activate", "Activate account"),
        ("deactivate", "Deactivate account"),
    ]

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="admin_actions_performed",
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="admin_actions_received",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    role_key = models.CharField(max_length=64, blank=True)
    role_name = models.CharField(max_length=120, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        actor = self.actor.username if self.actor else "Unknown"
        target = self.target_user.username if self.target_user else "Unknown"
        return f"{self.action} by {actor} for {target}"
