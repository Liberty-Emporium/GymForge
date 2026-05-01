from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='GymConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gym_name', models.CharField(max_length=200)),
                ('slug', models.SlugField(help_text='URL-safe gym identifier', max_length=100, unique=True)),
                ('owner_email', models.EmailField(max_length=254)),
                ('subscription_status', models.CharField(
                    choices=[
                        ('trial', 'Trial'),
                        ('active', 'Active'),
                        ('suspended', 'Suspended'),
                        ('cancelled', 'Cancelled'),
                    ],
                    db_index=True,
                    default='trial',
                    max_length=20,
                )),
                ('trial_start_date', models.DateTimeField(auto_now_add=True)),
                ('trial_active', models.BooleanField(default=True)),
                ('member_app_active', models.BooleanField(default=False)),
                ('stripe_customer_id', models.CharField(blank=True, max_length=100)),
                ('stripe_subscription_id', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Gym Config',
                'verbose_name_plural': 'Gym Config',
            },
        ),
    ]
