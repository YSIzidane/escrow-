from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.test import RequestFactory, SimpleTestCase, override_settings

from main.middleware import Custom404Middleware


class FriendlyErrorPagesTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_unknown_route_uses_custom_404_page_in_debug(self):
        response = self.client.get("/c5")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

    @override_settings(DEBUG=True)
    def test_browser_500_exception_uses_custom_template_in_debug(self):
        factory = RequestFactory()

        def boom(_request):
            raise ValueError("boom")

        middleware = Custom404Middleware(boom)
        response = middleware(factory.get("/broken", HTTP_ACCEPT="text/html"))

        self.assertEqual(response.status_code, 500)
        self.assertIn(b"500", response.content)

    @override_settings(DEBUG=True)
    def test_browser_403_response_uses_custom_template_in_debug(self):
        factory = RequestFactory()
        middleware = Custom404Middleware(lambda _request: HttpResponseForbidden("forbidden"))

        response = middleware(factory.get("/forbidden", HTTP_ACCEPT="text/html"))

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"403", response.content)

    @override_settings(DEBUG=True)
    def test_browser_503_response_uses_maintenance_template_in_debug(self):
        factory = RequestFactory()
        middleware = Custom404Middleware(lambda _request: HttpResponse("maintenance", status=503))

        response = middleware(factory.get("/maintenance", HTTP_ACCEPT="text/html"))

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"503", response.content)

    @override_settings(DEBUG=True)
    def test_json_requests_keep_original_404_response(self):
        factory = RequestFactory()
        middleware = Custom404Middleware(lambda _request: HttpResponseNotFound("api missing"))

        response = middleware(factory.get("/api/missing", HTTP_ACCEPT="application/json"))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"api missing")
