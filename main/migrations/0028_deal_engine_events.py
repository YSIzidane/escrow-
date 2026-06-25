from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0027_tradeexchange"),
    ]

    operations = [
        migrations.CreateModel(
            name="DealEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("from_state", models.CharField(blank=True, max_length=32)),
                ("to_state", models.CharField(blank=True, max_length=32)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deal_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="main.deal",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="DealTransitionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("command", models.CharField(max_length=80)),
                ("from_state", models.CharField(blank=True, max_length=32)),
                ("to_state", models.CharField(blank=True, max_length=32)),
                ("allowed", models.BooleanField(default=False)),
                ("reason", models.CharField(blank=True, max_length=160)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deal_transition_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transition_logs",
                        to="main.deal",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="dealevent",
            index=models.Index(fields=["deal", "created_at"], name="main_dealev_deal_id_2b299d_idx"),
        ),
        migrations.AddIndex(
            model_name="dealevent",
            index=models.Index(fields=["event_type", "created_at"], name="main_dealev_event_t_ec32f9_idx"),
        ),
        migrations.AddIndex(
            model_name="dealevent",
            index=models.Index(fields=["actor", "created_at"], name="main_dealev_actor_i_4032fe_idx"),
        ),
        migrations.AddIndex(
            model_name="dealtransitionlog",
            index=models.Index(fields=["deal", "-created_at"], name="main_dealtr_deal_id_be3f41_idx"),
        ),
        migrations.AddIndex(
            model_name="dealtransitionlog",
            index=models.Index(fields=["command", "allowed"], name="main_dealtr_command_392259_idx"),
        ),
        migrations.AddIndex(
            model_name="dealtransitionlog",
            index=models.Index(fields=["actor", "-created_at"], name="main_dealtr_actor_i_8c582a_idx"),
        ),
    ]
