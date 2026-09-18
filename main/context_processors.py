from django.conf import settings
from django.core.cache import cache
from django.templatetags.static import static

from .i18n import SUPPORTED_LANGUAGES, get_request_language, get_translation
from .models import Notification
from .services.admin_roles import ADMIN_ROLE_SPECS, get_user_role_keys


def _build_default_share_context(request, language):
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    site_url = getattr(settings, "SITE_URL", "").strip().rstrip("/")
    request_base_url = request.build_absolute_uri("/").rstrip("/")
    base_url = request_base_url or site_url
    share_title = get_translation("site.name", language)
    share_description = get_translation("footer.tagline", language)

    if url_name == "home":
        share_title = get_translation("home.title", language)
        share_description = " ".join(
            filter(
                None,
                [
                    get_translation("home.hero_desc_1", language),
                    get_translation("home.hero_desc_2", language),
                ],
            )
        )
    elif url_name == "about":
        share_title = get_translation("about.title", language)
        share_description = get_translation("about.hero_text", language)
    elif url_name == "listings":
        share_title = get_translation("deals.title", language)
        share_description = get_translation("footer.tagline", language)
    elif url_name == "how_it_works":
        share_title = get_translation("how_it_works.share_title", language)
        share_description = get_translation("how_it_works.meta_description", language)

    return {
        "default_share_title": share_title,
        "default_share_description": share_description,
        "default_share_url": request.build_absolute_uri(),
        "default_share_image_url": f"{base_url}{static('images/brand/og-card.png')}",
        "default_share_image_alt": share_title,
        "brand_logo_url": f"{base_url}{static('images/brand/logo-primary.png')}",
        "brand_mark_url": f"{base_url}{static('images/brand/icon-192.png')}",
        "brand_hero_image_url": f"{base_url}{static('images/brand/og-card.png')}",
        "brand_logo_email_src": f"{base_url}{static('images/brand/logo-primary.png')}",
        "brand_hero_email_src": f"{base_url}{static('images/brand/og-card.png')}",
        "site_url": base_url,
        "site_brand_name": share_title,
        "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", "").strip(),
    }


def site_language(request):
    language = get_request_language(request)
    unread_notif_count = 0
    admin_role_keys = set()

    if getattr(request, "user", None) and request.user.is_authenticated:
        # The navbar is rendered on every authenticated request. Cache this
        # badge briefly instead of issuing another COUNT query on every load.
        notification_cache_key = f"unread_notification_count:{request.user.pk}"
        unread_notif_count = cache.get(notification_cache_key)
        if unread_notif_count is None:
            unread_notif_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
            ).count()
            cache.set(notification_cache_key, unread_notif_count, 10)
        if request.user.is_superuser:
            admin_role_keys = set(ADMIN_ROLE_SPECS.keys())
        elif request.user.is_staff:
            admin_role_keys = set(get_user_role_keys(request.user))

    return {
        "current_language": language,
        "current_dir": "rtl" if language == "ar" else "ltr",
        "available_languages": SUPPORTED_LANGUAGES,
        "language_label": get_translation("lang.current", language),
        "unread_notif_count": unread_notif_count,
        "nav_has_security_access": (
            bool(getattr(request, "user", None) and request.user.is_superuser)
            or "security_admin" in admin_role_keys
        ),
        "nav_has_support_access": (
            bool(getattr(request, "user", None) and request.user.is_superuser)
            or "support_admin" in admin_role_keys
        ),
        "nav_has_finance_access": (
            bool(getattr(request, "user", None) and request.user.is_superuser)
            or "finance_admin" in admin_role_keys
        ),
        "nav_has_operations_access": (
            bool(getattr(request, "user", None) and request.user.is_superuser)
            or "operations_admin" in admin_role_keys
        ),
        **_build_default_share_context(request, language),
    }
