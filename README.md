<div align="center">
  <img src="./static/images/brand/logo-primary.svg" alt="SafouaneEscrow" width="144" />

  <h1>SafouaneEscrow</h1>
  <p><strong>Escrow-first marketplace infrastructure for protected digital transactions.</strong></p>

  <p>
    <img src="https://readme-typing-svg.demolab.com?font=Inter&weight=600&size=18&pause=1400&color=C9963B&center=true&vCenter=true&width=920&lines=Protected+checkout+for+buyers+and+sellers;Real-time+deal+rooms%2C+chat%2C+notifications%2C+and+admin+review;Built+with+Django%2C+Channels%2C+PostgreSQL%2C+Redis%2C+Celery%2C+and+Stripe" alt="Project intro animation" />
  </p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Django-4.2+-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django" />
    <img src="https://img.shields.io/badge/Channels-Realtime-FF6F00?style=for-the-badge" alt="Channels" />
    <img src="https://img.shields.io/badge/PostgreSQL-Production-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
    <img src="https://img.shields.io/badge/Redis-Realtime%20%26%20Queues-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
    <img src="https://img.shields.io/badge/Stripe-Escrow%20Flow-635BFF?style=for-the-badge&logo=stripe&logoColor=white" alt="Stripe" />
  </p>
</div>

<p align="center">
  <img src="./static/images/new_logo.jpg" alt="SafouaneEscrow cover" width="100%" />
</p>

<table>
  <tr>
    <td align="center" width="25%">
      <strong>Protected Payments</strong><br />
      Checkout, hold, release, and refund logic
    </td>
    <td align="center" width="25%">
      <strong>Realtime Operations</strong><br />
      Rooms, chat, notifications, and activity flow
    </td>
    <td align="center" width="25%">
      <strong>Trust Layer</strong><br />
      KYC-aware workflows, moderation, and support
    </td>
    <td align="center" width="25%">
      <strong>Deployment Ready</strong><br />
      Health checks, Docker stack, staging, and tests
    </td>
  </tr>
</table>

## Product Vision

SafouaneEscrow is a Django-based marketplace built around one core principle: a transaction should remain structured, traceable, and protected from the moment a buyer commits payment until the deal is successfully completed or safely refunded.

Instead of treating escrow as an add-on, the platform places it at the center of the product experience. Listings, rooms, support, notifications, moderation, invoices, and payment state changes are all connected to the transaction lifecycle.

## End-to-End Flow

1. A seller creates a listing or starts a deal.
2. A buyer initiates payment through the platform.
3. The amount is held in escrow rather than released immediately.
4. Both sides continue inside the protected deal room.
5. The transaction concludes through release, refund, or staff review.

## Feature System

### Transaction Core

- Escrow payment lifecycle with hold, release, and refund states
- Fixed-price listings and auction listings
- Invoice visibility and payment audit continuity
- Dedicated success and checkout flows for buyer confidence

### Collaboration Layer

- Real-time escrow rooms
- Private chat and message attachments
- Notification polling and room activity updates
- Structured communication tied directly to the transaction

### Trust and Moderation

- KYC-aware verification states
- Support ticket system and staff review workflows
- Moderation paths for withdrawals, rooms, and user actions
- Protected staff surfaces with access controls

### Operational Readiness

- Docker and production-style compose stack
- Health endpoint for uptime and orchestration checks
- Deployment checklist and env templates
- Full test suite covering core business flows

## Visual Preview

<table>
  <tr>
    <td width="33%">
      <img src="./static/images/login.jpg" alt="Authentication flow" width="100%" />
      <p align="center"><strong>Authentication Flow</strong></p>
    </td>
    <td width="33%">
      <img src="./static/images/about.jpg" alt="Trust and product layer" width="100%" />
      <p align="center"><strong>Trust and Product Layer</strong></p>
    </td>
    <td width="33%">
      <img src="./static/images/back.jpg" alt="Marketplace experience" width="100%" />
      <p align="center"><strong>Marketplace Experience</strong></p>
    </td>
  </tr>
</table>

## Architecture Snapshot

### Core Stack

- Python 3
- Django 4.2+
- Django Channels
- Celery

### Data and Infrastructure

- PostgreSQL
- Redis
- Docker and Docker Compose

### Integrations

- Stripe
- Google OAuth via `django-allauth`
- SMTP email delivery

## Service Map

```mermaid
flowchart LR
    U[Users] --> W[Web App]
    W --> D[(PostgreSQL)]
    W --> R[(Redis)]
    W --> S[Stripe]
    W --> M[SMTP]
    W --> C[Celery Worker]
    W --> B[Celery Beat]
    C --> D
    C --> R
    B --> R
    S --> WH[Webhook Endpoint]
    WH --> W
```

## Repository Layout

```text
core/                    Django settings and project configuration
main/                    Main application: views, models, tests, services
templates/               HTML templates
static/                  CSS, JavaScript, and image assets
docker/                  Entrypoint and healthcheck helpers
.env.example             Local development template
.env.production.example  Production environment template
DEPLOYMENT_CHECKLIST.md  Launch and deployment checklist
```

## Quick Start

### Requirements

- Python 3.9+
- PostgreSQL
- Redis
- Virtual environment support

### Local Setup

1. Clone the repository

```bash
git clone https://github.com/your-username/escrow_project.git
cd escrow_project
```

2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Create the environment file

```bash
cp .env.example .env
```

5. Run database setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

6. Start the app

```bash
python manage.py runserver
```

Local HTTPS for preview:

```powershell
.\run_dev.ps1 -Https
```

Then open `https://localhost:8000/`. The generated certificate is for local development only, so the browser may ask you to accept it the first time.

If port `8000` is still used by an old HTTP server, replace it with:

```powershell
.\run_dev.ps1 -Https -ReplacePort
```

## Docker

Containerized local stack:

```bash
docker compose up --build
```

Production-style stack:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.prod.yml up --build -d
```

## Configuration

Important environment variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `SITE_URL`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` or `DB_*`
- `REDIS_URL` or `REDIS_HOST` / `REDIS_PORT`
- `STRIPE_PUBLIC_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`

Reference files:

- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- [.env.example](.env.example)
- [.env.production.example](.env.production.example)

## Health and Readiness

Built-in health endpoints:

- `/health/`
- `/health/?format=text`

These are suitable for local verification, staging uptime checks, and container health probes.

## Payments and Escrow

The current payment lifecycle is:

1. A checkout is created for a deal.
2. A successful payment moves the deal into escrow.
3. The escrow room becomes active.
4. The platform resolves the deal through release or refund logic.
5. Invoice and audit details remain available in the system.

For local Stripe webhook testing:

```bash
stripe listen --forward-to http://127.0.0.1:8000/stripe/webhook/
```

## Testing

Core verification:

```bash
python manage.py check
python manage.py test --keepdb
```

Deployment-oriented verification:

```bash
python manage.py check --deploy
```

## Deployment Notes

For staging or production, ensure:

- `DJANGO_DEBUG=False`
- PostgreSQL is available
- Redis is available
- Celery worker and beat are running
- Stripe webhook configuration matches `SITE_URL`
- Email delivery is configured
- Secret values are real and not placeholders

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)

## License

This project is distributed under the MIT License.

See [LICENSE](LICENSE) for full details.
