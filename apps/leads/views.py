"""
Lead management views for the gym owner portal.

All views are protected by @gym_owner_required imported from apps.gym_owner.views.
URL namespace: 'leads' — mounted at /owner/leads/ via gym_owner/urls.py.
"""
import csv

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.gym_owner.views import gym_owner_required


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUSES = [
    ('new',          'New'),
    ('contacted',    'Contacted'),
    ('trial_booked', 'Trial Booked'),
    ('converted',    'Converted'),
    ('lost',         'Lost'),
]

STATUS_ACCENT = {
    'new':          '#3b82f6',   # blue
    'contacted':    '#f59e0b',   # amber
    'trial_booked': '#8b5cf6',   # violet
    'converted':    '#10b981',   # emerald
    'lost':         '#6b7280',   # gray
}


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _base_qs(request):
    """Build a Lead queryset with all active GET filters applied (except status)."""
    from apps.leads.models import Lead

    qs = Lead.objects.select_related('assigned_to', 'location')

    source    = request.GET.get('source')
    assigned  = request.GET.get('assigned')
    location  = request.GET.get('location')
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    search    = request.GET.get('q', '').strip()

    if source:
        qs = qs.filter(source=source)
    if assigned:
        try:
            qs = qs.filter(assigned_to_id=int(assigned))
        except (ValueError, TypeError):
            pass
    if location:
        try:
            qs = qs.filter(location_id=int(location))
        except (ValueError, TypeError):
            pass
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    return qs


def _filter_context(request):
    """Return filter-selector data for templates."""
    from apps.leads.models import Lead
    from apps.core.models import Location
    from apps.accounts.models import User
    return {
        'sources':   Lead.SOURCE_CHOICES,
        'statuses':  STATUSES,
        'locations': Location.objects.filter(is_active=True),
        'staff':     User.objects.filter(is_active=True).exclude(role__in=['member', 'platform_admin']),
        'filters':   request.GET,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@gym_owner_required
def pipeline(request):
    from apps.leads.models import Lead

    base = _base_qs(request)
    status_filter = request.GET.get('status')

    columns = []
    for code, label in STATUSES:
        if status_filter and code != status_filter:
            col_qs = base.none()
        else:
            col_qs = base.filter(status=code)
        columns.append({
            'code':   code,
            'label':  label,
            'leads':  list(col_qs),
            'count':  col_qs.count(),
            'accent': STATUS_ACCENT[code],
        })

    ctx = _filter_context(request)
    ctx.update({
        'columns':   columns,
        'methods':   Lead.follow_ups.rel.related_model.METHOD_CHOICES,
        'total':     sum(c['count'] for c in columns),
    })
    return render(request, 'owner/leads/pipeline.html', ctx)


# ---------------------------------------------------------------------------
# Quick add (HTMX)
# ---------------------------------------------------------------------------

@gym_owner_required
def quick_add(request):
    """
    HTMX POST — create a lead and return the lead card HTML.
    On error returns the form partial with errors.
    On success uses HX-Retarget / HX-Reswap so the card lands in #new-col-cards.
    """
    from apps.leads.models import Lead

    if request.method != 'POST':
        return HttpResponse(status=405)

    first_name = request.POST.get('first_name', '').strip()
    last_name  = request.POST.get('last_name', '').strip()
    email      = request.POST.get('email', '').strip().lower()
    phone      = request.POST.get('phone', '').strip()
    source     = request.POST.get('source', 'walk_in')
    notes      = request.POST.get('notes', '').strip()

    errors = {}
    if not first_name:
        errors['first_name'] = 'First name is required.'

    if errors:
        resp = render(request, 'owner/leads/partials/quick_add_form.html', {
            'errors':  errors,
            'post':    request.POST,
            'sources': Lead.SOURCE_CHOICES,
        })
        resp['HX-Retarget'] = '#quick-add-form-wrap'
        resp['HX-Reswap']   = 'innerHTML'
        return resp

    lead = Lead.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        source=source,
        notes=notes,
        status='new',
    )
    resp = render(request, 'owner/leads/partials/lead_card.html', {
        'lead':   lead,
        'accent': STATUS_ACCENT['new'],
    })
    resp['HX-Retarget'] = '#new-col-cards'
    resp['HX-Reswap']   = 'afterbegin'
    return resp


# ---------------------------------------------------------------------------
# Lead detail + update
# ---------------------------------------------------------------------------

@gym_owner_required
def lead_detail(request, pk):
    from apps.leads.models import Lead, LeadFollowUp
    from apps.core.models import Location
    from apps.accounts.models import User

    lead       = get_object_or_404(Lead, pk=pk)
    follow_ups = lead.follow_ups.select_related('completed_by').order_by('scheduled_at')

    return render(request, 'owner/leads/detail.html', {
        'lead':       lead,
        'follow_ups': follow_ups,
        'statuses':   STATUSES,
        'sources':    Lead.SOURCE_CHOICES,
        'methods':    LeadFollowUp.METHOD_CHOICES,
        'locations':  Location.objects.filter(is_active=True),
        'staff':      User.objects.filter(is_active=True).exclude(role__in=['member', 'platform_admin']),
        'accent':     STATUS_ACCENT.get(lead.status, '#6b7280'),
    })


