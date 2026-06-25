# ==================== Social Views ====================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Avg, Count
from django.http import JsonResponse
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from decimal import Decimal
from django.conf import settings as django_settings
from django.db import transaction
from ..forms import WithdrawalRequestForm
from ..models import (
    Deal,
    Friendship,
    Notification,
    Profile,
    Review,
    TransactionInvoice,
    WithdrawalRequest,
)
from ..i18n import get_request_language, get_translation
from ..utils import model_table_exists
from ..validators import validate_kyc_file
from .notifications import create_notification


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _ajax_response(request, message, message_type='success', status=200, **extra):
    list(messages.get_messages(request))
    payload = {
        'status': 'ok' if status < 400 else 'error',
        'message': message,
        'message_type': message_type,
    }
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _first_form_error(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return ""


def _get_friendship_state(request_user, profile_user):
    friendship = Friendship.objects.filter(
        Q(from_user=request_user, to_user=profile_user) |
        Q(from_user=profile_user, to_user=request_user)
    ).first()

    return {
        'is_friend': friendship.status == 'accepted' if friendship else False,
        'request_sent': (
            friendship.status == 'pending' and friendship.from_user == request_user
            if friendship else False
        ),
    }


def _get_friends_page_context(user):
    friends = User.objects.filter(
        Q(friendships_received__from_user=user, friendships_received__status='accepted') |
        Q(friendships_sent__to_user=user, friendships_sent__status='accepted')
    ).distinct().select_related('profile').annotate(
        published_deals_count=Count('seller_deals', distinct=True),
    ).order_by('username')

    pending_requests = Friendship.objects.filter(
        to_user=user, status='pending'
    ).select_related('from_user__profile')

    return {
        'friends': friends,
        'pending_requests': pending_requests,
        'friends_count': friends.count(),
        'pending_requests_count': pending_requests.count(),
    }


def _mask_email(email):
    email = (email or "").strip()
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _mask_phone(phone):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 4:
        return ""
    return f"+*** *** **{digits[-2:]}"


def _decorate_profile_deal(deal, user, language="ar"):
    counterpart = deal.buyer if deal.seller_id == user.id else deal.seller
    deal.profile_counterpart = counterpart
    deal.profile_counterpart_label = counterpart.username if counterpart else get_translation("my_deals.waiting", language)
    deal.profile_amount = deal.starting_price if deal.is_auction else deal.price
    return deal


def _build_profile_context(user, profile_obj, language="ar"):
    seller_deals = user.seller_deals.all()
    buyer_deals = user.buyer_deals.all()
    seller_deals_count = seller_deals.count()
    buyer_deals_count = buyer_deals.count()
    completed_sales = seller_deals.filter(status='completed').count()
    completed_buys = buyer_deals.filter(status='completed').count()
    reviews = user.received_reviews.all()
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']
    total_earned = sum(
        d.payment.amount for d in seller_deals.filter(status='completed')
        if hasattr(d, 'payment') and d.payment.status == 'released'
    )

    has_invoice_table = model_table_exists(TransactionInvoice)
    active_transactions = list(
        Deal.objects.filter(Q(seller=user) | Q(buyer=user))
        .filter(status__in=["reserved", "shipped", "delivered", "disputed"])
        .select_related("seller", "buyer")
        .order_by("-updated_at", "-created_at")[:5]
    )
    for deal in active_transactions:
        _decorate_profile_deal(deal, user, language)

    recent_activity_items = [
        {
            "kind": notification.notif_type,
            "title": notification.title,
            "body": notification.body,
            "url": notification.url,
            "created_at": notification.created_at,
        }
        for notification in Notification.objects.filter(recipient=user).order_by("-created_at")[:5]
    ]
    if user.last_login:
        recent_activity_items.append(
            {
                "kind": "login",
                "title": get_translation("profile.activity_login_title", language),
                "body": get_translation("profile.activity_login_body", language),
                "url": "",
                "created_at": user.last_login,
            }
        )
    recent_activity_items = sorted(
        recent_activity_items,
        key=lambda item: item["created_at"],
        reverse=True,
    )[:5]

    return {
        'profile': profile_obj,
        'completed_sales': completed_sales,
        'completed_buys': completed_buys,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'total_earned': total_earned,
        'seller_deals_count': seller_deals_count,
        'buyer_deals_count': buyer_deals_count,
        'total_deals': seller_deals_count + buyer_deals_count,
        'completed_deals_total': completed_sales + completed_buys,
        'masked_email': _mask_email(user.email),
        'masked_phone': _mask_phone(profile_obj.phone),
        'email_verified': bool(user.email),
        'phone_verified': bool(profile_obj.phone),
        'two_factor_enabled': False,
        'active_transactions': active_transactions,
        'recent_activity_items': recent_activity_items,
        'sale_invoices': (
            TransactionInvoice.objects.filter(seller=user).select_related('buyer', 'deal', 'payment')[:5]
            if has_invoice_table else []
        ),
        'purchase_invoices': (
            TransactionInvoice.objects.filter(buyer=user).select_related('seller', 'deal', 'payment')[:5]
            if has_invoice_table else []
        ),
        'account_role_names': list(user.groups.values_list('name', flat=True)),
        'withdrawal_enabled': getattr(django_settings, 'WITHDRAWAL_ENABLED', False),
    }


def _build_withdrawal_context(request, profile_obj, form=None):
    has_pending_withdrawal = request.user.withdrawals.filter(status='pending').exists()
    withdraw_block_reason = None

    if not profile_obj.can_withdraw:
        if profile_obj.kyc_status == 'pending':
            withdraw_block_reason = 'pending_kyc'
        elif profile_obj.kyc_status == 'rejected':
            withdraw_block_reason = 'rejected_kyc'
        else:
            withdraw_block_reason = 'missing_kyc'
    elif has_pending_withdrawal:
        withdraw_block_reason = 'pending_withdrawal'

    language = get_request_language(request)
    if form is None:
        form = WithdrawalRequestForm(
            max_balance=profile_obj.balance,
            language=language,
        )

    recent_withdrawals = request.user.withdrawals.order_by('-created_at')[:6]

    return {
        'profile': profile_obj,
        'has_pending_withdrawal': has_pending_withdrawal,
        'withdraw_block_reason': withdraw_block_reason,
        'recent_withdrawals': recent_withdrawals,
        'form': form,
        'method_hints': {
            'paypal': {
                'placeholder': 'example@paypal.com',
                'hint_ar': 'أدخل بريد PayPal الذي سيستقبل المبلغ.',
                'hint_en': 'Enter the PayPal email that should receive the payout.',
            },
            'bank': {
                'placeholder': 'Bank name / IBAN / account number',
                'hint_ar': 'أدخل اسم البنك واسم صاحب الحساب ورقم الحساب أو IBAN.',
                'hint_en': 'Enter the bank name, account holder name, and account or IBAN.',
            },
            'crypto': {
                'placeholder': 'USDT TRC20 wallet address',
                'hint_ar': 'أدخل عنوان محفظة USDT على شبكة TRC20 يبدأ بالحرف T.',
                'hint_en': 'Enter a USDT wallet address on the TRC20 network starting with T.',
            },
        },
    }


def _render_withdrawal_shell(request, context):
    return render_to_string('partials/withdraw_request_shell.html', context, request=request)


@login_required(login_url='login')
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    language = get_request_language(request)

    if request.method == "POST":
        # تغيير كلمة المرور
        if 'change_password' in request.POST:
            if not request.user.has_usable_password():
                language = get_request_language(request)
                messages.info(
                    request,
                    (
                        "هذا الحساب يستخدم Google حاليًا. أضف كلمة مرور محلية أولًا إذا أردت أيضًا تسجيل الدخول بالبريد وكلمة المرور."
                        if language == "ar"
                        else "This account currently signs in with Google. Set a local password first if you also want to log in by email and password."
                    ),
                )
                return redirect('account_set_password')
            from django.contrib.auth.forms import PasswordChangeForm
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'تم تغيير كلمة المرور بنجاح!')
            else:
                messages.error(request, 'تحقق من البيانات المدخلة')
            return redirect('profile')

        # تحديث بيانات الملف الشخصي
        first_name = request.POST.get("first_name", "").strip()[:30]
        last_name  = request.POST.get("last_name", "").strip()[:150]
        bio        = request.POST.get("bio", "").strip()
        phone      = request.POST.get("phone", "").strip()[:20]

        context = _build_profile_context(request.user, profile_obj, language)

        if len(bio) > 500:
            messages.error(request, "النبذة الشخصية طويلة جداً (500 حرف كحد أقصى).")
            return render(request, "profile.html", context)

        request.user.first_name = first_name
        request.user.last_name  = last_name
        profile_obj.bio   = bio
        profile_obj.phone = phone

        if 'avatar' in request.FILES:
            avatar = request.FILES['avatar']
            if avatar.content_type not in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']:
                messages.error(request, "صيغة الصورة غير مدعومة. استخدم JPG أو PNG.")
                return render(request, "profile.html", context)
            if avatar.size > 2 * 1024 * 1024:
                messages.error(request, "حجم الصورة كبير جداً (الحد الأقصى 2MB).")
                return render(request, "profile.html", context)
            profile_obj.avatar = avatar
        if 'kyc_document' in request.FILES:
            kyc_doc = request.FILES['kyc_document']
            try:
                validate_kyc_file(kyc_doc)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, "profile.html", _build_profile_context(request.user, profile_obj, language))
            else:
                profile_obj.kyc_document = kyc_doc
                profile_obj.kyc_status = 'pending'
                messages.success(request, "تم إرسال مستندات التوثيق بنجاح! سيتم مراجعتها قريباً.")

        request.user.save()
        profile_obj.save()
        messages.success(request, "تم تحديث الملف الشخصي بنجاح ✅")
        return redirect('profile')

    return render(request, "profile.html", _build_profile_context(request.user, profile_obj, language))


