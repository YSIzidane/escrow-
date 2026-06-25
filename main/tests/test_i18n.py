from django.test import TestCase
from django.urls import reverse


class SiteLanguageTests(TestCase):
    def test_signup_page_shows_arabic_password_help_text_by_default(self):
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.LANGUAGE_CODE, "ar")
        self.assertContains(
            response,
            "لا يمكن لكلمة المرور أن تكون مشابهة للمعلومات الشخصية الأخرى.",
        )
        self.assertContains(
            response,
            "كلمة المرور الخاصة بك يجب أن تتضمن 8 حروف على الأقل.",
        )
        self.assertContains(
            response,
            "لا يمكن أن تكون كلمة المرور شائعة الاستخدام.",
        )
        self.assertContains(
            response,
            "لا يمكن أن تكون كلمة المرور مكونة من أرقام فقط.",
        )

    def test_signup_page_uses_cookie_language_for_django_translations(self):
        self.client.cookies["site_language"] = "en"

        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.LANGUAGE_CODE, "en")
        self.assertContains(
            response,
            "Your password can’t be too similar to your other personal information.",
        )
        self.assertContains(
            response,
            "Your password must contain at least 8 characters.",
        )

    def test_signup_validation_errors_render_in_arabic(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "arabic@example.com",
                "username": "arabic-user",
                "password1": "12345678",
                "password2": "12345678",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "لا يمكن أن تكون كلمة المرور مكونة من أرقام فقط.",
        )
