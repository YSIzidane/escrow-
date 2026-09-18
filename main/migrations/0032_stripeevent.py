from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0031_notification_action_notification_actor_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StripeEvent",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID")),
                ("event_id", models.CharField(max_length=120, unique=True, db_index=True)),
                ("event_type", models.CharField(max_length=120)),
                ("api_version", models.CharField(max_length=40, blank=True)),
                ("processed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(null=True, blank=True)),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["event_type", "-created_at"], name="main_stripe_event_t_ca64fe_idx"),
                    models.Index(fields=["processed", "-created_at"], name="main_stripe_process_abc0e7_idx"),
                ],
            },
        ),
    ]