@login_required(login_url='login')
def user_profile(request, user_id):
    """عرض ملف شخصي لمستخدم آخر"""
    if request.user.id == user_id:
        return redirect('profile')

    profile_user = get_object_or_404(User, id=user_id)
    profile_obj, _ = Profile.objects.get_or_create(user=profile_user)
    display_name = profile_user.get_full_name() or profile_user.username

    friendship_state = _get_friendship_state(request.user, profile_user)

    seller_deals = profile_user.seller_deals.all()
    buyer_deals = profile_user.buyer_deals.all()
    seller_deals_count = seller_deals.count()
    buyer_deals_count = buyer_deals.count()
    completed_sales = seller_deals.filter(status='completed').count()
    completed_buys = buyer_deals.filter(status='completed').count()
    completed_deals_total = completed_sales + completed_buys
    total_deals = seller_deals_count + buyer_deals_count

    user_deals = seller_deals.filter(
        status__in=['new', 'reserved']
    ).select_related('seller__profile').prefetch_related('images', 'bids').order_by('-created_at')[:6]

    reviews = profile_user.received_reviews.select_related('reviewer__profile').all()
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

    return render(request, 'user_profile.html', {
        'profile_user': profile_user,
        'profile': profile_obj,
        'display_name': display_name,
        **friendship_state,
        'user_deals': user_deals,
        'seller_deals_count': seller_deals_count,
        'buyer_deals_count': buyer_deals_count,
        'completed_sales': completed_sales,
        'completed_buys': completed_buys,
        'completed_deals_total': completed_deals_total,
        'total_deals': total_deals,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })


