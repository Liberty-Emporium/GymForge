"""
Member Celery tasks — single-tenant version.
No tenant loop, no schema_context. Operates directly on the one database.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from pyfcm import FCMNotification

from apps.ai_coach.models import MemberAIAlert
from apps.loyalty.utils import award_loyalty_points
from apps.members.models import MemberProfile

logger = logging.getLogger(__name__)


def send_reengagement_message(member, days_inactive):
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
    """Daily: scan for inactive members and send re-engagement messages."""
    today = timezone.now().date()
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
                last_checkin.checked_in_at.date() if last_checkin else member.join_date
            )
            days_inactive = (today - last_activity).days
            if days_inactive >= 30:
                MemberAIAlert.objects.get_or_create(
                    member=member, alert_type='inactivity', is_resolved=False,
                    defaults={'message': f'Member inactive for {days_inactive} days.'},
                )
                send_reengagement_message(member, days_inactive)
            elif days_inactive >= 14:
                send_reengagement_message(member, days_inactive)
        except Exception:
            logger.exception('check_member_retention failed for member %s', member.pk)


@shared_task
def send_birthday_messages():
    """Daily: award birthday points and notify members whose birthday is today."""
    from apps.gym.models import GymConfig
    today = timezone.now().date()
    gym = GymConfig.get()
    gym_name = gym.gym_name if gym else 'Your Gym'

    members = (
        MemberProfile.objects
        .filter(date_of_birth__month=today.month, date_of_birth__day=today.day)
        .select_related('user')
    )
    for member in members:
        try:
            points = award_loyalty_points(member, 'birthday', description='Happy Birthday!')
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
                logger.exception('Birthday push failed for member %s', member.pk)
            send_mail(
                subject=f'Happy Birthday from {gym_name}!',
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
            logger.exception('Birthday message failed for member %s', member.pk)


@shared_task
def process_trial_statuses():
    """Daily: send trial nudge emails and suspend at day 14."""
    from apps.gym.models import GymConfig
    gym = GymConfig.get()
    if not gym or not gym.trial_active:
        return

    today = timezone.now().date()
    elapsed = (today - gym.trial_start_date.date()).days

    emails_sent = getattr(gym, 'trial_emails_sent', []) or []

    if elapsed >= 14:
        gym.trial_active = False
        gym.subscription_status = 'suspended'
        if 14 not in emails_sent:
            _send_trial_email(gym, 'day14_ended')
            emails_sent = emails_sent + [14]
        gym.save()
    elif elapsed in {0, 3, 7, 10, 13} and elapsed not in emails_sent:
        _send_trial_email(gym, f'day{elapsed}')
        emails_sent = emails_sent + [elapsed]
        gym.save()


def _send_trial_email(gym, template_key):
    subjects = {
        'day0':      'Welcome! Your trial starts now.',
        'day3':      "How's your first week going?",
        'day7':      "7 days in — here's what's working",
        'day10':     '4 days left on your trial',
        'day13':     'Tomorrow is your last trial day',
        'day14_ended': 'Your trial has ended',
    }
    bodies = {
        'day0': (
            f'Welcome to GymForge, {gym.gym_name}!\n\n'
            'Your 14-day free trial has started. Key features to explore:\n'
            '- Member check-in · Class scheduling · Loyalty points · AI coach\n\n'
            'Get started at your dashboard: /owner/'
        ),
        'day3': (
            f'Hi {gym.gym_name},\n\nYou\'re 3 days in. Tips:\n'
            '- Add members and run a check-in\n- Set up a class schedule\n'
            '- Configure your membership tiers\n\nReply with any questions.'
        ),
        'day7': (
            f'Hi {gym.gym_name},\n\nHalfway through! Highlights:\n'
            '- Automated check-in saves 30 min/day\n'
            '- Loyalty points increase visit frequency by 20%\n\nSubscribe anytime from /billing/.'
        ),
        'day10': (
            f'Hi {gym.gym_name},\n\n4 days left on your trial.\n\n'
            'Subscribe before it ends to keep all your data.'
        ),
        'day13': (
            f'Hi {gym.gym_name},\n\nTomorrow is your last trial day.\n\n'
            'Subscribe today to avoid interruption.'
        ),
        'day14_ended': (
            f'Hi {gym.gym_name},\n\nYour trial has ended and your account is suspended.\n\n'
            'Subscribe at /billing/subscribe/ to restore access. Your data is safe for 30 days.'
        ),
    }
    send_mail(
        subject=subjects.get(template_key, 'GymForge Trial Update'),
        message=bodies.get(template_key, ''),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[gym.owner_email],
        fail_silently=True,
    )
