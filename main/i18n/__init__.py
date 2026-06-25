# i18n/__init__.py — Bilingual translation system
from django.conf import settings

from .ar import TRANSLATIONS_AR
from .en import TRANSLATIONS_EN

SUPPORTED_LANGUAGES = ("ar", "en")
DEFAULT_LANGUAGE = "ar"

TRANSLATIONS = {
    "ar": TRANSLATIONS_AR,
    "en": TRANSLATIONS_EN,
}


def normalize_language(language):
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def get_request_language(request, default=None):
    fallback_language = normalize_language(default or DEFAULT_LANGUAGE)
    if request is None:
        return fallback_language

    session = getattr(request, "session", None)
    cookies = getattr(request, "COOKIES", {})
    candidates = [
        session.get("site_language") if session is not None else None,
        cookies.get("site_language"),
        cookies.get(getattr(settings, "LANGUAGE_COOKIE_NAME", "django_language")),
        getattr(request, "LANGUAGE_CODE", None),
    ]

    for candidate in candidates:
        if candidate:
            return normalize_language(candidate)
    return fallback_language


def get_translation(key, language=None):
    language = normalize_language(language)
    return TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE]).get(key, key)


__all__ = [
    "SUPPORTED_LANGUAGES", "DEFAULT_LANGUAGE", "TRANSLATIONS",
    "normalize_language", "get_request_language", "get_translation",
]
