import hashlib
import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from main.utils import compress_image
from ..validators import validate_public_attachment


class Deal(models.Model):
    STATUS_CHOICES = [
        ("new", "جديدة"),
        ("expired", "منتهية"),
        ("reserved", "محجوزة"),
        ("shipped", "قيد الشحن"),
        ("delivered", "تم الاستلام"),
        ("completed", "مكتملة"),
        ("disputed", "نزاع"),
        ("cancelled", "ملغاة"),
    ]

    CATEGORY_CHOICES = [
        ("games", "ألعاب"),
        ("accounts", "حسابات"),
        ("services", "خدمات"),
        ("electronics", "إلكترونيات"),
        ("digital", "منتجات رقمية"),
        ("physical", "منتجات مادية"),
        ("other", "أخرى"),
    ]

    DELIVERY_CHOICES = [
        ("shipping", "شحن"),
        ("digital", "تسليم رقمي"),
        ("service", "تنفيذ خدمة"),
        ("in_person", "تسليم يدوي"),
    ]

    # Category & Delivery
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other", help_text="تصنيف الصفقة")
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="shipping", help_text="طريقة التسليم")
    platform = models.CharField(max_length=100, blank=True, help_text="المنصة (اختياري — للحسابات والألعاب)")
    delivery_time = models.PositiveIntegerField(null=True, blank=True, help_text="مدة التسليم بالأيام (اختياري — للخدمات)")

    is_auction = models.BooleanField(default=False, help_text="هل هذه صفقة مزايدة؟")
    starting_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    auction_ends_at = models.DateTimeField(null=True, blank=True, help_text="تاريخ انتهاء المزايدة")
    min_bid_increment = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("5.00"), help_text="الحد الأدنى لزيادة العرض")

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="seller_deals")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="buyer_deals", null=True, blank=True)

    product_title = models.CharField(max_length=200)
    product_description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

    buyer_approved = models.BooleanField(default=False)
    seller_shipped = models.BooleanField(default=False)
    buyer_confirmed = models.BooleanField(default=False)
    seller_confirmed = models.BooleanField(default=False)

    shipping_proof = models.FileField(
        upload_to="shipping_proofs/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    tracking_number = models.CharField(max_length=100, blank=True)

    dispute_reason = models.TextField(blank=True)
    dispute_evidence = models.FileField(
        upload_to="dispute_evidence/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    dispute_resolved = models.BooleanField(default=False)
    dispute_resolution = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        errors = {}

        if self.is_auction:
            if not self.starting_price or self.starting_price <= 0:
                errors["starting_price"] = "صفقة المزايدة تتطلب سعر ابتدائي أكبر من صفر."
            if not self.auction_ends_at:
                errors["auction_ends_at"] = "صفقة المزايدة تتطلب تاريخ انتهاء."
        else:
            if not self.price or self.price <= 0:
                errors["price"] = "الصفقة ذات السعر الثابت تتطلب سعراً أكبر من صفر."

        if self.buyer and self.seller and self.buyer == self.seller:
            errors["buyer"] = "لا يمكن أن يكون البائع والمشتري نفس الشخص."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"صفقة #{self.id} - {self.product_title}"


class DealMessage(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    file = models.FileField(
        upload_to="deal_files/",
        null=True,
        blank=True,
        validators=[validate_public_attachment],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"رسالة من {self.sender.username} في صفقة #{self.deal.id}"


class DealFile(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="deals/", validators=[validate_public_attachment])
    uploader = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ملف في صفقة #{self.deal.id}"


class DealEvidence(models.Model):
    """Immutable evidence artifact attached to a deal timeline."""

    TYPE_DELIVERY = "delivery"
    TYPE_DISPUTE = "dispute"
    TYPE_ADMIN = "admin"

    EVIDENCE_TYPES = [
        (TYPE_DELIVERY, "Delivery proof"),
        (TYPE_DISPUTE, "Dispute evidence"),
        (TYPE_ADMIN, "Admin evidence"),
    ]
    IMMUTABLE_FIELDS = (
        "deal_id",
        "uploader_id",
        "evidence_type",
        "file",
        "original_name",
        "file_size",
        "content_type",
        "sha256_hash",
        "metadata",
    )

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="evidence_items")
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="deal_evidence")
    evidence_type = models.CharField(max_length=32, choices=EVIDENCE_TYPES)
    file = models.FileField(upload_to="deal_evidence/", validators=[validate_public_attachment])
    original_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)
    sha256_hash = models.CharField(max_length=64, db_index=True, editable=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_deal_evidence",
    )
    archive_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["deal", "-created_at"]),
            models.Index(fields=["evidence_type", "-created_at"]),
            models.Index(fields=["sha256_hash"]),
        ]

    @property
    def short_hash(self):
        return self.sha256_hash[:12]

    def _calculate_file_hash(self):
        digest = hashlib.sha256()
        file_obj = self.file
        position = None
        try:
            position = file_obj.tell()
        except Exception:
            position = None

        for chunk in file_obj.chunks():
            digest.update(chunk)

        if position is not None:
            try:
                file_obj.seek(position)
            except Exception:
                pass
        return digest.hexdigest()

    def clean(self):
        super().clean()
        if not self.pk:
            return

        old = type(self).objects.get(pk=self.pk)
        changed_fields = [
            field
            for field in self.IMMUTABLE_FIELDS
            if getattr(old, field) != getattr(self, field)
        ]
        if changed_fields:
            raise ValidationError("Evidence artifacts are immutable. Archive the artifact instead of editing it.")

    def save(self, *args, **kwargs):
        if self.file:
            if not self.original_name:
                self.original_name = os.path.basename(self.file.name)
            if not self.file_size:
                self.file_size = int(getattr(self.file, "size", 0) or 0)
            if not self.content_type:
                self.content_type = (
                    getattr(self.file, "content_type", "")
                    or getattr(getattr(self.file, "file", None), "content_type", "")
                )
            if not self.sha256_hash:
                self.sha256_hash = self._calculate_file_hash()

        self.full_clean()
        super().save(*args, **kwargs)

    def archive(self, *, by=None, reason=""):
        from django.utils import timezone

        self.archived_at = timezone.now()
        self.archived_by = by
        self.archive_reason = reason
        self.save(update_fields=["archived_at", "archived_by", "archive_reason"])

    def __str__(self):
        return f"{self.evidence_type} evidence for deal #{self.deal_id}"


