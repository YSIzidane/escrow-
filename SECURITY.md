# Security Policy

SafouaneEscrow handles authentication, payments, protected deal communication, and user trust workflows. Security issues should be treated seriously and reported responsibly.

## Supported Versions

Security fixes are applied to the actively maintained codebase.

| Version | Supported |
| ------- | --------- |
| Current main branch | Yes |
| Older unpublished snapshots | No |

## Reporting a Vulnerability

If you believe you have found a security issue:

- Do not open a public GitHub issue
- Do not disclose the issue in discussions or pull requests
- Do not publish proof-of-concept exploits publicly before a fix is available

Please report the issue privately to the project maintainer or the designated security contact.

Include:

- A clear description of the issue
- The affected area or feature
- Reproduction steps
- Impact assessment
- Optional mitigation suggestions

## What Counts as a Security Issue

Examples include:

- Authentication bypass
- Authorization or privilege escalation
- Payment or escrow workflow manipulation
- Webhook signature bypass
- Exposure of private messages, invoices, KYC data, or user files
- Sensitive environment or secret leakage
- Dangerous file upload or attachment access issues

## Sensitive Data Rules

Never commit or expose:

- `.env` files
- Secret keys
- Stripe secrets
- OAuth client secrets
- Database credentials
- SMTP passwords
- Redis passwords
- Real user data
- KYC files
- Private media or internal backups

## Production Security Checklist

Before a real deployment:

- Set `DJANGO_DEBUG=False`
- Use a strong `DJANGO_SECRET_KEY`
- Configure `SITE_URL`
- Set `DJANGO_ALLOWED_HOSTS`
- Set `DJANGO_CSRF_TRUSTED_ORIGINS`
- Enable secure cookies
- Enforce HTTPS
- Configure Redis and background workers
- Use real Stripe credentials
- Protect webhook endpoints with real secrets
- Configure email delivery safely
- Rotate any exposed secrets immediately

## Staging and Public Testing

If you share the project through a temporary tunnel such as `ngrok`:

- Use a dedicated staging environment
- Avoid exposing real payment credentials
- Keep withdrawals disabled unless explicitly required
- Use test users and test payment keys
- Recheck `SITE_URL`, allowed hosts, and CSRF origins whenever the public URL changes

## Response Expectations

Reported issues should be:

- Acknowledged as quickly as possible
- Investigated before public discussion
- Fixed with minimal disclosure until a patch is ready

## Responsible Disclosure

We appreciate coordinated disclosure and practical reports that help improve the platform without exposing users or operators to unnecessary risk.
