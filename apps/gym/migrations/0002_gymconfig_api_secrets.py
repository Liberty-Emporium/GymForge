from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gymconfig',
            name='api_secrets',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Owner-managed API keys and secrets. Stored encrypted at rest.',
            ),
        ),
    ]
