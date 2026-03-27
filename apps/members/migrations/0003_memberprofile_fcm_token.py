from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0002_add_pin_hash_to_member_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='memberprofile',
            name='fcm_token',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
