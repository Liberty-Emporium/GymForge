"""
Community feed views — /app/community/

Models live in apps/community/models.py:
  CommunityPost  — is_visible (not is_hidden); author = FK to User
  PostReaction   — unique_together (post, member); reaction_type choices: like/fire/strong/clap/heart
  GymChallenge   — status field ('active'); prize_description; no reward_points
  ChallengeEntry — current_value (not score); unique_together (challenge, member)
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.community.models import ChallengeEntry, CommunityPost, GymChallenge, PostReaction


def _member_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'member_profile'):
            return redirect('members:home')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _get_member(request):
    return request.user.member_profile


# ---------------------------------------------------------------------------
# Community feed
# ---------------------------------------------------------------------------

@_member_required
def feed(request):
    member = _get_member(request)

    # Pinned first, then newest; exclude hidden posts
    pinned = CommunityPost.objects.filter(
        is_pinned=True, is_visible=True
    ).select_related('author').prefetch_related('reactions').order_by('-created_at')

    regular_qs = CommunityPost.objects.filter(
        is_pinned=False, is_visible=True
    ).select_related('author').prefetch_related('reactions').order_by('-created_at')

    paginator = Paginator(regular_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Which posts this member has already reacted to
    my_reactions = set(
        PostReaction.objects.filter(
            member=request.user,
            post__in=list(pinned) + list(page_obj.object_list),
        ).values_list('post_id', flat=True)
    )

    return render(request, 'member/community_feed.html', {
        'pinned': pinned,
        'page_obj': page_obj,
        'my_reactions': my_reactions,
    })


# ---------------------------------------------------------------------------
# Create post
# ---------------------------------------------------------------------------

@_member_required
def create_post(request):
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        post_type = request.POST.get('post_type', 'general')
        image = request.FILES.get('image')

        if not content:
            messages.error(request, "Post content cannot be empty.")
            return redirect('community:feed')

        CommunityPost.objects.create(
            author=request.user,
            content=content,
            post_type=post_type,
            image=image,
            is_visible=True,
        )
        messages.success(request, "Post shared!")
        return redirect('community:feed')

    return redirect('community:feed')


# ---------------------------------------------------------------------------
# React to post (HTMX toggle)
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def react(request, post_pk):
    post = get_object_or_404(CommunityPost, pk=post_pk, is_visible=True)
    reaction_type = request.POST.get('reaction_type', 'like')

    existing = PostReaction.objects.filter(post=post, member=request.user).first()
    if existing:
        existing.delete()
        reacted = False
    else:
        PostReaction.objects.create(
            post=post,
            member=request.user,
            reaction_type=reaction_type,
        )
        reacted = True

    count = post.reaction_count
    # HTMX partial — return just the updated button
    return render(request, 'member/partials/react_button.html', {
        'post': post,
        'reacted': reacted,
        'count': count,
    })


# ---------------------------------------------------------------------------
# Challenges list
# ---------------------------------------------------------------------------

@_member_required
def challenges(request):
    member = _get_member(request)
    active = GymChallenge.objects.filter(status='active').order_by('end_date')
    upcoming = GymChallenge.objects.filter(status='upcoming').order_by('start_date')

    # Member's joined challenge IDs
    joined_ids = set(
        ChallengeEntry.objects.filter(
            member=request.user
        ).values_list('challenge_id', flat=True)
    )

    return render(request, 'member/challenges.html', {
        'active': active,
        'upcoming': upcoming,
        'joined_ids': joined_ids,
    })


# ---------------------------------------------------------------------------
# Challenge detail + leaderboard
# ---------------------------------------------------------------------------

@_member_required
def challenge_detail(request, challenge_pk):
    challenge = get_object_or_404(GymChallenge, pk=challenge_pk)
    member = _get_member(request)

    my_entry = ChallengeEntry.objects.filter(
        challenge=challenge, member=request.user
    ).first()

    # Top 10 leaderboard by current_value desc
    leaderboard = (
        ChallengeEntry.objects
        .filter(challenge=challenge)
        .select_related('member')
        .order_by('-current_value')[:10]
    )

    # Compute rank for this member
    my_rank = None
    if my_entry:
        my_rank = (
            ChallengeEntry.objects
            .filter(challenge=challenge, current_value__gt=my_entry.current_value)
            .count() + 1
        )

    return render(request, 'member/challenge_detail.html', {
        'challenge': challenge,
        'my_entry': my_entry,
        'leaderboard': leaderboard,
        'my_rank': my_rank,
    })


# ---------------------------------------------------------------------------
# Join challenge
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def join_challenge(request, challenge_pk):
    challenge = get_object_or_404(GymChallenge, pk=challenge_pk, status='active')

    _, created = ChallengeEntry.objects.get_or_create(
        challenge=challenge,
        member=request.user,
    )
    if created:
        messages.success(request, f"You joined '{challenge.title}'!")
    else:
        messages.info(request, "You're already in this challenge.")

    return redirect('community:challenge_detail', challenge_pk=challenge_pk)
