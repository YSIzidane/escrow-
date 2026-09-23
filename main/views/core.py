# ==================== Core Views ====================
import json
import logging
import mimetypes
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..i18n import SUPPORTED_LANGUAGES, get_translation, normalize_language
from ..models import Deal, SupportTicket

PUBLIC_MEDIA_PREFIXES = {"avatars", "deal_images"}
perf_logger = logging.getLogger("main.performance")


def _fee_rate_percent():
    return int(Decimal(str(getattr(settings, "ESCROW_FEE_PERCENTAGE", 0.05))) * 100)


def _active_public_deals_queryset(now=None):
    now = now or timezone.now()
    return (
        Deal.objects.filter(status__in=["new", "reserved"])
        .filter(
            Q(status="reserved")
            | Q(is_auction=False)
            | Q(auction_ends_at__isnull=True)
            | Q(auction_ends_at__gt=now)
        )
        .select_related("seller__profile")
        # Auction bids are only needed on the listings page. Keeping them out
        # of this shared queryset avoids loading every bid on home and search.
        .prefetch_related("images")
    )


def home(request):
    """Render the homepage with the latest public deals."""
    public_deals_qs = _active_public_deals_queryset()
    latest_deals = list(public_deals_qs.order_by("-created_at")[:6])

    for deal in latest_deals:
        images = list(deal.images.all())
        deal.cover_image = images[0] if images else None
        deal.display_price = deal.starting_price if deal.is_auction else deal.price

    home_stats = cache.get("public_home_stats:v1")
    if home_stats is None:
        home_stats = {
            "users_count": User.objects.count(),
            "public_deals_count": public_deals_qs.count(),
            "completed_deals_count": Deal.objects.filter(status="completed").count(),
        }
        # These are display counters, not authorization data. A short cache
        # removes three database COUNT queries from every homepage visit.
        cache.set("public_home_stats:v1", home_stats, 30)

    return render(
        request,
        "home.html",
        {
            "latest_deals": latest_deals,
            "fee_rate_percent": _fee_rate_percent(),
            "home_stats": home_stats,
        },
    )


def about(request):
    """About page with trust, fee, and product guidance context."""
    stats = {
        "users_count": User.objects.count(),
        "deals_count": Deal.objects.count(),
        "completed_deals_count": Deal.objects.filter(status="completed").count(),
        "open_tickets_count": SupportTicket.objects.filter(
            status__in=["open", "in_progress"]
        ).count(),
    }
    return render(
        request,
        "about.html",
        {
            "stats": stats,
            "fee_rate_percent": _fee_rate_percent(),
        },
    )


def how_it_works(request):
    """Simple onboarding and education page for new users."""
    return render(
        request,
        "how_it_works.html",
        {
            "fee_rate_percent": _fee_rate_percent(),
        },
    )


def listings_view(request):
    """Public deals page with live filters and lightweight search."""
    now = timezone.now()
    deal_type = request.GET.get("type", "")
    status_filter = request.GET.get("status", "")
    category_filter = request.GET.get("category", "")
    price_min = request.GET.get("price_min", "").strip()
    price_max = request.GET.get("price_max", "").strip()
    sort_by = request.GET.get("sort", "")
    query = request.GET.get("q", "").strip()

    all_deals = (
        _active_public_deals_queryset(now)
        .prefetch_related("bids")
        .annotate(
            bid_count=Count("bids", distinct=True),
            seller_review_count=Count("seller__received_reviews", distinct=True),
        )
    )

    if query:
        all_deals = all_deals.filter(
            Q(product_title__icontains=query)
            | Q(product_description__icontains=query)
            | Q(seller__username__icontains=query)
        )

    if deal_type == "auction":
        all_deals = all_deals.filter(is_auction=True)
    elif deal_type == "fixed":
        all_deals = all_deals.filter(is_auction=False)

    if category_filter:
        all_deals = all_deals.filter(category=category_filter)

    if status_filter in ["new", "reserved"]:
        all_deals = all_deals.filter(status=status_filter)

    if price_min:
        try:
            min_amount = Decimal(price_min)
            all_deals = all_deals.filter(
                Q(price__gte=min_amount) | Q(starting_price__gte=min_amount)
            )
        except (InvalidOperation, ValueError):
            pass

    if price_max:
        try:
            max_amount = Decimal(price_max)
            all_deals = all_deals.filter(
                Q(price__lte=max_amount) | Q(starting_price__lte=max_amount)
            )
        except (InvalidOperation, ValueError):
            pass

    if sort_by == "price_low":
        all_deals = all_deals.order_by("price", "starting_price", "-created_at")
    elif sort_by == "price_high":
        all_deals = all_deals.order_by("-price", "-starting_price", "-created_at")
    elif sort_by == "bids":
        all_deals = all_deals.order_by("-bid_count", "-created_at")
    else:
        all_deals = all_deals.order_by("-created_at")

    paginator = Paginator(all_deals, 12)
    page_number = request.GET.get("page")
    deals_page = paginator.get_page(page_number)

    context = {
        "deals": deals_page,
        "search_query": query,
        "fee_rate_percent": _fee_rate_percent(),
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "partials/deals_grid.html", context)

    return render(request, "deals.html", context)


