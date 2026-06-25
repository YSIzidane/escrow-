"""
Management command to setup Google OAuth provider in django-allauth.
Usage: 
  - Setup with credentials: python manage.py setup_google_oauth --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
  - Interactive mode: python manage.py setup_google_oauth --interactive
  - Create placeholder (for development): python manage.py setup_google_oauth --create-placeholder
"""
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp


class Command(BaseCommand):
    help = 'Setup Google OAuth provider for django-allauth'

    def add_arguments(self, parser):
        parser.add_argument('--client-id', type=str, help='Google OAuth Client ID')
        parser.add_argument('--client-secret', type=str, help='Google OAuth Client Secret')
        parser.add_argument('--interactive', action='store_true', help='Interactive mode (prompt for credentials)')
        parser.add_argument('--create-placeholder', action='store_true', help='Create placeholder app with dummy credentials')

    def handle(self, *args, **options):
        client_id = options.get('client_id')
        client_secret = options.get('client_secret')
        interactive = options.get('interactive', False)
        create_placeholder = options.get('create_placeholder', False)

        # Get current site
        site = Site.objects.get_or_create(id=1)[0]
        if site.domain == 'example.com':
            site.domain = 'localhost:8000'
            site.name = 'Local Development'
            site.save()
            self.stdout.write(f'✓ Updated site to: {site.domain}')

        # Create placeholder
        if create_placeholder:
            client_id = 'placeholder-client-id.apps.googleusercontent.com'
            client_secret = 'placeholder-secret-key'
            self.stdout.write(self.style.WARNING('⚠️  Creating placeholder Google OAuth app...'))
            self.stdout.write('This is for DEVELOPMENT ONLY. You must update credentials later!')

        # Interactive mode
        elif interactive or (not client_id or not client_secret):
            self.stdout.write(self.style.WARNING('\n📝 Google OAuth Setup Instructions:'))
            self.stdout.write('\n1. Go to Google Cloud Console: https://console.cloud.google.com/')
            self.stdout.write('2. Create a new project or select existing')
            self.stdout.write('3. Enable Google+ API')
            self.stdout.write('4. Create OAuth 2.0 credentials (Authorized JavaScript origins):')
            self.stdout.write('   - http://localhost:8000')
            self.stdout.write('   - http://127.0.0.1:8000')
            self.stdout.write('   - Your production domain')
            self.stdout.write('5. Add authorized redirect URI:')
            self.stdout.write('   - http://localhost:8000/accounts/google/login/callback/')
            self.stdout.write('   - http://127.0.0.1:8000/accounts/google/login/callback/')
            self.stdout.write('   - Your production callback URL\n')

            if not client_id:
                client_id = input('Enter your Google OAuth Client ID: ').strip()
            if not client_secret:
                client_secret = input('Enter your Google OAuth Client Secret: ').strip()

        if not client_id or not client_secret:
            self.stdout.write(self.style.ERROR('❌ Client ID and Secret are required!'))
            return

        # Create or update Google OAuth app
        try:
            google_app = SocialApp.objects.get(provider='google')
            google_app.client_id = client_id
            google_app.secret = client_secret
            google_app.save()
            self.stdout.write(self.style.SUCCESS('✓ Updated Google OAuth credentials'))
        except SocialApp.DoesNotExist:
            google_app = SocialApp.objects.create(
                name='Google',
                provider='google',
                client_id=client_id,
                secret=client_secret,
            )
            self.stdout.write(self.style.SUCCESS('✓ Created Google OAuth application'))

        # Add site to app
        if site not in google_app.sites.all():
            google_app.sites.add(site)
            google_app.save()
            self.stdout.write(f'✓ Linked to site: {site.domain}')

        self.stdout.write(self.style.SUCCESS('\n✅ Google OAuth setup completed!'))
        self.stdout.write(f'Site: {site.domain}')
        self.stdout.write(f'Provider: Google')
        self.stdout.write('\nYou can now use "Login with Google" on your login page.')
        
        if create_placeholder:
            self.stdout.write(self.style.WARNING('\n⚠️  IMPORTANT: Update credentials later with:'))
            self.stdout.write('python manage.py setup_google_oauth --client-id YOUR_REAL_ID --client-secret YOUR_REAL_SECRET')