class DealImage(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="deal_images/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def save(self, *args, **kwargs):
        if self.image:
            if self.pk:
                try:
                    old_img = DealImage.objects.get(pk=self.pk)
                    if old_img.image != self.image:
                        self.image = compress_image(self.image, max_width=800, max_height=800, quality=80)
                except DealImage.DoesNotExist:
                    self.image = compress_image(self.image, max_width=800, max_height=800, quality=80)
            else:
                self.image = compress_image(self.image, max_width=800, max_height=800, quality=80)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"صورة لصفقة #{self.deal.id}"


class DealComment(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deal_comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"تعليق من {self.author.username} على صفقة #{self.deal.id}"

    @property
    def is_reply(self):
        return self.parent is not None


class DealEvent(models.Model):
    """Immutable business timeline event emitted by the deal engine."""

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="deal_events")
    event_type = models.CharField(max_length=80)
    from_state = models.CharField(max_length=32, blank=True)
    to_state = models.CharField(max_length=32, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["deal", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]

    def __str__(self):
        actor = self.actor.username if self.actor else "system"
        return f"{self.event_type} on deal #{self.deal_id} by {actor}"


class DealTransitionLog(models.Model):
    """Security log for every deal engine transition attempt."""

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="transition_logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="deal_transition_logs")
    command = models.CharField(max_length=80)
    from_state = models.CharField(max_length=32, blank=True)
    to_state = models.CharField(max_length=32, blank=True)
    allowed = models.BooleanField(default=False)
    reason = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["deal", "-created_at"]),
            models.Index(fields=["command", "allowed"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        verdict = "allowed" if self.allowed else "blocked"
        return f"{self.command} {verdict} on deal #{self.deal_id}"


class DealDeadline(models.Model):
    """Persistent SLA/deadline record produced by deal state transitions."""

    TYPE_PAYMENT = "payment"
    TYPE_DELIVERY = "delivery"
    TYPE_RECEIPT = "receipt"
    TYPE_DISPUTE_RESPONSE = "dispute_response"

    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"

    DEADLINE_TYPES = [
        (TYPE_PAYMENT, "Payment"),
        (TYPE_DELIVERY, "Delivery"),
        (TYPE_RECEIPT, "Receipt confirmation"),
        (TYPE_DISPUTE_RESPONSE, "Dispute response"),
    ]
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="deadlines")
    deadline_type = models.CharField(max_length=32, choices=DEADLINE_TYPES)
    actor_role = models.CharField(max_length=32)
    state = models.CharField(max_length=32)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    source_event = models.ForeignKey(DealEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name="deadlines")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at", "id"]
        indexes = [
            models.Index(fields=["deal", "status", "due_at"]),
            models.Index(fields=["deadline_type", "status", "due_at"]),
        ]

    def complete(self, status=STATUS_COMPLETED):
        from django.utils import timezone

        self.status = status
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def __str__(self):
        return f"{self.deadline_type} deadline for deal #{self.deal_id}"


class Bid(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="bids")
    bidder = models.ForeignKey(User, on_delete=models.CASCADE, related_name="my_bids")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True, help_text="رسالة اختيارية مع العرض")
    is_accepted = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-amount", "-created_at"]

    def clean(self):
        super().clean()
        errors = {}

        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "مبلغ العرض يجب أن يكون أكبر من صفر."

        if self.is_accepted and self.is_rejected:
            errors["is_rejected"] = "لا يمكن أن يكون العرض مقبولاً ومرفوضاً في نفس الوقت."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"عرض {self.amount} $ من {self.bidder.username} على صفقة #{self.deal.id}"


class Review(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    rated_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_reviews")
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"تقييم {self.rating} نجوم من {self.reviewer.username}"
