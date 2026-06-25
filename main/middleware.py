import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils import translation

from .i18n import get_request_language

logger = logging.getLogger(__name__)

class SecurityHeadersMiddleware:
    """
    Adds basic security headers to every response to protect against 
    clickjacking, XSS, and MIME-sniffing attacks.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        response.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), browsing-topics=()',
        )
        # Can add Strict-Transport-Security (HSTS) if running on HTTPS
        # response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response


class PerformanceHeadersMiddleware:
    """Adds lightweight delivery headers for faster repeat visits and diagnostics."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.setdefault("X-DNS-Prefetch-Control", "on")
        response.setdefault("Server-Timing", f"app;dur={elapsed_ms:.1f}")

        path = request.path
        static_url = getattr(settings, "STATIC_URL", "/static/")
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        content_type = (response.headers.get("Content-Type") or "").lower()

        if path.startswith(static_url):
            response["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        if media_url and path.startswith(media_url):
            response.setdefault(
                "Cache-Control",
                "public, max-age=604800, stale-while-revalidate=86400",
            )
            return response

        if "text/html" in content_type:
            patch_vary_headers(response, ["Cookie", "Accept-Language", "Accept-Encoding"])
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                response.setdefault("Cache-Control", "private, no-store, max-age=0")
            else:
                response.setdefault("Cache-Control", "private, no-cache, max-age=0, must-revalidate")

        return response


class RateLimitMiddleware:
    """
    A lightweight rate limiter to prevent basic spam or abuse.
    It limits POST requests per actor and per endpoint so one noisy form
    does not accidentally block the rest of the site for that user/IP.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We only strictly rate-limit POST requests for now (e.g. creating deals, disputes)
        if request.method == "POST":
            actor = self.get_rate_limit_actor(request)
            scope = getattr(getattr(request, "resolver_match", None), "url_name", "") or request.path
            cache_key = f"rate_limit_{actor}_{scope}"
            
            # Allow 15 POST requests per minute per IP
            requests = cache.get(cache_key, [])
            now = time.time()
            
            # Remove requests older than 60 seconds
            requests = [req for req in requests if now - req < 60]
            
            if len(requests) >= 15:
                return HttpResponseForbidden("Too many requests. Please wait a moment and try again.")
            
            requests.append(now)
            cache.set(cache_key, requests, 60)

        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get_rate_limit_actor(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"user_{user.pk}"
        return f"ip_{self.get_client_ip(request)}"


class SiteLanguageMiddleware:
    """
    Activates the selected site language for Django's own translations.
    This keeps auth forms, validator messages, and built-in pages aligned
    with the custom template translation system.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        previous_language = translation.get_language()
        language = get_request_language(request)
        request.LANGUAGE_CODE = language

        session = getattr(request, "session", None)
        if session is not None:
            current_session_language = session.get("site_language")
            has_language_cookie = bool(
                request.COOKIES.get("site_language")
                or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
            )
            if current_session_language and current_session_language != language:
                session["site_language"] = language
            elif current_session_language is None and has_language_cookie:
                session["site_language"] = language

        translation.activate(language)
        try:
            response = self.get_response(request)
        finally:
            if previous_language:
                translation.activate(previous_language)
            else:
                translation.deactivate()

        response.headers.setdefault("Content-Language", language)
        return response


class AdminProtectionMiddleware:
    """
    Compatibility middleware kept in the stack for admin hardening hooks.
    Access control is enforced by Django admin and explicit view decorators.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


class Custom404Middleware:
    """
    Render friendly HTML error pages even while DEBUG=True.
    This keeps ngrok/staging previews user-facing instead of exposing
    Django's technical error pages for normal browser requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _wants_html(self, request):
        accept = request.headers.get("Accept", "")
        if not accept:
            return True
        return "text/html" in accept or "*/*" in accept

    def _is_api_like_request(self, request):
        return (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
            or request.path.startswith("/admin/")
        )

    def _should_render_custom_error(self, request):
        return self._wants_html(request) and not self._is_api_like_request(request)

    def _response_is_html(self, response):
        content_type = (response.headers.get("Content-Type") or "").lower()
        if not content_type:
            return True
        return "text/html" in content_type

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception:
            logger.exception("Unhandled exception while serving %s", request.path)
            if self._should_render_custom_error(request):
                return render(request, "500.html", status=500)
            raise

        if not self._should_render_custom_error(request):
            return response

        if not self._response_is_html(response):
            return response

        if response.status_code == 404:
            return render(request, "404.html", status=404)
        if response.status_code == 403:
            return render(request, "403.html", status=403)
        if response.status_code == 503:
            return render(request, "503.html", status=503)
        if response.status_code >= 500:
            return render(request, "500.html", status=500)
        return response
