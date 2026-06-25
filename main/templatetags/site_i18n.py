from django import template
from django.templatetags.static import static

from main.i18n import get_request_language, get_translation
from main.services.verification import render_verification_badge

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, key):
    request = context.get("request")
    language = get_request_language(request)
    return get_translation(key, language)


@register.simple_tag(takes_context=True)
def choice_label(context, prefix, value):
    request = context.get("request")
    language = get_request_language(request)
    return get_translation(f"{prefix}.{value}", language)


@register.simple_tag
def verification_badge(profile):
    return render_verification_badge(profile)


@register.filter
def file_url(file_field, fallback="images/default_avatar.jpg"):
    """Return a safe URL for optional ImageField/FileField values."""
    try:
        if file_field and getattr(file_field, "url", None):
            return file_field.url
    except (ValueError, AttributeError):
        pass
    return static(fallback)
