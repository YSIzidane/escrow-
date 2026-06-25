from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0020_alter_profile_kyc_document"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("approved", "Approved payment"),
                    ("rejected", "Rejected payment"),
                    ("released", "Released funds"),
                    ("refunded", "Refunded payment"),
                ],
                max_length=20,
            ),
        ),
    ]
