import shutil
from pathlib import Path
from uuid import uuid4

from django.test import TestCase, override_settings


class PublicMediaFileTests(TestCase):
    def setUp(self):
        self.temp_media_dir = Path.cwd() / ".tmp-public-media" / f"escrow-public-media-{uuid4().hex}"
        self.temp_media_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_media_dir, ignore_errors=True))

    @override_settings(DEBUG=False, USE_S3_STORAGE=False, SECURE_SSL_REDIRECT=False)
    def test_public_avatar_file_is_served(self):
        avatar_path = Path(self.temp_media_dir) / "avatars" / "demo.jpg"
        avatar_path.parent.mkdir(parents=True, exist_ok=True)
        avatar_path.write_bytes(b"fake-avatar")

        with override_settings(MEDIA_ROOT=str(self.temp_media_dir)):
            response = self.client.get("/media/avatars/demo.jpg", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(response.streaming_content), b"fake-avatar")

    @override_settings(DEBUG=False, USE_S3_STORAGE=False, SECURE_SSL_REDIRECT=False)
    def test_sensitive_media_path_is_not_public(self):
        secret_path = Path(self.temp_media_dir) / "kyc_docs" / "identity.pdf"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_bytes(b"secret-doc")

        with override_settings(MEDIA_ROOT=str(self.temp_media_dir)):
            response = self.client.get("/media/kyc_docs/identity.pdf", secure=True)

        self.assertEqual(response.status_code, 404)