def search_user(request):
    """Search users and deals with lightweight relevance ranking."""
    now = timezone.now()
    query = request.GET.get("q", "").strip()
    active_tab = request.GET.get("tab", "").strip() or "all"
    users_page = []
    deals_page = []
    users_total = 0
    deals_total = 0
    query_too_short = bool(query) and len(query) < 2

    if query and not query_too_short:
        users_qs = (
            User.objects.select_related("profile")
            .annotate(
                relevance=Case(
                    When(username__iexact=query, then=Value(120)),
                    When(username__istartswith=query, then=Value(90)),
                    When(username__icontains=query, then=Value(70)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                published_deals_count=Count("seller_deals", distinct=True),
            )
            .filter(relevance__gt=0)
        )
        if request.user.is_authenticated:
            users_qs = users_qs.exclude(id=request.user.id)
        users_qs = users_qs.order_by("-relevance", "-published_deals_count", "username")

        deals_qs = (
            _active_public_deals_queryset(now)
            .annotate(
                bid_count=Count("bids", distinct=True),
                relevance=Case(
                    When(product_title__iexact=query, then=Value(160)),
                    When(product_title__istartswith=query, then=Value(130)),
                    When(product_title__icontains=query, then=Value(100)),
                    When(seller__username__istartswith=query, then=Value(75)),
                    When(seller__username__icontains=query, then=Value(60)),
                    When(product_description__icontains=query, then=Value(40)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .filter(
                Q(product_title__icontains=query)
                | Q(product_description__icontains=query)
                | Q(seller__username__icontains=query)
            )
            .order_by("-relevance", "-created_at")
        )

        users_total = users_qs.count()
        deals_total = deals_qs.count()

        users_paginator = Paginator(users_qs, 10)
        deals_paginator = Paginator(deals_qs, 12)
        users_page = users_paginator.get_page(request.GET.get("page_users"))
        deals_page = deals_paginator.get_page(request.GET.get("page_deals"))

        if active_tab == "all":
            active_tab = "deals" if deals_total >= users_total else "users"

    context = {
        "users": users_page,
        "deals": deals_page,
        "query": query,
        "query_too_short": query_too_short,
        "users_total": users_total,
        "deals_total": deals_total,
        "active_tab": active_tab,
        "fee_rate_percent": _fee_rate_percent(),
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "partials/search_results.html", context)

    return render(request, "search.html", context)


@require_POST
def set_site_language(request):
    language = request.POST.get("language", "ar").strip().lower()
    next_url = request.POST.get("next", "").strip() or request.META.get(
        "HTTP_REFERER", ""
    )

    if language not in SUPPORTED_LANGUAGES:
        language = "ar"

    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"

    request.session["site_language"] = language
    response = redirect(next_url)
    response.set_cookie("site_language", language, max_age=60 * 60 * 24 * 365)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=60 * 60 * 24 * 365,
    )
    return response


def health_check(request):
    """Lightweight health endpoint for containers, load balancers, and uptime checks."""
    database_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        database_ok = False

    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "error",
    }
    status_code = 200 if database_ok else 503

    if request.GET.get("format") == "text":
        response = HttpResponse(payload["status"], status=status_code, content_type="text/plain")
    else:
        response = JsonResponse(payload, status=status_code)

    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@csrf_exempt
@require_POST
def performance_vitals(request):
    """Receive sampled Core Web Vitals beacons without writing user data."""
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False}, status=400)
    if content_length > 4096:
        return HttpResponse(status=413)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False}, status=400)

    allowed_keys = {
        "path", "page", "nav", "fcp", "lcp", "cls", "inp", "tbt",
        "dcl", "load", "effectiveType", "saveData", "viewport",
    }
    clean_payload = {key: payload.get(key) for key in allowed_keys if key in payload}
    perf_logger.info("web_vitals %s", clean_payload)
    response = HttpResponse(status=204)
    response["Cache-Control"] = "no-store"
    return response


def public_media_file(request, relative_path):
    """Serve only explicitly public media folders when running without object storage."""
    if getattr(settings, "USE_S3_STORAGE", False) or not settings.MEDIA_ROOT:
        raise Http404("Public media is not available from this server.")

    normalized_path = Path(relative_path)
    if normalized_path.is_absolute() or ".." in normalized_path.parts or not normalized_path.parts:
        raise Http404("Invalid media path.")

    if normalized_path.parts[0] not in PUBLIC_MEDIA_PREFIXES:
        raise Http404("This media path is not public.")

    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (media_root / normalized_path).resolve()
    if media_root not in candidate.parents and candidate != media_root:
        raise Http404("Invalid media path.")
    if not candidate.is_file():
        raise Http404("Media file not found.")

    content_type, _ = mimetypes.guess_type(str(candidate))
    response = FileResponse(candidate.open("rb"), content_type=content_type or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
    return response


# ==================== Policy Pages ====================
def privacy_policy(request):
    return render(request, "policies/privacy.html")


def terms_policy(request):
    return render(request, "policies/terms.html")


def returns_policy(request):
    return render(request, "policies/returns.html")


# ==================== Error Pages ====================
def view_403(request, exception=None):
    return render(request, "403.html", status=403)


def view_404(request, exception=None):
    return render(request, "404.html", status=404)


def view_500(request):
    return render(request, "500.html", status=500)


def view_503(request):
    maintenance_end = None
    maintenance_end_raw = getattr(settings, "MAINTENANCE_END_AT", "").strip()
    if maintenance_end_raw:
        maintenance_end = parse_datetime(maintenance_end_raw)
        if maintenance_end and timezone.is_naive(maintenance_end):
            maintenance_end = timezone.make_aware(maintenance_end, timezone.get_current_timezone())

    return render(
        request,
        "503.html",
        {
            "maintenance_end": maintenance_end,
            "maintenance_end_iso": maintenance_end.isoformat() if maintenance_end else "",
        },
        status=503,
    )
