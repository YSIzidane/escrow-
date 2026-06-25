from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0013_profile_is_verified_profile_kyc_document_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deal",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "جديدة"),
                    ("expired", "منتهية"),
                    ("reserved", "محجوزة"),
                    ("shipped", "قيد الشحن"),
                    ("delivered", "تم الاستلام"),
                    ("completed", "مكتملة"),
                    ("disputed", "نزاع"),
                    ("cancelled", "ملغاة"),
                ],
                default="new",
                max_length=20,
            ),
        ),
    ]
