"""
Retention Celery tasks — Step 44 GymForge v2.

send_reengagement_message  — push + email helper for inactive members.
check_member_retention     — daily 09:00 UTC; 14/30-day inactivity alerts.
send_birthday_messages     — daily 08:00 UTC; birthday loyalty points + messages.
process_trial_statuses     — daily 00:00 UTC; trial nudge emails + day-14 suspension.

Import note: models imported at module level (rather than deferred inside functions)
so that test patches via patch('apps.members.tasks.X') resolve correctly. This
follows the same pattern established in apps/billing/tasks.py.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django_tenants.utils import schema_context
from pyfcm import FCMNotification

from apps.ai_coach.models import MemberAIAlert
from apps.loyalty.utils import award_loyalty_points
from apps.members.models import MemberProfile
from apps.tenants.models import GymTenant

logger = logging.getLogger(__name__)


def send_reengagement_message(member, days_inactive):
    """Send push notification + email to a member who has been inactive."""
    message = (
        f"Hi {member.user.first_name}, we miss you! It's been {days_inactive} days "
        f"since your last visit. Come back and keep up your progress!"
    )
    try:
        if member.fcm_token:
            push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
            push_service.notify_single_device(
                registration_id=member.fcm_token,
                message_title='We miss you!',
                message_body=message,
            )
    except Exception:
        logger.exception('Push notification failed for member %s', member.pk)
    try:
        send_mail(
            subject='We miss you at the gym!',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member.user.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception('Re-engagement email failed for member %s', member.pk)


@shared_task
def check_member_retention():
    """Scan all active tenants for inactive members; send re-engagement messages."""
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(subscription_status__in=['trial', 'active']):
        try:
            with schema_context(tenant.schema_name):
                members = (
                    MemberProfile.objects
                    .filter(memberships__status='active')
                    .select_related('user')
                    .distinct()
                )
                for member in members:
                    try:
                        last_checkin = member.checkins.order_by('-checked_in_at').first()
                        last_activity = (
                            last_checkin.checked_in_at.date()
                            if last_checkin
                            else member.join_date
                        )
                        days_inactive = (today - last_activity).days
                        if days_inactive >= 30:
                            MemberAIAlert.objects.get_or_create(
                                member=member,
                                alert_type='inactivity',
                                is_resolved=False,
                                defaults={
                                    'message': f'Member inactive for {days_inactive} days.'
                                },
                            )
                            send_reengagement_message(member, days_inactive)
                        elif days_inactive >= 14:
                            send_reengagement_message(member, days_inactive)
                    except Exception:
                        logger.exception(
                            'check_member_retention failed for member %s', member.pk
                        )
        except Exception:
            logger.exception(
                'check_member_retention failed for tenant %s', tenant.schema_name
            )


@shared_task
def send_birthday_messages():
    """Award birthday loyalty points and send push + email to members with today's birthday."""
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(subscription_status__in=['trial', 'active']):
        try:
            with schema_context(tenant.schema_name):
                members = (
                    MemberProfile.objects
                    .filter(
                        date_of_birth__month=today.month,
                        date_of_birth__day=today.day,
                    )
                    .select_related('user')
                )
                for member in members:
                    try:
                        points = award_loyalty_points(
                            member, 'birthday', description='Happy Birthday!'
                        )
                        try:
                            if member.fcm_token:
                                push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
                                push_service.notify_single_device(
                                    registration_id=member.fcm_token,
                                    message_title='Happy Birthday! 🎂',
                                    message_body=(
                                        f'Happy Birthday {member.user.first_name}! '
                                        f'Enjoy your {points} bonus loyalty points.'
                                    ),
                                )
                        except Exception:
                            logger.exception(
                                'Birthday push notification failed for member %s', member.pk
                            )
                        send_mail(
                            subject=f'Happy Birthday from {tenant.gym_name}!',
                            message=(
                                f'Happy Birthday {member.user.first_name}! '
                                f'We have awarded you {points} bonus loyalty points. '
                                f'See you at the gym!'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[member.user.email],
                            fail_silently=True,
                        )
                    except Exception:
                        logger.exception(
                            'Birthday message failed for member %s', member.pk
                        )
        except Exception:
            logger.exception(
                'send_birthday_messages failed for tenant %s', tenant.schema_name
            )


def _send_trial_email(tenant, template_key):
    """Send a trial lifecycle email to the gym owner. Called only by process_trial_statuses."""
    subjects = {
        'day0': 'Welcome to GymForge! Your trial starts now.',
        'day3': "How's your first week going?",
        'day7': "7 days in — here's what's working",
        'day10': '4 days left on your trial',
        'day13': 'Tomorrow is your last trial day',
        'day14_ended': 'Your GymForge trial has ended',
    }
    bodies = {
        'day0': (
            f'Welcome to GymForge, {tenant.gym_name}!\n\n'
            'Your 14-day free trial has started. Key features to explore:\n'
            '- Member check-in and RFID management\n'
            '- Class scheduling and booking\n'
            '- Loyalty points and rewards\n'
            '- AI coach for member wellness\n\n'
            'Get started at your GymForge dashboard.'
        ),
        'day3': (
            f'Hi {tenant.gym_name},\n\n'
            "You're 3 days into your trial. Tips to get the most from it:\n"
            '- Add your first members and run a check-in\n'
            '- Set up a class schedule\n'
            '- Configure your membership tiers\n\n'
            'Reply to this email if you have questions.'
        ),
        'day7': (
            f'Hi {tenant.gym_name},\n\n'
            "You're halfway through your GymForge trial. Here's what's working:\n\n"
            '- Automated check-in saves 30 minutes of admin per day\n'
            '- Members love the class booking system\n'
            '- Loyalty points increase visit frequency by 20%\n\n'
            'Subscribe anytime from your dashboard.'
        ),
        'day10': (
            f'Hi {tenant.gym_name},\n\n'
            'You have 4 days left on your GymForge trial.\n\n'
            'Subscribe before your trial ends to keep all your data and continue '
            'serving your members without interruption.'
        ),
        'day13': (
            f'Hi {tenant.gym_name},\n\n'
            'Tomorrow is your last trial day.\n\n'
            'Subscribe today to keep your gym running without interruption. '
            'Your members, data, and settings are all ready to go.'
        ),
        'day14_ended': (
            f'Hi {tenant.gym_name},\n\n'
            'Your GymForge trial has ended and your account is now suspended.\n\n'
            'Subscribe to restore access. Your data is safe and will be '
            'retained for 30 days.\n\n'
            "What you'll lose access to until you subscribe:\n"
            '- Member check-in\n'
            '- Class scheduling\n'
            '- Loyalty points\n'
            '- AI coach\n\n'
            'Subscribe now to restore access immediately.'
        ),
    }
    send_mail(
        subject=subjects[template_key],
        message=bodies[template_key],
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[tenant.owner_email],
        fail_silently=True,
    )


@shared_task
def process_trial_statuses():
    """
    Run daily at midnight UTC. Sends trial nudge emails at days 0/3/7/10/13;
    suspends tenant at day 14. Operates in the public schema — no schema_context loop.
    """
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(trial_active=True):
        try:
            elapsed = (today - tenant.trial_start_date.date()).days
            if elapsed >= 14:
                tenant.trial_active = False
                tenant.subscription_status = 'suspended'
                if 14 not in tenant.trial_emails_sent:
                    _send_trial_email(tenant, 'day14_ended')
                    tenant.trial_emails_sent = tenant.trial_emails_sent + [14]
                # Always save — re-asserts suspended status defensively.
                # After this save, trial_active=False means the queryset filter
                # (trial_active=True) excludes this tenant on subsequent runs.
                tenant.save(
                    update_fields=['trial_active', 'subscription_status', 'trial_emails_sent']
                )
            elif elapsed in {0, 3, 7, 10, 13} and elapsed not in tenant.trial_emails_sent:
                _send_trial_email(tenant, f'day{elapsed}')
                tenant.trial_emails_sent = tenant.trial_emails_sent + [elapsed]
                tenant.save(update_fields=['trial_emails_sent'])
        except Exception:
            logger.exception(
                'process_trial_statuses failed for tenant %s', tenant.schema_name
            )
