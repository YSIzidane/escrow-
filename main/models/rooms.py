import random
import string
import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Room(models.Model):
    MAX_PARTICIPANTS = 2
    ROOM_TYPES = [
        ("buy", "شراء"),
        ("sell", "بيع"),
        ("trade", "تبادل"),
    ]

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_rooms",
    )
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES)
    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=8, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_code():
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choice(alphabet) for _ in range(8))
            if any(char.isalpha() for char in code):
                return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        else:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    @property
    def display_title(self):
        return self.title or f"Room {self.code}"

    def user_is_participant(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        return self.participants.filter(user=user).exists()

    def user_is_owner(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if self.creator_id == user.id:
            return True
        return self.participants.filter(user=user, role="owner").exists()

    def can_user_access(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if user.is_superuser:
            return True
        if user.is_staff:
            from main.services.admin_roles import has_any_admin_role

            return has_any_admin_role(user, {"support_admin", "security_admin"})
        return self.user_is_owner(user) or self.user_is_participant(user)

    def has_space_for_guest(self):
        return self.participants.count() < self.MAX_PARTICIPANTS

    def __str__(self):
        return self.display_title


class RoomParticipant(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("member", "Member"),
    ]

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="room_memberships",
    )
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="unique_room_participant"),
        ]
        ordering = ["joined_at", "id"]

    def __str__(self):
        return f"{self.user.username} in {self.room.code} ({self.role})"


class RoomMessage(models.Model):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"رسالة من {self.sender.username} في غرفة {self.room.code}"


class TradeExchange(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_WAITING = "waiting_partner"
    STATUS_READY = "ready_to_exchange"
    STATUS_RECEIVING = "receiving"
    STATUS_COMPLETED = "completed"
    STATUS_DISPUTED = "disputed"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_WAITING, "Waiting for partner"),
        (STATUS_READY, "Ready to exchange"),
        (STATUS_RECEIVING, "Receiving confirmations"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_DISPUTED, "Disputed"),
    ]

    room = models.OneToOneField(
        Room,
        on_delete=models.CASCADE,
        related_name="trade_exchange",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    owner_item_description = models.TextField(blank=True)
    member_item_description = models.TextField(blank=True)
    owner_ready_at = models.DateTimeField(null=True, blank=True)
    member_ready_at = models.DateTimeField(null=True, blank=True)
    owner_received_at = models.DateTimeField(null=True, blank=True)
    member_received_at = models.DateTimeField(null=True, blank=True)
    disputed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trade_disputes",
    )
    dispute_reason = models.TextField(blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def participant_key_for(self, user):
        if not getattr(user, "is_authenticated", False):
            return ""
        if self.room.creator_id == user.id or self.room.participants.filter(user=user, role="owner").exists():
            return "owner"
        if self.room.participants.filter(user=user, role="member").exists():
            return "member"
        return ""

    def set_item_for(self, key, description):
        if key == "owner":
            self.owner_item_description = description
            self.owner_ready_at = None
            self.owner_received_at = None
        elif key == "member":
            self.member_item_description = description
            self.member_ready_at = None
            self.member_received_at = None
        self.refresh_status()

    def mark_ready_for(self, key):
        now = timezone.now()
        if key == "owner" and self.owner_item_description.strip():
            self.owner_ready_at = now
        elif key == "member" and self.member_item_description.strip():
            self.member_ready_at = now
        self.refresh_status()

    def confirm_received_for(self, key):
        now = timezone.now()
        if key == "owner":
            self.owner_received_at = now
        elif key == "member":
            self.member_received_at = now
        self.refresh_status()

    def open_dispute(self, user, reason):
        self.disputed_by = user
        self.dispute_reason = reason
        self.disputed_at = timezone.now()
        self.status = self.STATUS_DISPUTED

    def refresh_status(self):
        if self.status == self.STATUS_DISPUTED:
            return

        owner_ready = bool(self.owner_ready_at)
        member_ready = bool(self.member_ready_at)
        owner_received = bool(self.owner_received_at)
        member_received = bool(self.member_received_at)

        if owner_received and member_received:
            self.status = self.STATUS_COMPLETED
            if not self.completed_at:
                self.completed_at = timezone.now()
            if self.room.is_active:
                self.room.is_active = False
                self.room.closed_at = self.completed_at
                self.room.save(update_fields=["is_active", "closed_at"])
        elif owner_received or member_received:
            self.status = self.STATUS_RECEIVING
        elif owner_ready and member_ready:
            self.status = self.STATUS_READY
        elif owner_ready or member_ready:
            self.status = self.STATUS_WAITING
        else:
            self.status = self.STATUS_DRAFT

    @property
    def both_items_described(self):
        return bool(self.owner_item_description.strip() and self.member_item_description.strip())

    @property
    def both_ready(self):
        return bool(self.owner_ready_at and self.member_ready_at)

    @property
    def both_received(self):
        return bool(self.owner_received_at and self.member_received_at)

    def __str__(self):
        return f"Trade exchange for {self.room.code} ({self.status})"