@gym_owner_required
def lead_update(request, pk):
    if request.method != 'POST':
        return redirect('leads:detail', pk=pk)

    from apps.leads.models import Lead
    lead = get_object_or_404(Lead, pk=pk)

    lead.first_name = request.POST.get('first_name', lead.first_name).strip() or lead.first_name
    lead.last_name  = request.POST.get('last_name',  lead.last_name).strip()
    lead.email      = request.POST.get('email',  lead.email).strip().lower()
    lead.phone      = request.POST.get('phone',  lead.phone).strip()
    lead.source     = request.POST.get('source', lead.source)
    lead.notes      = request.POST.get('notes',  lead.notes).strip()

    new_status = request.POST.get('status', lead.status)
    lead.status = new_status
    if new_status == 'converted' and not lead.converted_at:
        lead.converted_at = timezone.now()

    assigned_id = request.POST.get('assigned_to', '').strip()
    if assigned_id:
        try:
            from apps.accounts.models import User
            lead.assigned_to = User.objects.get(pk=int(assigned_id))
        except (Exception,):
            lead.assigned_to = None
    else:
        lead.assigned_to = None

    location_id = request.POST.get('location', '').strip()
    if location_id:
        try:
            from apps.core.models import Location
            lead.location = Location.objects.get(pk=int(location_id))
        except (Exception,):
            lead.location = None
    else:
        lead.location = None

    lead.save()
    return redirect('leads:detail', pk=pk)


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------

@gym_owner_required
def followup_create(request, pk):
    """HTMX POST — create a follow-up and return the new row partial."""
    if request.method != 'POST':
        return redirect('leads:detail', pk=pk)

    from apps.leads.models import Lead, LeadFollowUp
    lead = get_object_or_404(Lead, pk=pk)

    method       = request.POST.get('method', 'email')
    scheduled_at = request.POST.get('scheduled_at', '').strip()
    notes        = request.POST.get('notes', '').strip()

    errors = {}
    scheduled_dt = None
    if not scheduled_at:
        errors['scheduled_at'] = 'Date and time are required.'
    else:
        scheduled_dt = parse_datetime(scheduled_at)
        if not scheduled_dt:
            errors['scheduled_at'] = 'Invalid date/time format.'

    if errors:
        resp = render(request, 'owner/leads/partials/followup_form.html', {
            'lead':    lead,
            'errors':  errors,
            'post':    request.POST,
            'methods': LeadFollowUp.METHOD_CHOICES,
        })
        resp['HX-Retarget'] = '#followup-form-wrap'
        resp['HX-Reswap']   = 'innerHTML'
        return resp

    fu = LeadFollowUp.objects.create(
        lead=lead,
        method=method,
        scheduled_at=scheduled_dt,
        notes=notes,
    )
    lead.last_contacted_at = timezone.now()
    lead.save(update_fields=['last_contacted_at'])

    resp = render(request, 'owner/leads/partials/followup_row.html', {
        'fu':      fu,
        'lead_pk': pk,
    })
    resp['HX-Retarget'] = '#followup-list'
    resp['HX-Reswap']   = 'beforeend'
    return resp


@gym_owner_required
def followup_complete(request, pk, followup_pk):
    """HTMX POST — mark a follow-up complete and return the updated row."""
    if request.method != 'POST':
        return redirect('leads:detail', pk=pk)

    from apps.leads.models import LeadFollowUp
    fu = get_object_or_404(LeadFollowUp, pk=followup_pk, lead_id=pk)

    if not fu.is_completed:
        fu.completed_at  = timezone.now()
        fu.completed_by  = request.user
        fu.save(update_fields=['completed_at', 'completed_by'])

    return render(request, 'owner/leads/partials/followup_row.html', {
        'fu':      fu,
        'lead_pk': pk,
    })


# ---------------------------------------------------------------------------
# AI draft message
# ---------------------------------------------------------------------------

@gym_owner_required
def ai_draft(request, pk):
    """
    HTMX POST — call Claude to draft a follow-up message for this lead.
    Returns a modal partial containing the draft.
    """
    if request.method != 'POST':
        return redirect('leads:detail', pk=pk)

    from apps.leads.models import Lead
    from apps.ai_coach.client import GymForgeAIClient

    lead = get_object_or_404(Lead, pk=pk)

    system_prompt = (
        "You are a gym business assistant helping a gym owner draft follow-up messages "
        "to prospective members (leads). Write concise, warm, professional messages "
        "tailored to where the lead is in the sales pipeline. "
        "Keep messages under 120 words. Do not include a subject line unless asked."
    )
    user_message = (
        f"Draft a follow-up message for this lead:\n"
        f"- Name: {lead.full_name}\n"
        f"- Status: {lead.get_status_display()}\n"
        f"- Source: {lead.get_source_display()}\n"
        f"- Notes: {lead.notes or 'None provided'}\n\n"
        "Write a brief, personalized outreach message appropriate to their stage."
    )

    ai_client = GymForgeAIClient(
        system_prompt=system_prompt,
        conversation_history=[],
    )
    try:
        draft = ai_client.send_message(user_message)
    except Exception:
        draft = "Unable to generate a draft right now. Please try again."

    return render(request, 'owner/leads/partials/ai_draft.html', {
        'draft': draft,
        'lead':  lead,
    })


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@gym_owner_required
def export_csv(request):
    """Download all filtered leads as a CSV file."""
    qs = _base_qs(request)

    # Also apply status filter for export
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leads.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'First Name', 'Last Name', 'Email', 'Phone', 'Status', 'Source',
        'Location', 'Assigned To', 'Notes', 'Created', 'Last Contacted', 'Converted',
    ])
    for lead in qs:
        writer.writerow([
            lead.first_name,
            lead.last_name,
            lead.email,
            lead.phone,
            lead.get_status_display(),
            lead.get_source_display(),
            lead.location.name if lead.location else '',
            lead.assigned_to.get_full_name() if lead.assigned_to else '',
            lead.notes,
            lead.created_at.strftime('%Y-%m-%d %H:%M'),
            lead.last_contacted_at.strftime('%Y-%m-%d %H:%M') if lead.last_contacted_at else '',
            lead.converted_at.strftime('%Y-%m-%d %H:%M') if lead.converted_at else '',
        ])
    return response
