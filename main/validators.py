import os
from dataclasses import dataclass

from django.core.exceptions import ValidationError


MB = 1024 * 1024
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DOCUMENT_EXTENSIONS = (".pdf",)


@dataclass(frozen=True)
class UploadPolicy:
    label: str
    allowed_extensions: tuple[str, ...]
    max_size_bytes: int
    allowed_display: str


PUBLIC_ATTACHMENT_POLICY = UploadPolicy(
    label="file",
    allowed_extensions=IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS,
    max_size_bytes=5 * MB,
    allowed_display="JPG, JPEG, PNG, WEBP, PDF",
)

CCP_PROOF_POLICY = UploadPolicy(
    label="payment proof",
    allowed_extensions=IMAGE_EXTENSIONS,
    max_size_bytes=5 * MB,
    allowed_display="JPG, JPEG, PNG, WEBP",
)

KYC_POLICY = UploadPolicy(
    label="KYC document",
    allowed_extensions=IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS,
    max_size_bytes=5 * MB,
    allowed_display="JPG, JPEG, PNG, WEBP, PDF",
)


def _validate_uploaded_file(value, policy: UploadPolicy):
    if not value or not getattr(value, "name", ""):
        return

    ext = os.path.splitext(value.name)[1].lower()
    if ext not in policy.allowed_extensions:
        raise ValidationError(
            f"Unsupported {policy.label} type ({ext or 'unknown'}). Allowed types: {policy.allowed_display}."
        )

    if getattr(value, "size", 0) > policy.max_size_bytes:
        max_size_mb = policy.max_size_bytes // MB
        raise ValidationError(
            f"The {policy.label} is too large. Maximum size is {max_size_mb} MB."
        )


def validate_public_attachment(value):
    _validate_uploaded_file(value, PUBLIC_ATTACHMENT_POLICY)


def validate_ccp_proof_file(value):
    _validate_uploaded_file(value, CCP_PROOF_POLICY)


def validate_kyc_file(value):
    _validate_uploaded_file(value, KYC_POLICY)
