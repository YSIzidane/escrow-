from django.test import TestCase
from django.urls import reverse


class SecurityHeadersTests(TestCase):
    def test_home_page_includes_security_headers(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(
            response["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )
        self.assertEqual(
            response["Cross-Origin-Opener-Policy"],
            "same-origin",
        )
        self.assertEqual(
            response["Cross-Origin-Resource-Policy"],
            "same-origin",
        )
        self.assertIn("camera=()", response["Permissions-Policy"])
        self.assertIn("microphone=()", response["Permissions-Policy"])
