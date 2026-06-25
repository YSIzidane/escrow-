from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from core.settings import validate_production_runtime


class ProductionSettingsValidationTests(SimpleTestCase):
    def production_kwargs(self, **overrides):
        kwargs = {
            "debug": False,
            "database_config": {"ENGINE": "django.db.backends.postgresql"},
            "redis_url": "redis://localhost:6379/0",
            "celery_broker_url": "redis://localhost:6379/0",
            "site_url": "https://example.com",
            "stripe_public_key": "pk_live_123",
            "stripe_secret_key": "sk_live_123",
            "stripe_webhook_secret": "whsec_live_123",
            "allow_test_payment_keys_in_production": False,
            "withdrawal_enabled": False,
            "allow_manual_withdrawals_in_production": False,
        }
        kwargs.update(overrides)
        return kwargs

    def test_accepts_complete_safe_production_config(self):
        validate_production_runtime(**self.production_kwargs())

    def test_rejects_sqlite_in_production(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SQLite"):
            validate_production_runtime(
                **self.production_kwargs(database_config={"ENGINE": "django.db.backends.sqlite3"})
            )

    def test_rejects_missing_redis_in_production(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "REDIS_URL or REDIS_HOST"):
            validate_production_runtime(**self.production_kwargs(redis_url=""))

    def test_rejects_missing_celery_broker_in_production(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "CELERY_BROKER_URL or REDIS_URL"):
            validate_production_runtime(**self.production_kwargs(celery_broker_url=""))

    def test_rejects_missing_site_url_in_production(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SITE_URL"):
            validate_production_runtime(**self.production_kwargs(site_url=""))

    def test_rejects_incomplete_stripe_configuration(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "STRIPE_PUBLIC_KEY, STRIPE_SECRET_KEY, and STRIPE_WEBHOOK_SECRET"):
            validate_production_runtime(
                **self.production_kwargs(stripe_webhook_secret="")
            )

    def test_rejects_stripe_placeholders_in_production(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "Stripe placeholder"):
            validate_production_runtime(
                **self.production_kwargs(
                    stripe_public_key="pk_test_...",
                    stripe_secret_key="sk_test_...",
                    stripe_webhook_secret="whsec_...",
                )
            )

    def test_rejects_manual_withdrawals_without_explicit_override(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "ALLOW_MANUAL_WITHDRAWALS_IN_PRODUCTION"):
            validate_production_runtime(
                **self.production_kwargs(withdrawal_enabled=True)
            )

    def test_allows_manual_withdrawals_with_explicit_override(self):
        validate_production_runtime(
            **self.production_kwargs(
                withdrawal_enabled=True,
                allow_manual_withdrawals_in_production=True,
            )
        )
