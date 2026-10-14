# Contributing to DZHub (دزاير هب) / دليل المساهمة

شكراً لاهتمامك بالمساهمة في مشروع **DZHub**! هذا المشروع مفتوح المصدر وقيد التطوير النشط، ونرحب بكل المطورين بمختلف مستويات خبرتهم.

Thank you for your interest in contributing to **DZHub**! This project is open-source, actively maintained, and welcomes contributions from developers worldwide.

> 🔒 **Notice:** Because this project handles payments, escrow, user trust, and protected transactions, contributions must prioritize security, clarity, and safety.

## Principles

When contributing, prioritize:

- Correctness over cleverness
- Readable code over dense code
- Safe defaults over risky shortcuts
- Production readiness over temporary convenience
- Consistent UI behavior across desktop and mobile

## Ways to Contribute

You can contribute by:

- Reporting bugs
- Suggesting improvements
- Improving documentation
- Submitting bug fixes
- Refining UX and frontend polish
- Expanding tests and deployment tooling

## Reporting Bugs

When opening a bug report, include:

- A short and clear title
- What you expected to happen
- What actually happened
- Exact reproduction steps
- Screenshots or recordings when relevant
- Browser, OS, and environment details

If the bug involves payments, authentication, permissions, or data access, include as much context as possible.

## Suggesting Features

When proposing a feature, explain:

- The problem it solves
- The intended user impact
- Any technical or security tradeoffs
- Whether it affects payments, moderation, or authentication

## Pull Request Guidelines

Before opening a pull request:

1. Create a focused branch.
2. Keep the scope small and reviewable.
3. Update tests when behavior changes.
4. Update documentation when configuration or usage changes.
5. Make sure the app still passes core checks.

Recommended commands:

```bash
python manage.py check
python manage.py test --keepdb
```

If your change affects deployment or environment configuration, also review:

```bash
python manage.py check --deploy
```

## Code Standards

- Do not commit secrets, tokens, `.env` files, or private credentials.
- Do not commit generated local databases or user-uploaded media.
- Prefer small, atomic commits with clear messages.
- Avoid unrelated refactors in the same pull request.
- Preserve backwards compatibility unless the change is intentional and documented.

## Frontend Expectations

For UI changes:

- Keep layouts responsive
- Avoid horizontal overflow
- Preserve the project visual identity
- Favor clean spacing, strong contrast, and clear call-to-action hierarchy
- Test important flows on mobile-sized screens

## Sensitive Areas

Extra care is required for changes touching:

- Payments and escrow logic
- Webhooks
- Refund and release flows
- Authentication and OAuth
- Permissions and staff tooling
- KYC, invoices, and private user data

## Security Reporting

Please do not open public issues for security vulnerabilities.

Use the instructions in [SECURITY.md](SECURITY.md) instead.

## Documentation

If you change setup, deployment, or operational behavior, update the relevant file:

- `README.md`
- `DEPLOYMENT_CHECKLIST.md`
- `.env.example`
- `.env.production.example`

## License

By contributing to this repository, you agree that your contributions will be licensed under the MIT License used by this project.
