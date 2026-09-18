# ==================== Payment Views ====================
import logging
import uuid
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction

from ..models import (
    Deal,
    EscrowMessage,
    EscrowRoom,
    Payment,
    PaymentAuditLog,
    Profile,
    SiteSettings,
    StripeEvent,
    TransactionInvoice,
)
from ..deal_engine import DealEngineError, execute as execute_deal_command
from ..services.admin_roles import has_role_or_legacy_staff
from ..utils import model_table_exists
from ..validators import validate_ccp_proof_file
from .notifications import create_notification
from ..services.payment_service import process_successful_payment

logger = logging.getLogger(__name__)

# Configure Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY


def _stripe_is_configured():
    return bool(
        settings.STRIPE_SECRET_KEY
        and settings.STRIPE_SECRET_KEY != "sk_test_..."
    )


def _build_absolute_url(request, path):
    base_url = getattr(settings, "SITE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    return request.build_absolute_uri(path)


def _reject_self_purchase(request, deal):
    if request.user == deal.seller:
        messages.error(request, "لا يمكنك شراء صفقتك الخاصة.")
        return redirect("deal_detail", deal_id=deal.id)
    return None


def _resolve_refundable_reference(reference):
    if not reference:
        return None
    if reference.startswith("pi_"):
        return {"payment_intent": reference}
    if reference.startswith("ch_"):
        return {"charge": reference}
    if reference.startswith("cs_"):
        session = stripe.checkout.Session.retrieve(reference)
        payment_intent = session.get("payment_intent")
        if payment_intent:
            return {"payment_intent": payment_intent}
    return None


class PaymentStateError(Exception):
    """Raised when a payment action is not allowed in the current state."""


FINAL_PAYMENT_STATUSES = {"escrow_held", "released", "refunded"}


def payment_is_escrow_held(payment):
    return bool(payment and payment.status == "escrow_held")


def get_locked_payment_for_deal(deal):
    return Payment.objects.select_for_update().filter(deal=deal).first()


def clear_unheld_payment_reservation(locked_deal, locked_payment):
    """
    Clear legacy/pre-approval reservation data for payments that are not funded.

    A pending Stripe checkout or CCP proof must never reserve a deal. Only a
    verified payment moving to escrow_held may assign the buyer and reserve it.
    """
    if not locked_payment or locked_payment.status in {"escrow_held", "released"}:
        return False
    if locked_deal.buyer_id != locked_payment.payer_id:
        return False

    locked_deal.buyer = None
    locked_deal.buyer_approved = False
    locked_deal.buyer_confirmed = False
    locked_deal.seller_confirmed = False
    locked_deal.seller_shipped = False
    locked_deal.tracking_number = ""
    locked_deal.shipping_proof = None
    if locked_deal.status in {"reserved", "shipped", "delivered"}:
        locked_deal.status = "new"
    locked_deal.save()
    return True


def _record_payment_audit(payment, *, action, actor=None, reason=""):
    PaymentAuditLog.objects.create(
        payment=payment,
        admin=actor if getattr(actor, "is_staff", False) else None,
        action=action,
        reason=reason or None,
    )


def _resolve_platform_owner_profile():
    owner_username = getattr(settings, "PLATFORM_OWNER_USERNAME", "").strip()
    owner_qs = User.objects.select_related("profile")
    if owner_username:
        configured_owner = owner_qs.filter(username=owner_username, is_superuser=True).first()
        if configured_owner:
            return configured_owner
    return owner_qs.filter(is_superuser=True).order_by("id").first()


def _fee_rate_percent():
    return int(Decimal(str(getattr(settings, "ESCROW_FEE_PERCENTAGE", 0.05))) * 100)


def _sync_invoice_for_payment(payment):
    if not model_table_exists(TransactionInvoice):
        return None

    deal = payment.deal
    buyer = deal.buyer or payment.payer
    if not buyer:
        return None

    invoice, _ = TransactionInvoice.objects.update_or_create(
        payment=payment,
        defaults={
            "deal": deal,
            "buyer": buyer,
            "seller": deal.seller,
            "subtotal": payment.amount,
            "platform_fee": payment.fee_amount,
            "seller_net": payment.net_amount,
            "currency": getattr(settings, "STRIPE_CURRENCY", "usd").upper(),
            "status": "refunded" if payment.status == "refunded" else "issued",
        },
    )
    return invoice


def release_payment_for_deal(deal, *, buyer_confirmed=None, audit_admin=None, audit_reason=""):
    """Release escrow funds through one consistent business path."""
    with transaction.atomic():
        locked_deal = Deal.objects.select_for_update().get(id=deal.id)
        payment = getattr(locked_deal, "payment", None)
        if not payment:
            raise PaymentStateError("no_payment")

        locked_payment = Payment.objects.select_for_update().get(id=payment.id)
        if locked_payment.status != "escrow_held":
            raise PaymentStateError("not_held")

        fee_percentage = getattr(settings, "ESCROW_FEE_PERCENTAGE", 0.05)
        fee_amount = locked_payment.amount * Decimal(str(fee_percentage))
        net_amount = locked_payment.amount - fee_amount

        try:
            execute_deal_command(
                "complete",
                deal=locked_deal,
                actor=audit_admin,
                metadata={
                    "source": "release_payment_for_deal",
                    "payment_id": locked_payment.id,
                    "amount": str(locked_payment.amount),
                    "fee_amount": str(fee_amount),
                    "net_amount": str(net_amount),
                },
                raise_on_error=True,
            )
        except DealEngineError as exc:
            raise PaymentStateError(exc.reason) from exc

        locked_payment.status = "released"
        locked_payment.fee_amount = fee_amount
        locked_payment.net_amount = net_amount
        locked_payment.save()

        seller_profile = Profile.objects.select_for_update().get(user=locked_deal.seller)
        seller_profile.balance += net_amount
        owner_user = _resolve_platform_owner_profile()
        if owner_user and fee_amount > 0:
            owner_profile = Profile.objects.select_for_update().get(user=owner_user)
            if owner_profile.user_id == seller_profile.user_id:
                seller_profile.balance += fee_amount
                seller_profile.save()
            else:
                seller_profile.save()
                owner_profile.balance += fee_amount
                owner_profile.save()
        else:
            seller_profile.save()

        if buyer_confirmed is not None:
            locked_deal.buyer_confirmed = buyer_confirmed
            locked_deal.save(update_fields=["buyer_confirmed", "updated_at"])

        invoice = _sync_invoice_for_payment(locked_payment)
        if audit_admin is not None:
            _record_payment_audit(
                locked_payment,
                action="released",
                actor=audit_admin,
                reason=audit_reason,
            )

    create_notification(
        recipient=locked_deal.seller,
        notif_type="payment",
        title=f"🎉 تم استلام الأرباح — {locked_deal.product_title}",
        body=f"تم تحرير الصفقة وإضافة ${net_amount} إلى محفظتك (رسوم المنصة: ${fee_amount}).",
        url="/profile/",
    )

    if invoice:
        create_notification(
            recipient=invoice.buyer,
            notif_type="payment",
            title=f"Invoice ready - {invoice.invoice_number}",
            body=f"Your invoice for deal #{locked_deal.id} is now available in your account.",
            url=f"/invoices/{invoice.id}/",
        )

    return locked_payment, net_amount, fee_amount, locked_deal


def refund_payment_for_deal(deal, *, audit_admin=None, audit_reason=""):
    """Refund via Stripe when available, then reset the local deal state."""
    with transaction.atomic():
        locked_deal = Deal.objects.select_for_update().get(id=deal.id)
        payment = getattr(locked_deal, "payment", None)
        if not payment:
            raise PaymentStateError("no_payment")

        locked_payment = Payment.objects.select_for_update().get(id=payment.id)
        if locked_payment.status not in ("escrow_held", "pending"):
            raise PaymentStateError("not_refundable")

        if locked_payment.payment_method == "stripe":
            if not _stripe_is_configured():
                logger.error(
                    "Refund blocked for Stripe payment on deal %s because Stripe is not configured.",
                    locked_deal.id,
                )
                raise PaymentStateError("stripe_not_configured")
            if not locked_payment.transaction_id:
                logger.error(
                    "Refund blocked for Stripe payment on deal %s because no transaction reference exists.",
                    locked_deal.id,
                )
                raise PaymentStateError("missing_reference")

            refund_target = _resolve_refundable_reference(locked_payment.transaction_id)
            if not refund_target:
                logger.error(
                    "Refund blocked for deal %s because transaction %s could not be mapped.",
                    locked_deal.id,
                    locked_payment.transaction_id,
                )
                raise PaymentStateError("unmappable_reference")

            stripe.Refund.create(
                reason="requested_by_customer",
                metadata={"deal_id": str(locked_deal.id)},
                **refund_target,
            )
        elif locked_payment.payment_method != "ccp":
            logger.error(
                "Refund blocked for deal %s because payment method %s is unsupported.",
                locked_deal.id,
                locked_payment.payment_method,
            )
            raise PaymentStateError("unsupported_payment_method")

        try:
            execute_deal_command(
                "refund",
                deal=locked_deal,
                actor=audit_admin,
                metadata={
                    "source": "refund_payment_for_deal",
                    "payment_id": locked_payment.id,
                    "amount": str(locked_payment.amount),
                },
                save=False,
                raise_on_error=True,
            )
        except DealEngineError as exc:
            raise PaymentStateError(exc.reason) from exc

        locked_payment.status = "refunded"
        locked_payment.save()

        locked_deal.status = "new"
        locked_deal.buyer = None
        locked_deal.buyer_approved = False
        locked_deal.buyer_confirmed = False
        locked_deal.seller_confirmed = False
        locked_deal.seller_shipped = False
        locked_deal.tracking_number = ""
        locked_deal.shipping_proof = None
        if locked_deal.is_auction:
            locked_deal.price = locked_deal.starting_price
            locked_deal.bids.update(is_accepted=False, is_rejected=False)
        locked_deal.save()

        _sync_invoice_for_payment(locked_payment)
        if audit_admin is not None:
            _record_payment_audit(
                locked_payment,
                action="refunded",
                actor=audit_admin,
                reason=audit_reason,
            )

    return locked_payment, locked_deal


@login_required(login_url="login")
def create_payment(request, deal_id):
    """صفحة الدفع قبل إنشاء جلسة Stripe."""
    deal = get_object_or_404(Deal, id=deal_id)
    self_purchase_response = _reject_self_purchase(request, deal)
    if self_purchase_response:
        return self_purchase_response
    if deal.buyer and request.user != deal.buyer:
        messages.error(request, "ليس لديك صلاحية الدفع لهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)
    if hasattr(deal, "payment") and deal.payment.status in ("escrow_held", "released"):
        messages.info(request, "تم الدفع بالفعل لهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)

    existing_payment = getattr(deal, "payment", None)
    if (
        existing_payment
        and existing_payment.status == "pending_manual_verification"
        and existing_payment.payer_id != request.user.id
    ):
        messages.warning(request, "توجد مراجعة دفع يدوية معلقة لهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)

    payment, created = Payment.objects.get_or_create(
        deal=deal,
        defaults={
            "payer": request.user,
            "amount": deal.price,
            "status": "pending",
            "transaction_id": f"ESC-{uuid.uuid4().hex[:12].upper()}",
        },
    )
    if not created:
        update_fields = []
        if payment.payer_id != request.user.id:
            payment.payer = request.user
            update_fields.append("payer")
        if payment.amount != deal.price:
            payment.amount = deal.price
            update_fields.append("amount")
        if not payment.transaction_id:
            payment.transaction_id = (
                f"CCP-{uuid.uuid4().hex[:12].upper()}"
                if payment.payment_method == "ccp"
                else f"ESC-{uuid.uuid4().hex[:12].upper()}"
            )
            update_fields.append("transaction_id")
        if update_fields:
            payment.save(update_fields=update_fields)
    # Load CCP settings for the template
    site_settings = SiteSettings.load()
    # Generate a unique transfer code for CCP
    if not payment.transfer_code:
        payment.transfer_code = f"ESCROW-{deal.id}-{uuid.uuid4().hex[:4].upper()}"
        payment.save(update_fields=["transfer_code"])
    ccp_status_summary = None
    current_language = getattr(request, "LANGUAGE_CODE", "ar")
    if payment.payment_method == "ccp":
        if payment.status == "pending_manual_verification":
            ccp_status_summary = {
                "tone": "pending",
                "title": "إثبات الدفع قيد المراجعة" if current_language == "ar" else "Your proof is under review",
                "body": (
                    "تم استلام إثبات التحويل الخاص بك، ولا يمكنك رفع إثبات جديد حتى تنتهي المراجعة الحالية."
                    if current_language == "ar"
                    else "Your transfer proof has been received. You cannot upload a new proof until the current review is completed."
                ),
            }
        elif payment.status == "pending" and payment.rejection_count > 0:
            remaining_attempts = max(0, 3 - payment.rejection_count)
            ccp_status_summary = {
                "tone": "warning",
                "title": "المراجعة السابقة رُفضت" if current_language == "ar" else "Your previous review was rejected",
                "body": (
                    f"سبب الرفض الأخير: {payment.rejection_reason}. يمكنك رفع إثبات جديد. المحاولات المتبقية: {remaining_attempts}."
                    if current_language == "ar"
                    else f"Last rejection reason: {payment.rejection_reason}. You can upload a new proof now. Remaining attempts: {remaining_attempts}."
                ),
            }
        elif payment.status == "failed_max_retries":
            ccp_status_summary = {
                "tone": "danger",
                "title": "تم إيقاف إعادة الرفع" if current_language == "ar" else "Further proof uploads are locked",
                "body": (
                    f"تم رفض العملية نهائيًا بعد عدة محاولات. السبب الأخير: {payment.rejection_reason}."
                    if current_language == "ar"
                    else f"This transfer was permanently rejected after multiple attempts. Last reason: {payment.rejection_reason}."
                ),
            }
    return render(request, "payment_checkout.html", {
        "deal": deal,
        "payment": payment,
        "site_settings": site_settings,
        "fee_rate_percent": _fee_rate_percent(),
        "ccp_status_summary": ccp_status_summary,
    })


@login_required(login_url="login")
@require_POST
def ccp_checkout_submit(request, deal_id):
    """معالجة رفع إثبات الدفع عبر CCP/BaridiMob."""
    deal = get_object_or_404(Deal, id=deal_id)
    self_purchase_response = _reject_self_purchase(request, deal)
    if self_purchase_response:
        return self_purchase_response
    if deal.buyer and request.user != deal.buyer:
        messages.error(request, "ليس لديك صلاحية.")
        return redirect("deal_detail", deal_id=deal.id)
    if hasattr(deal, "payment") and deal.payment.status in ("escrow_held", "released"):
        messages.info(request, "تم الدفع بالفعل لهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)

    existing_payment = getattr(deal, "payment", None)
    if existing_payment and existing_payment.payment_method == "ccp":
        if existing_payment.status == "pending_manual_verification":
            messages.warning(request, "إثبات الدفع الحالي ما زال قيد المراجعة. انتظر قرار الإدارة قبل رفع إثبات جديد.")
            return redirect("create_payment", deal_id=deal.id)
        if existing_payment.status == "failed_max_retries":
            messages.error(request, "تم إيقاف هذا الدفع بعد الوصول إلى الحد الأقصى من المحاولات. تواصل مع الإدارة إذا كنت بحاجة إلى المساعدة.")
            return redirect("deal_detail", deal_id=deal.id)

    proof_file = request.FILES.get("proof_file")
    reference_number = request.POST.get("reference_number", "").strip()

    if not proof_file:
        messages.error(request, "يرجى رفع صورة إثبات التحويل.")
        return redirect("create_payment", deal_id=deal.id)
    if not reference_number:
        messages.error(request, "يرجى إدخال رقم العملية (Reference).")
        return redirect("create_payment", deal_id=deal.id)

    try:
        validate_ccp_proof_file(proof_file)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("create_payment", deal_id=deal.id)

    payment, _ = Payment.objects.update_or_create(
        deal=deal,
        defaults={
            "payer": request.user,
            "amount": deal.price,
            "status": "pending_manual_verification",
            "payment_method": "ccp",
            "proof_file": proof_file,
            "reference_number": reference_number,
            "transaction_id": f"CCP-{uuid.uuid4().hex[:12].upper()}",
        },
    )
    if not payment.transfer_code:
        payment.transfer_code = f"ESCROW-{deal.id}-{uuid.uuid4().hex[:4].upper()}"
        payment.save(update_fields=["transfer_code"])

    # Notify all staff
    from django.contrib.auth.models import User as AuthUser
    for admin in AuthUser.objects.filter(is_staff=True):
        create_notification(
            recipient=admin,
            notif_type="payment",
            title=f"📋 دفع CCP جديد بانتظار المراجعة — صفقة #{deal.id}",
            body=f"{request.user.username} أرسل إثبات دفع بقيمة ${deal.price}.",
            url="/staff/pending-payments/",
        )

    messages.success(request, "✅ تم رفع إثبات الدفع بنجاح! سيتم مراجعته من قبل الإدارة.")
    return redirect("deal_detail", deal_id=deal.id)


@login_required(login_url="login")
@require_POST
def payment_confirm(request, deal_id):
    """إنشاء جلسة Stripe Checkout وإعادة التوجيه للدفع."""
    deal = get_object_or_404(Deal, id=deal_id)
    self_purchase_response = _reject_self_purchase(request, deal)
    if self_purchase_response:
        return self_purchase_response
    if deal.buyer and request.user != deal.buyer:
        messages.error(request, "ليس لديك صلاحية.")
        return redirect("deal_detail", deal_id=deal.id)
    if hasattr(deal, "payment") and deal.payment.status in ("escrow_held", "released"):
        messages.info(request, "تم الدفع مسبقاً.")
        return redirect("deal_detail", deal_id=deal.id)

    existing_payment = getattr(deal, "payment", None)
    if existing_payment and existing_payment.status == "pending_manual_verification":
        messages.warning(request, "إثبات الدفع الحالي ما زال قيد المراجعة.")
        return redirect("create_payment", deal_id=deal.id)

    if _stripe_is_configured():
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": settings.STRIPE_CURRENCY,
                            "product_data": {
                                "name": deal.product_title,
                                "description": (deal.product_description or "")[:500],
                            },
                            "unit_amount": int(deal.price * 100),
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=_build_absolute_url(
                    request, reverse("payment_success_page", args=[deal.id])
                ),
                cancel_url=_build_absolute_url(
                    request, f"{reverse('payment_cancel')}?deal_id={deal.id}"
                ),
                client_reference_id=str(deal.id),
                customer_email=request.user.email or None,
                metadata={
                    "deal_id": str(deal.id),
                    "buyer_id": str(request.user.id),
                },
                payment_intent_data={
                    "metadata": {
                        "deal_id": str(deal.id),
                        "buyer_id": str(request.user.id),
                    },
                },
            )

            Payment.objects.update_or_create(
                deal=deal,
                defaults={
                    "payer": request.user,
                    "amount": deal.price,
                    "status": "pending",
                    "transaction_id": session.id,
                },
            )

            return redirect(session.url)
        except stripe.error.StripeError as e:
            logger.error("Stripe session creation failed for deal %s: %s", deal.id, e)
            messages.error(request, "حدث خطأ أثناء إعداد الدفع. يرجى المحاولة لاحقاً.")
            return redirect("deal_detail", deal_id=deal.id)

    logger.warning("Stripe is not configured. Payment for deal %s was NOT processed.", deal.id)
    messages.warning(
        request,
        "بوابة الدفع غير مفعلة حالياً. لا يمكن إتمام الدفع الآن، يرجى التواصل مع الإدارة.",
    )
    return redirect("deal_detail", deal_id=deal.id)


@login_required(login_url="login")
def payment_success_page(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id)
    payment = getattr(deal, "payment", None)
    if not payment:
        messages.warning(request, "لا توجد عملية دفع مرتبطة بهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)
    allowed_user_ids = {deal.buyer_id, deal.seller_id}
    if payment.payer_id:
        allowed_user_ids.add(payment.payer_id)
    if request.user.id not in allowed_user_ids and not request.user.is_staff:
        messages.error(request, "ليس لديك صلاحية عرض تفاصيل هذا الدفع.")
        return redirect("deal_detail", deal_id=deal.id)
    return render(request, "payment_success.html", {"deal": deal, "payment": payment})


@login_required(login_url="login")
def invoice_detail(request, invoice_id):
    if not model_table_exists(TransactionInvoice):
        messages.warning(request, "Invoice tables are not available yet. Please run migrations first.")
        return redirect("profile")

    invoice = get_object_or_404(
        TransactionInvoice.objects.select_related("buyer", "seller", "deal", "payment"),
        id=invoice_id,
    )
    allowed_users = {invoice.buyer_id, invoice.seller_id}
    if request.user.id not in allowed_users and not request.user.is_staff:
        messages.error(request, "ليس لديك صلاحية عرض هذه الفاتورة.")
        return redirect("profile")

    return render(request, "invoice_detail.html", {"invoice": invoice})


@login_required(login_url="login")
@require_POST
def payment_release(request, deal_id):
    """تحرير المبلغ للبائع عبر مسار موحد."""
    deal = get_object_or_404(Deal, id=deal_id)
    if not (request.user.is_superuser or has_role_or_legacy_staff(request.user, "finance_admin")):
        messages.error(request, "ليس لديك صلاحية تحرير المبلغ.")
        return redirect("deal_detail", deal_id=deal.id)
    if not hasattr(deal, "payment"):
        messages.error(request, "لا يوجد دفع مرتبط بهذه الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)

    try:
        _, net_amount, fee_amount, _ = release_payment_for_deal(
            deal,
            audit_admin=request.user,
            audit_reason="Admin release from direct payment action.",
        )
    except PaymentStateError:
        messages.warning(request, "المبلغ ليس محتجزاً في Escrow.")
        return redirect("deal_detail", deal_id=deal.id)

    messages.success(request, f"✅ تم تحرير المبلغ! الصافي للبائع: ${net_amount} | عمولة المنصة: ${fee_amount}")
    return redirect("deal_detail", deal_id=deal.id)


@login_required(login_url="login")
@require_POST
def payment_refund(request, deal_id):
    """استرداد المبلغ عبر مسار موحد."""
    deal = get_object_or_404(Deal, id=deal_id)
    if not (request.user.is_superuser or has_role_or_legacy_staff(request.user, "finance_admin")):
        messages.error(request, "ليس لديك صلاحية.")
        return redirect("deal_detail", deal_id=deal.id)

    try:
        payment, _ = refund_payment_for_deal(
            deal,
            audit_admin=request.user,
            audit_reason="Admin refund from direct payment action.",
        )
    except PaymentStateError as exc:
        if str(exc) == "unmappable_reference":
            messages.error(request, "مرجع الدفع الحالي لا يسمح بتنفيذ استرداد Stripe بأمان.")
        elif str(exc) == "stripe_not_configured":
            messages.error(request, "تم حظر الاسترداد لأن Stripe غير مفعل بشكل صحيح. لم يتم تغيير حالة الدفع.")
        elif str(exc) == "missing_reference":
            messages.error(request, "تم حظر الاسترداد لأن مرجع عملية Stripe مفقود.")
        else:
            messages.warning(request, "لا يمكن استرداد هذا الدفع.")
        return redirect("deal_detail", deal_id=deal.id)
    except stripe.error.StripeError as e:
        logger.error("Stripe refund failed for deal %s: %s", deal.id, e)
        messages.error(request, "فشل استرداد المبلغ من Stripe. لم يتم تغيير حالة الصفقة.")
        return redirect("deal_detail", deal_id=deal.id)

    messages.success(request, f"✅ تم استرداد المبلغ ${payment.amount} للمشتري!")
    return redirect("deal_detail", deal_id=deal.id)


@login_required(login_url="login")
def payment_cancel(request):
    deal_id = request.GET.get("deal_id")
    messages.warning(request, "تم إلغاء عملية الدفع.")
    return redirect("deal_detail", deal_id=deal_id)


def payment_success(request):
    deal_id = request.GET.get("deal_id")
    if deal_id:
        return redirect("payment_success_page", deal_id=deal_id)
    return redirect("my_deals")


def _mark_stripe_event_processed(stripe_event):
    """Mark a previously-recorded StripeEvent as successfully processed."""
    if stripe_event is None:
        return
    from django.utils import timezone

    stripe_event.processed = True
    stripe_event.processed_at = timezone.now()
    stripe_event.save(update_fields=["processed", "processed_at"])


def _process_stripe_event(event):
    """Dispatch a single verified Stripe event to the relevant handler.

    Returns an HttpResponse status code. Only ``checkout.session.completed``
    is handled today; other event types are intentionally acknowledged so
    Stripe stops retrying them, but are still recorded for auditability.
    """
    event_type = event["type"]

    if event_type != "checkout.session.completed":
        logger.info("Stripe webhook: ignoring unhandled event type %s (evt=%s).", event_type, event.get("id"))
        return 200

    session = event["data"]["object"]
    deal_id = session.get("metadata", {}).get("deal_id")
    buyer_id = session.get("metadata", {}).get("buyer_id")

    if not deal_id:
        logger.error("Stripe webhook: checkout.session.completed without deal_id in metadata (evt=%s).", event.get("id"))
        return 400

    try:
        deal = Deal.objects.get(id=int(deal_id))
        buyer = User.objects.get(id=int(buyer_id)) if buyer_id else deal.buyer

        txn_id = (
            session.get("payment_intent")
            or session.get("id")
            or f"ESC-{uuid.uuid4().hex[:12].upper()}"
        )
        process_successful_payment(deal, buyer, transaction_id=txn_id, payment_method="stripe")
    except Deal.DoesNotExist:
        logger.error("Stripe webhook: deal %s not found (evt=%s).", deal_id, event.get("id"))
        return 400
    except Exception:
        logger.exception("Stripe webhook: error processing deal %s (evt=%s).", deal_id, event.get("id"))
        return 500

    return 200


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """معالجة أحداث Stripe بعد التحقق من التوقيع.

    Guarantees at-most-once processing by persisting each received Stripe
    ``event.id`` in a dedicated table before any business logic runs. Stripe
    retries webhook delivery on non-2xx responses; a retried event whose row
    is already ``processed`` is acknowledged immediately, while a row left
    ``processed=False`` (because processing failed) is retried on the next
    delivery attempt.
    """
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "").strip()
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "").strip()

    if not webhook_secret or webhook_secret == "whsec_...":
        logger.warning("Stripe webhook secret is not configured.")
        return HttpResponse(status=503)
    if not signature:
        logger.warning("Stripe webhook received without signature.")
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=signature,
            secret=webhook_secret,
        )
    except ValueError:
        logger.error("Stripe webhook: invalid payload.")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.error("Stripe webhook: signature verification failed.")
        return HttpResponse(status=400)

    event_id = event.get("id")
    event_type = event.get("type", "")
    api_version = event.get("api_version", "") or ""

    if not event_id:
        logger.error("Stripe webhook: verified event is missing an id (type=%s).", event_type)
        return HttpResponse(status=400)

    # Record (or retrieve) the event in its own short transaction. A duplicate
    # delivery of an already-processed event is acknowledged immediately; a
    # duplicate of a previously-failed event is reprocessed.
    with transaction.atomic():
        stripe_event, created = StripeEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "api_version": api_version,
            },
        )
        if not created and stripe_event.processed:
            logger.info("Stripe webhook: duplicate event %s already processed, skipping.", event_id)
            return HttpResponse(status=200)

    # Process outside the bookkeeping transaction so its rollback does not
    # wipe the event record. If processing fails the row stays ``processed``
    # set to True at the end of this branch.
    status_code = _process_stripe_event(event)

    if status_code < 500:
        _mark_stripe_event_processed(stripe_event)
        return HttpResponse(status=status_code)

    # Processing failed (HTTP 5xx): leave the row unprocessed so Stripe
    # retries, and we can reprocess the same event id safely.
    return HttpResponse(status=status_code)
