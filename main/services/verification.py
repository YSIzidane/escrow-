from django.utils.html import format_html


def get_verification_badge_meta(profile):
    if not profile or not getattr(profile, "is_verified", False):
        return None

    if getattr(profile, "verification_tier", "standard") == "gold":
        return {
            "label": "Gold verified owner",
            "badge_class": "se-verified-badge-gold",
            "icon": "fa-crown",
        }

    return {
        "label": "Verified account",
        "badge_class": "se-verified-badge-standard",
        "icon": "fa-check-circle",
    }


def render_verification_badge(profile):
    badge = get_verification_badge_meta(profile)
    if not badge:
        return ""

    return format_html(
        '<span class="se-verified-badge {}" title="{}" aria-label="{}"><i class="fas {}"></i></span>',
        badge["badge_class"],
        badge["label"],
        badge["label"],
        badge["icon"],
    )
