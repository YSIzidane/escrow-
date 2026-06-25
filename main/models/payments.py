from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .deals import Deal
from .settings import ccp_proof_upload_path, validate_ccp_proof_file


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "في الانتظار"),
        ("pending_manual_verification", "بانتظار المراجعة اليدوية"),
        ("escrow_held", "محجوز في الضمان"),
        ("released", "محرر للبائع"),
        ("refunded", "مسترجع للمشتري"),
        ("failed", "فشل"),
        ("failed_max_retries", "مرفوض نهائيًا (تجاوز المحاولات)"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("stripe", "Stripe (بطاقة ائتمانية)"),
        ("ccp", "بريد الجزائر (CCP / BaridiMob)"),
    ]

    deal = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="payment")
    payer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="عمولة المنصة")
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="المبلغ الصافي للبائع")
    transaction_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="pending")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="stripe")

    proof_file = models.FileField(
        upload_to=ccp_proof_upload_path,
        validators=[validate_ccp_proof_file],
        blank=True,
        null=True,
    )
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    transfer_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    rejection_count = models.IntegerField(default=0)
    rejection_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    held_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.status == "escrow_held" and not self.held_at:
            self.held_at = timezone.now()
        if self.status == "released" and not self.released_at:
            self.released_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def is_held(self):
        return self.status == "escrow_held"

    @property
    def is_released(self):
        return self.status == "released"

    def __str__(self):
        return f"دفع ${self.amount} لصفقة #{self.deal.id} - {self.get_status_display()}"


class TransactionInvoice(models.Model):
    STATUS_CHOICES = [
        ("issued", "Issued"),
        ("refunded", "Refunded"),
    ]

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="invoice")
    deal = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="invoice")
    invoice_number = models.CharField(max_length=32, unique=True, blank=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchase_invoices")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sales_invoices")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    seller_net = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=8, default="USD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="issued")
    issued_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-issued_at", "-id")

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            stamp = timezone.now().strftime("%Y%m%d")
            self.invoice_number = f"INV-{stamp}-{self.deal_id:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - Deal #{self.deal_id}"


class PaymentAuditLog(models.Model):
    """Audit trail for sensitive payment review and money movement actions."""

    ACTION_CHOICES = [
        ("approved", "Approved payment"),
        ("rejected", "Rejected payment"),
        ("released", "Released funds"),
        ("refunded", "Refunded payment"),
    ]

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="audit_logs")
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        actor = self.admin.username if self.admin else "Unknown"
        return f"{self.get_action_display()} for payment {self.payment.id} by {actor}"
