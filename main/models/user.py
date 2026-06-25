import os
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from main.utils import compress_image
from ..validators import (
    validate_kyc_file as shared_validate_kyc_file,
    validate_public_attachment,
)


def validate_kyc_file(value):
    shared_validate_kyc_file(value)


def kyc_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"kyc_docs/{uuid.uuid4().hex}{ext}"


class Profile(models.Model):
    VERIFICATION_TIER_CHOICES = [
        ("standard", "Standard"),
        ("gold", "Gold"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", default="avatars/default.jpg")
    phone = models.CharField(max_length=20, blank=True)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="الرصيد المتاح للسحب في محفظة البائع",
    )
    is_verified = models.BooleanField(default=False)
    verification_tier = models.CharField(
        max_length=20,
        choices=VERIFICATION_TIER_CHOICES,
        default="standard",
    )
    kyc_document = models.FileField(
        upload_to=kyc_upload_path,
        blank=True,
        null=True,
        validators=[validate_kyc_file],
        help_text="مستند التوثيق (صورة أو PDF)",
    )
    kyc_status = models.CharField(
        max_length=20,
        choices=[
            ("unsubmitted", "غير مرسل"),
            ("pending", "قيد المراجعة"),
            ("approved", "مقبول"),
            ("rejected", "مرفوض"),
        ],
        default="unsubmitted",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.avatar and not self.avatar.name.startswith("avatars/default"):
            if self.pk:
                try:
                    old_profile = Profile.objects.get(pk=self.pk)
                    if old_profile.avatar != self.avatar:
                        self.avatar = compress_image(self.avatar, max_width=400, max_height=400, quality=80)
                except Profile.DoesNotExist:
                    self.avatar = compress_image(self.avatar, max_width=400, max_height=400, quality=80)
            else:
                self.avatar = compress_image(self.avatar, max_width=400, max_height=400, quality=80)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username

    @property
    def is_kyc_approved(self):
        return self.kyc_status == "approved"

    @property
    def can_withdraw(self):
        return self.is_verified and self.is_kyc_approved

    @property
    def is_gold_verified(self):
        return self.is_verified and self.verification_tier == "gold"


class Friendship(models.Model):
    STATUS_CHOICES = [
        ("pending", "معلق"),
        ("accepted", "مقبول"),
        ("rejected", "مرفوض"),
    ]

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_sent")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_received")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("from_user", "to_user")

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.status})"


class PrivateMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    text = models.TextField()
    file = models.FileField(
        upload_to="private_files/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sender} -> {self.receiver}"


class WithdrawalRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=[
            ("paypal", "PayPal"),
            ("bank", "التحويل البنكي"),
            ("crypto", "عملات رقمية (USDT)"),
        ],
    )
    details = models.TextField(
        help_text="تفاصيل الحساب المستلم (إيميل PayPal، رقم الحساب البنكي، أو عنوان المحفظة)"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "قيد المعالجة"),
            ("processed", "تم التحويل"),
            ("rejected", "مرفوض"),
        ],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_withdrawals",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Withdrawal amount must be greater than zero."})
        if self.user_id:
            profile = getattr(self.user, "profile", None)
            if not profile or not profile.can_withdraw:
                raise ValidationError({"user": "Account verification is required before creating a withdrawal request."})
            has_pending_request = WithdrawalRequest.objects.filter(
                user_id=self.user_id,
                status="pending",
            ).exclude(pk=self.pk).exists()
            if has_pending_request:
                raise ValidationError({"status": "You already have a pending withdrawal request."})
        if self.status == "processed" and not self.payout_reference.strip():
            raise ValidationError({"payout_reference": "Payout reference is required before marking this withdrawal as processed."})
        if self.status == "rejected" and not self.rejection_reason.strip():
            raise ValidationError({"rejection_reason": "Rejection reason is required before rejecting this withdrawal."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Withdrawal {self.amount}$ from {self.user.username} ({self.get_status_display()})"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