@login_required(login_url='login')
def send_friend_request(request, user_id):
    to_user = get_object_or_404(User, id=user_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.user == to_user:
        error_message = "لا يمكنك إرسال طلب صداقة لنفسك."
        if is_ajax:
            return JsonResponse({
                'status': 'error',
                'message': error_message,
                'message_type': 'error',
            }, status=400)
        messages.error(request, error_message)
        return redirect('user_profile', user_id=user_id)

    response_message = ''
    message_type = 'info'

    existing = Friendship.objects.filter(
        Q(from_user=request.user, to_user=to_user) |
        Q(from_user=to_user, to_user=request.user)
    ).first()

    if existing:
        if existing.status == 'accepted':
            response_message = "أنتما أصدقاء بالفعل."
            message_type = 'info'
            messages.info(request, "أنتما أصدقاء بالفعل.")
        else:
            messages.info(request, "طلب الصداقة مُرسَل بالفعل.")
    else:
        Friendship.objects.create(from_user=request.user, to_user=to_user)
        messages.success(request, f"تم إرسال طلب الصداقة إلى {to_user.username}.")

    if existing and not response_message:
        response_message = "طلب الصداقة مُرسَل بالفعل."
        message_type = 'info'
    elif not existing:
        response_message = f"تم إرسال طلب الصداقة إلى {to_user.username}."
        message_type = 'success'

    if is_ajax:
        list(messages.get_messages(request))
        html = render_to_string(
            'partials/friend_action_state.html',
            {
                'profile_user': to_user,
                **_get_friendship_state(request.user, to_user),
            },
            request=request,
        )
        return JsonResponse({
            'status': 'ok',
            'message': response_message,
            'message_type': message_type,
            'html': html,
            'target_selector': f'#friend-action-slot-{to_user.id}',
            'swap': 'outerHTML',
        })

    return redirect('user_profile', user_id=user_id)


@login_required(login_url='login')
@require_POST
def accept_friend_request(request, request_id):
    friendship = get_object_or_404(
        Friendship, id=request_id, to_user=request.user, status='pending'
    )
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    friendship.status = 'accepted'
    friendship.save()
    messages.success(request, f"أصبحت صديقا لـ {friendship.from_user.username}.")
    if is_ajax:
        success_message = f"أصبحت صديقا لـ {friendship.from_user.username}."
        list(messages.get_messages(request))
        html = render_to_string(
            'partials/friends_sections.html',
            _get_friends_page_context(request.user),
            request=request,
        )
        return JsonResponse({
            'status': 'ok',
            'message': success_message,
            'message_type': 'success',
            'html': html,
            'target_selector': '#friends-sections',
            'swap': 'innerHTML',
        })

    return redirect('friends_list')


@login_required(login_url='login')
def friends_list(request):
    return render(request, 'friends_list.html', _get_friends_page_context(request.user))

@login_required(login_url='login')
def request_withdrawal(request):
    """Withdrawal request page."""
    if not getattr(django_settings, 'WITHDRAWAL_ENABLED', False):
        messages.warning(request, "عمليات السحب غير متاحة حاليا. تواصل مع الإدارة.")
        if _is_ajax(request):
            return _ajax_response(request, "عمليات السحب غير متاحة حاليا.", 'warning', 403)
        return redirect('profile')

    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    is_ajax = _is_ajax(request)
    language = get_request_language(request)
    context = _build_withdrawal_context(request, profile_obj)
    withdraw_block_reason = context['withdraw_block_reason']

    if request.method == 'POST':
        form = WithdrawalRequestForm(
            request.POST,
            max_balance=profile_obj.balance,
            language=language,
        )
        context = _build_withdrawal_context(request, profile_obj, form=form)
        withdraw_block_reason = context['withdraw_block_reason']

        if withdraw_block_reason == 'missing_kyc':
            message = "يجب توثيق حسابك والموافقة عليه قبل أن تتمكن من سحب الأرباح." if language == 'ar' else "Your account must be verified before you can withdraw earnings."
            messages.error(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'error', 403, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return redirect('profile')
        if withdraw_block_reason == 'pending_kyc':
            message = "طلب التوثيق ما زال قيد المراجعة. سيتاح السحب بعد الموافقة عليه." if language == 'ar' else "Your verification request is still under review. Withdrawals will be available after approval."
            messages.warning(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'warning', 403, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return redirect('profile')
        if withdraw_block_reason == 'rejected_kyc':
            message = "تم رفض مستندات التوثيق الحالية. حدّثها أولًا قبل إرسال طلب السحب." if language == 'ar' else "Your current verification document was rejected. Update it before submitting a withdrawal request."
            messages.error(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'error', 403, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return redirect('profile')
        if withdraw_block_reason == 'pending_withdrawal':
            message = "لديك طلب سحب معلق بالفعل. انتظر مراجعته قبل إنشاء طلب جديد." if language == 'ar' else "You already have a pending withdrawal request. Wait until it is reviewed before creating another one."
            messages.warning(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'warning', 409, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return redirect('request_withdrawal')

        if not form.is_valid():
            message = _first_form_error(form) or ("تحقق من البيانات المدخلة ثم حاول مرة أخرى." if language == 'ar' else "Please review your input and try again.")
            messages.error(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'error', 400, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return render(request, 'withdraw.html', context)

        amount = form.cleaned_data['amount']
        method = form.cleaned_data['method']
        details = form.cleaned_data['details']

        try:
            with transaction.atomic():
                locked_profile = Profile.objects.select_for_update().get(user=request.user)

                if not locked_profile.can_withdraw:
                    message = "يجب توثيق الحساب أولًا قبل السحب." if language == 'ar' else "Your account must be verified before you can withdraw."
                    messages.error(request, message)
                    if is_ajax:
                        refreshed_context = _build_withdrawal_context(request, locked_profile, form=form)
                        return _ajax_response(request, message, 'error', 403, html=_render_withdrawal_shell(request, refreshed_context), target_selector='#withdraw-page-shell', swap='outerHTML')
                    return redirect('request_withdrawal')

                if WithdrawalRequest.objects.select_for_update().filter(user=request.user, status='pending').exists():
                    message = "لديك طلب سحب معلق بالفعل. انتظر مراجعته أولًا." if language == 'ar' else "You already have a pending withdrawal request. Wait until it is reviewed."
                    messages.warning(request, message)
                    if is_ajax:
                        refreshed_context = _build_withdrawal_context(request, locked_profile, form=form)
                        return _ajax_response(request, message, 'warning', 409, html=_render_withdrawal_shell(request, refreshed_context), target_selector='#withdraw-page-shell', swap='outerHTML')
                    return redirect('request_withdrawal')

                if amount > locked_profile.balance:
                    form.add_error('amount', "المبلغ المطلوب أكبر من الرصيد المتاح." if language == 'ar' else "The requested amount is greater than your available balance.")
                    message = _first_form_error(form)
                    refreshed_context = _build_withdrawal_context(request, locked_profile, form=form)
                    messages.error(request, message)
                    if is_ajax:
                        return _ajax_response(request, message, 'error', 400, html=_render_withdrawal_shell(request, refreshed_context), target_selector='#withdraw-page-shell', swap='outerHTML')
                    return render(request, 'withdraw.html', refreshed_context)

                WithdrawalRequest.objects.create(
                    user=request.user,
                    amount=amount,
                    method=method,
                    details=details,
                )
                locked_profile.balance -= amount
                locked_profile.save()

            profile_obj.refresh_from_db()
            fresh_context = _build_withdrawal_context(request, profile_obj)
            create_notification(
                request.user,
                'withdrawal',
                "تم استلام طلب السحب" if language == 'ar' else "Withdrawal request received",
                (
                    f"تم استلام طلب سحب بمبلغ ${amount} وهو الآن بانتظار المراجعة."
                    if language == 'ar'
                    else f"Your ${amount} withdrawal request has been received and is now awaiting review."
                ),
                reverse('request_withdrawal'),
            )
            message = (
                f"تم إرسال طلب السحب بمبلغ ${amount} بنجاح، وهو الآن بانتظار المراجعة."
                if language == 'ar'
                else f"Your ${amount} withdrawal request was submitted successfully and is now waiting for review."
            )
            messages.success(request, message)
            if is_ajax:
                return _ajax_response(request, message, html=_render_withdrawal_shell(request, fresh_context), target_selector='#withdraw-page-shell', swap='outerHTML')
            return redirect('request_withdrawal')
        except ValidationError as exc:
            message = exc.messages[0] if exc.messages else ("تعذر إنشاء طلب السحب." if language == 'ar' else "We could not create the withdrawal request.")
            messages.error(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'error', 400, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')
        except Exception:
            message = "حدث خطأ أثناء إرسال طلب السحب. حاول مرة أخرى." if language == 'ar' else "Something went wrong while submitting the withdrawal request. Please try again."
            messages.error(request, message)
            if is_ajax:
                return _ajax_response(request, message, 'error', 500, html=_render_withdrawal_shell(request, context), target_selector='#withdraw-page-shell', swap='outerHTML')

    return render(request, 'withdraw.html', context)

