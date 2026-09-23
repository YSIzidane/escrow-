"""Smoke-test public UI pages after the DZHub design-unification phase.

Renders the main anonymous-accessible pages with Django's test client and
reports HTTP status codes plus template errors so UI regressions are caught
before commit.

Usage: python scripts/smoke_test_pages.py
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

PAGES = [
    ("home", "/"),
    ("how-it-works", "/how-it-works/"),
    ("about", "/about/"),
    ("deals", "/deals/"),
    ("search", "/search/"),
    ("login", "/accounts/login/"),
    ("signup", "/accounts/signup/"),
    ("privacy", "/privacy/"),
    ("terms", "/terms/"),
    ("returns", "/returns/"),
    ("support-create", "/support/create/"),
]


AUTH_PAGES = [
    ("profile", "/profile/"),
    ("deal-room", "/deal-room/"),
    ("escrow-dash", "/escrow/"),
    ("notifications", "/notifications/"),
    ("chat-hub", "/chat/"),
    ("friends", "/friends/"),
    ("my-tickets", "/support/"),
]


def run_authenticated(client: Client) -> list:
    """Smoke-test pages that require a session using an existing user."""
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(is_active=True).first()
    if user is None:
        print("[SKIP] No active user in DB to test authenticated pages.")
        return []

    client.force_login(user)
    failures = []
    for name, path in AUTH_PAGES:
        try:
            response = client.get(path)
            status = response.status_code
            ok = status in (200, 302)
        except Exception as exc:
            status = f"EXCEPTION: {type(exc).__name__}: {exc}"
            ok = False
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {name:16s} {path:24s} -> {status}")
        if not ok:
            failures.append((name, path, status))
    return failures


def check_dzhub_layer(client: Client) -> bool:
    """Confirm the DZHub theme layer is actually shipped in rendered HTML."""
    html = client.get("/").content.decode("utf-8", errors="replace")
    checks = {
        "dzhub-theme.css": "css/dzhub-theme.css" in html,
        "dzhub-final.css": "css/dzhub-final.css" in html,
        "brand logo svg": "dzhub-symbol.svg" in html,
        "light theme locked": "data-theme=\"light\"" in html,
    }
    for label, ok in checks.items():
        print(f"[{'OK ' if ok else 'FAIL'}] home ships {label}")
    return all(checks.values())


def run() -> None:
    client = Client()
    failures = []
    for name, path in PAGES:
        try:
            response = client.get(path)
            status = response.status_code
            ok = status in (200, 302)
            # 302 is acceptable for pages that redirect anonymous users.
        except Exception as exc:  # template errors, missing context, etc.
            status = f"EXCEPTION: {type(exc).__name__}: {exc}"
            ok = False
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {name:16s} {path:24s} -> {status}")
        if not ok:
            failures.append((name, path, status))

    if not check_dzhub_layer(client):
        failures.append(("dzhub-layer", "/", "missing from rendered home"))

    failures.extend(run_authenticated(client))

    total = len(PAGES) + len(AUTH_PAGES)
    print(f"\nSmoke test finished. Failures: {len(failures)}.")
    if failures:
        for item in failures:
            print("  FAILED:", item)
        raise SystemExit(1)


if __name__ == "__main__":
    run()
