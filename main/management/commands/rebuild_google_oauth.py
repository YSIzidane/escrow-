"""
Clean up and rebuild Google OAuth app in django-allauth
"""
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp


class Command(BaseCommand):
    help = 'Clean up and rebuild Google OAuth provider'

    def add_arguments(self, parser):
        parser.add_argument('--client-id', type=str, help='Google OAuth Client ID')
        parser.add_argument('--client-secret', type=str, help='Google OAuth Client Secret')

    def handle(self, *args, **options):
        client_id = options.get('client_id', 'placeholder-client-id.apps.googleusercontent.com')
        client_secret = options.get('client_secret', 'placeholder-secret-key')

        # Get or create site
        site = Site.objects.get_or_create(id=1)[0]
        if site.domain == 'example.com':
            site.domain = 'localhost:8000'
            site.name = 'Local Development'
            site.save()

        # Delete all existing Google apps
        deleted_count = 0
        for app in SocialApp.objects.filter(provider='google'):
            self.stdout.write(f'Deleting existing Google app: {app.name} (ID: {app.id})')
            app.delete()
            deleted_count += 1

        if deleted_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✓ Deleted {deleted_count} existing Google app(s)'))

        # Create fresh Google OAuth app
        google_app = SocialApp.objects.create(
            name='Google',
            provider='google',
            client_id=client_id,
            secret=client_secret,
        )
        self.stdout.write(self.style.SUCCESS('✓ Created fresh Google OAuth application'))

        # Make sure site is linked
        google_app.sites.add(site)
        google_app.save()

        self.stdout.write(self.style.SUCCESS('\n✅ Google OAuth setup cleaned and rebuilt!'))
        self.stdout.write(f'Site: {site.domain}')
        self.stdout.write(f'Client ID: {client_id}')
        self.stdout.write(f'Provider: Google')
