"""
Billing Celery tasks.

charge_no_show_fee — shared helper for no-show and late-cancel Stripe charges.
    Called by: process_no_shows task (no-shows) and cancel_booking view (late cancels).

process_no_shows — periodic task (every 15 min via Celery beat).
    Scans all tenant schemas for confirmed bookings where the class ended
    more than 30 minutes ago and charges have not yet been processed.
"""
import logging
from datetime import timedelta

import stripe
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.billing.models import NoShowCharge
from apps.scheduling.models import Booking
from apps.tenants.models import GymTenant

stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

logger = logging.getLogger(__name__)


def charge_no_show_fee(booking, fee_amount, charge_type):
    """
    Charge a no-show or late-cancel fee to the member's saved Stripe customer.

    Args:
        booking    : Booking instance (status already set by caller)
        fee_amount : Decimal — from MembershipTier.no_show_fee or .late_cancel_fee
        charge_type: 'no_show' or 'late_cancel'

    Side effects:
        - Creates a NoShowCharge record (status='completed' or 'failed')
        - Sets booking.no_show_fee_charged=True on success
        - Sends notification email to member on success
        - Never raises — all Stripe errors are caught and logged

    Precondition: the Stripe Customer (stripe_customer_id) must have a default
    payment method set in Stripe. Without it, Stripe rejects the off-session charge
    and the NoShowCharge is recorded as failed for manual review.
    """
    member = booking.member
    membership = member.active_membership

    if not membership or not membership.stripe_customer_id:
        logger.warning(
            'No stripe_customer_id for member %s (booking %s) — skipping charge',
            member,
            booking.pk,
        )
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            status='failed',
        )
        return

    amount_cents = int(fee_amount * 100)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            customer=membership.stripe_customer_id,
            confirm=True,
            off_session=True,
        )
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            stripe_payment_intent=intent.id,
            status='completed',
        )
        booking.no_show_fee_charged = True
        booking.save(update_fields=['no_show_fee_charged'])

        subject = (
            'No-show fee charged'
            if charge_type == 'no_show'
            else 'Late cancellation fee charged'
        )
        send_mail(
            subject=subject,
            message=(
                f'Hi {member.user.get_full_name() or member.user.username},\n\n'
                f'A ${fee_amount:.2f} {subject.lower()} has been applied to your account.\n\n'
                f'If you have any questions, please contact the gym.\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@gymforge.com'),
            recipient_list=[member.user.email],
            fail_silently=True,
        )

    except stripe.error.StripeError as e:
        logger.error('Stripe charge failed for booking %s: %s', booking.pk, e)
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            status='failed',
        )


@shared_task
def process_no_shows():
    """
    Scan all active tenant schemas for no-shows and charge fees.

    Runs every 15 minutes via Celery beat. A no-show is a Booking with:
      - status='confirmed'
      - no_show_fee_charged=False
      - class_session.end_datetime < now - 30 minutes
    """
    cutoff = timezone.now() - timedelta(minutes=30)
    tenants = GymTenant.objects.filter(subscription_status__in=['trial', 'active'])

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                bookings = (
                    Booking.objects
                    .filter(
                        status='confirmed',
                        no_show_fee_charged=False,
                        class_session__end_datetime__lt=cutoff,
                    )
                    .select_related('member__user', 'class_session')
                    .prefetch_related('member__memberships__tier')
                )
                for booking in bookings:
                    booking.status = 'no_show'
                    booking.save(update_fields=['status'])

                    membership = booking.member.active_membership
                    if membership and membership.tier.no_show_fee > 0:
                        charge_no_show_fee(
                            booking,
                            membership.tier.no_show_fee,
                            'no_show',
                        )
                    else:
                        booking.no_show_fee_charged = True
                        booking.save(update_fields=['no_show_fee_charged'])

        except Exception:
            logger.exception(
                'process_no_shows failed for tenant %s', tenant.schema_name
            )
