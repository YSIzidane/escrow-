# Deployment Checklist

Use this checklist before publishing `SafouaneEscrow` to a real server.

## 1. Required Environment Variables

Set these first:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `SITE_URL`
- `DB_ENGINE=postgres` or `DATABASE_URL`
- `REDIS_URL` or `REDIS_HOST` + related Redis variables
- `STRIPE_PUBLIC_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

## 2. Security Values

For production, make sure these are enabled:

- `DJANGO_SESSION_COOKIE_SECURE=True`
- `DJANGO_CSRF_COOKIE_SECURE=True`
- `DJANGO_SECURE_SSL_REDIRECT=True`
- `DJANGO_SECURE_HSTS_SECONDS=31536000`
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- `DJANGO_SECURE_HSTS_PRELOAD=True`

## 3. Services You Must Run

The codebase is ready, but these external services must exist:

- PostgreSQL
- Redis
- Daphne or another ASGI server
- Celery worker
- Celery beat
- Celery beat schedules must include auction closing and deal deadline processing
- Stripe webhook forwarding in development, or a real webhook endpoint in production
- SMTP provider for password reset and verification emails

## 4. Stripe Activation

Before real payments:

- Replace all Stripe test keys with live keys
- Set the live webhook secret
- Confirm the Stripe success/cancel URLs match `SITE_URL`
- Test checkout, refund, and webhook flow end to end
- Test CCP proof upload, admin approval, rejection, retry limit, and refund flow end to end

## 5. Google OAuth Activation

If you want Google login:

- Create Google OAuth credentials
- Add the correct redirect URL:
  - `/accounts/google/login/callback/`
- Make sure the Site domain in Django matches the real domain
- Run:
  - `python manage.py setup_google_oauth --interactive`

## 6. Optional Features

Enable only if you are ready:

- `WITHDRAWAL_ENABLED=True`
  - Only after you decide the real payout workflow
- `USE_S3_STORAGE=True`
  - Only after S3-compatible media storage is configured
- `DB_USE_POOL=True`
  - Only when PostgreSQL pooling is desired and available

## 7. Final Verification Commands

Run these before launch:

```bash
python manage.py check --deploy
python manage.py test --keepdb
python manage.py collectstatic --noinput
python manage.py migrate
```

## 8. Health Endpoint

Use this endpoint for uptime and container checks:

- `/health/`
- `/health/?format=text`
