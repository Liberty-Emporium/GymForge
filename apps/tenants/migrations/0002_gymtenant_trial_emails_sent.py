from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gymtenant',
            name='trial_emails_sent',
            field=models.JSONField(default=list),
        ),
    ]
