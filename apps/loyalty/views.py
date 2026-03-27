"""
Loyalty & rewards portal views — /app/loyalty/

All FKs: LoyaltyTransaction.member → MemberProfile, MemberBadge.member → MemberProfile.
Reward stock field is `stock` (not quantity_available). Redeem uses F() for atomic deduction.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.loyalty.models import BadgeMilestone, LoyaltyReward, LoyaltyRule, LoyaltyTransaction, MemberBadge
from apps.members.models import MemberProfile


def _member_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'member_profile'):
            return redirect('members:home')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _get_member(request) -> MemberProfile:
    return request.user.member_profile


# ---------------------------------------------------------------------------
# Points dashboard
# ---------------------------------------------------------------------------

@_member_required
def dashboard(request):
    member = _get_member(request)
    today = date.today()
    month_start = today.replace(day=1)

    earned_this_month = (
        LoyaltyTransaction.objects
        .filter(member=member, transaction_type='earn', created_at__date__gte=month_start)
        .aggregate(total=Sum('points'))['total'] or 0
    )
    redeemed_this_month = abs(
        LoyaltyTransaction.objects
        .filter(member=member, transaction_type='redeem', created_at__date__gte=month_start)
        .aggregate(total=Sum('points'))['total'] or 0
    )

    badge_count = MemberBadge.objects.filter(member=member).count()
    recent_transactions = LoyaltyTransaction.objects.filter(
        member=member
    ).order_by('-created_at')[:5]

    # Streak: consecutive check-in days ending today (reuse CheckIn query)
    from apps.checkin.models import CheckIn
    from datetime import timedelta
    streak = 0
    d = today
    while True:
        if CheckIn.objects.filter(member=member, checked_in_at__date=d).exists():
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    return render(request, 'member/loyalty_dashboard.html', {
        'member': member,
        'earned_this_month': earned_this_month,
        'redeemed_this_month': redeemed_this_month,
        'badge_count': badge_count,
        'recent_transactions': recent_transactions,
        'streak': streak,
    })


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

@_member_required
def transactions(request):
    member = _get_member(request)
    qs = LoyaltyTransaction.objects.filter(member=member).order_by('-created_at')
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'member/loyalty_transactions.html', {
        'page_obj': page_obj,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Badge collection
# ---------------------------------------------------------------------------

@_member_required
def badges(request):
    member = _get_member(request)
    all_milestones = BadgeMilestone.objects.filter(is_active=True).order_by('threshold')
    earned_map = {
        mb.milestone_id: mb.earned_at
        for mb in MemberBadge.objects.filter(member=member).select_related('milestone')
    }

    badge_rows = []
    for ms in all_milestones:
        badge_rows.append({
            'milestone': ms,
            'earned': ms.pk in earned_map,
            'earned_at': earned_map.get(ms.pk),
        })

    return render(request, 'member/loyalty_badges.html', {
        'badge_rows': badge_rows,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Rewards catalog
# ---------------------------------------------------------------------------

@_member_required
def rewards(request):
    member = _get_member(request)
    active_rewards = LoyaltyReward.objects.filter(is_active=True).order_by('points_cost')
    rules = LoyaltyRule.objects.filter(is_active=True).order_by('action')
    return render(request, 'member/loyalty_rewards.html', {
        'rewards': active_rewards,
        'rules': rules,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Redeem reward
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def redeem(request, reward_pk):
    member = _get_member(request)
    reward = get_object_or_404(LoyaltyReward, pk=reward_pk, is_active=True)

    if not reward.is_available:
        messages.error(request, f"'{reward.name}' is no longer available.")
        return redirect('loyalty:rewards')

    if member.loyalty_points < reward.points_cost:
        messages.error(
            request,
            f"Not enough points. You have {member.loyalty_points} pts; "
            f"this reward costs {reward.points_cost} pts."
        )
        return redirect('loyalty:rewards')

    with db_transaction.atomic():
        # Decrement stock if finite
        if reward.stock is not None:
            updated = LoyaltyReward.objects.filter(
                pk=reward.pk, stock__gt=0
            ).update(stock=F('stock') - 1)
            if not updated:
                messages.error(request, "This reward is out of stock.")
                return redirect('loyalty:rewards')

        # Create debit transaction
        LoyaltyTransaction.objects.create(
            member=member,
            points=-reward.points_cost,
            transaction_type='redeem',
            action='redeem',
            description=f"Redeemed: {reward.name}",
        )

        # Atomically deduct from member points
        MemberProfile.objects.filter(pk=member.pk).update(
            loyalty_points=F('loyalty_points') - reward.points_cost
        )
        member.refresh_from_db(fields=['loyalty_points'])

    messages.success(
        request,
        f"✓ Redeemed '{reward.name}' for {reward.points_cost} points! "
        f"Your new balance: {member.loyalty_points} pts."
    )
    return redirect('loyalty:rewards')
