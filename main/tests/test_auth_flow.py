from types import SimpleNamespace

from django import forms
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.forms import SimpleSocialSignupForm
from allauth.socialaccount.models import SocialAccount


class AuthFlowTests(TestCase):
    def test_legacy_login_redirect_preserves_next(self):
        response = self.client.get(reverse("login"), {"next": "/pay/12/"})

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next=/pay/12/",
            fetch_redirect_response=False,
        )

    def test_account_login_page_shows_return_notice_and_signup_link(self):
        response = self.client.get(reverse("account_login"), {"next": "/pay/12/"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بعد تسجيل الدخول")
        self.assertContains(response, "إكمال الدفع")
        self.assertContains(response, f"{reverse('account_signup')}?next=/pay/12/")

    def test_social_signup_form_hides_provider_email(self):
        sociallogin = SimpleNamespace(
            user=User(email="google@example.com", username=""),
            email_addresses=[],
        )

        form = SimpleSocialSignupForm(sociallogin=sociallogin)

        self.assertIsInstance(form.fields["email"].widget, forms.HiddenInput)
        self.assertEqual(form.initial["email"], "google@example.com")

    def test_social_signup_form_ignores_tampered_hidden_email(self):
        sociallogin = SimpleNamespace(
            user=User(email="google@example.com", username=""),
            email_addresses=[],
            provider=SimpleNamespace(name="Google"),
        )

        form = SimpleSocialSignupForm(
            data={"username": "googleuser", "email": "attacker@example.com"},
            sociallogin=sociallogin,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "google@example.com")

    def test_profile_for_google_only_account_shows_set_password_link(self):
        user = User.objects.create_user(
            username="googleuser",
            email="google@example.com",
            password="TempPassword123!",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        self.client.force_login(user)
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_set_password"))
        self.assertNotContains(response, 'name="change_password"', html=False)

    def test_profile_password_post_for_google_only_account_redirects_to_set_password(self):
        user = User.objects.create_user(
            username="googleuser2",
            email="google2@example.com",
            password="TempPassword123!",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        self.client.force_login(user)
        response = self.client.post(
            reverse("profile"),
            {
                "change_password": "1",
                "old_password": "whatever",
                "new_password1": "NewPassword123!",
                "new_password2": "NewPassword123!",
            },
        )

        self.assertRedirects(response, reverse("account_set_password"))

    def test_connections_page_blocks_disconnect_for_google_only_account_without_local_password(self):
        user = User.objects.create_user(
            username="socialonly",
            email="socialonly@example.com",
            password="TempPassword123!",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-socialonly",
            extra_data={"email": user.email, "name": "Social Only"},
        )

        self.client.force_login(user)
        response = self.client.get(reverse("socialaccount_connections"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_set_password"))
        self.assertContains(response, 'class="btn btn-danger w-100 connections-remove"')
        self.assertContains(response, 'disabled title=')

    def test_connections_page_allows_disconnect_when_local_password_exists(self):
        user = User.objects.create_user(
            username="socialbackup",
            email="socialbackup@example.com",
            password="TempPassword123!",
        )
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-socialbackup",
            extra_data={"email": user.email, "name": "Social Backup"},
        )

        self.client.force_login(user)
        response = self.client.get(reverse("socialaccount_connections"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("profile"))
        self.assertNotContains(response, 'connections-remove" disabled', html=False)
