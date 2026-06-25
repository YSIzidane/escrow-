from django.db import migrations, models
import main.models.user


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0019_withdrawalrequest_audit_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="kyc_document",
            field=models.FileField(
                blank=True,
                help_text="مستند التوثيق (صورة أو PDF)",
                null=True,
                upload_to=main.models.user.kyc_upload_path,
                validators=[main.models.user.validate_kyc_file],
            ),
        ),
    ]
