import os
import uuid

from django.db import models

from ..validators import validate_ccp_proof_file as shared_validate_ccp_proof_file


def validate_ccp_proof_file(value):
    shared_validate_ccp_proof_file(value)


def ccp_proof_upload_path(instance, filename):
    ext = filename.split(".")[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    return f"ccp_proofs/{filename}"


class SiteSettings(models.Model):
    ccp_name = models.CharField(max_length=255, default="اسم الحساب", verbose_name="اسم حساب CCP")
    ccp_account = models.CharField(max_length=50, default="0000000000", verbose_name="رقم حساب CCP")
    ccp_rip = models.CharField(max_length=50, default="00799999000000000000", verbose_name="RIP")
    baridimob_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم الهاتف (BaridiMob)")

    class Meta:
        verbose_name = "إعدادات الموقع"
        verbose_name_plural = "إعدادات الموقع"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "إعدادات منصة Escrow"
