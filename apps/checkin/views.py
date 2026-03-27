"""
RFID card system, door device management, and card scan log viewer.

Auth tiers
----------
_front_desk_or_above : front_desk, manager, gym_owner, platform_admin
_manager_or_owner    : manager, gym_owner, platform_admin

URL homes
---------
Card + device management → /desk/cards/... and /desk/devices/...
Scan log viewer          → /manager/scan-log/
"""
import io
import uuid
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.checkin.models import CardScanLog, DoorDevice, MemberCard
from apps.core.models import Location
from apps.members.models import MemberProfile


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------

def _front_desk_or_above(view_func):
    ALLOWED = {'front_desk', 'manager', 'gym_owner', 'platform_admin'}

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role not in ALLOWED:
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


def _manager_or_owner(view_func):
    ALLOWED = {'manager', 'gym_owner', 'platform_admin'}

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role not in ALLOWED:
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Card number generation
# ---------------------------------------------------------------------------

def _next_card_number() -> str:
    """Return the next sequential card number in GF-NNNNN format."""
    last = MemberCard.objects.order_by('-id').first()
    if last and last.card_number.startswith('GF-'):
        try:
            num = int(last.card_number[3:]) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f'GF-{num:05d}'


# ---------------------------------------------------------------------------
# Card management
# ---------------------------------------------------------------------------

@_front_desk_or_above
def member_cards(request, member_id):
    """List all RFID cards for a member and issue a new one."""
    member = get_object_or_404(MemberProfile, pk=member_id)
    cards = MemberCard.objects.filter(member=member).order_by('-issued_at')
    return render(request, 'front_desk/member_cards.html', {
        'member': member,
        'cards': cards,
    })


@_front_desk_or_above
@require_POST
def card_issue(request, member_id):
    """Issue a new RFID card to a member."""
    member = get_object_or_404(MemberProfile, pk=member_id)

    card = MemberCard.objects.create(
        member=member,
        rfid_token=MemberCard.generate_token(),
        card_number=_next_card_number(),
        issued_by=request.user,
    )
    messages.success(request, f'Card {card.card_number} issued successfully.')
    return redirect('front_desk:member_cards', member_id=member_id)


@_front_desk_or_above
@require_POST
def card_deactivate(request, card_id):
    """Deactivate an RFID card."""
    card = get_object_or_404(MemberCard, pk=card_id)
    reason = request.POST.get('deactivation_reason', '').strip() or 'Deactivated by staff'
    card.deactivate(reason=reason)
    messages.success(request, f'Card {card.card_number} deactivated.')
    return redirect('front_desk:member_cards', member_id=card.member_id)


@_front_desk_or_above
@require_POST
def card_replace(request, card_id):
    """Deactivate a card and issue a replacement in one step."""
    old_card = get_object_or_404(MemberCard, pk=card_id)
    old_card.deactivate(reason='Replaced')

    new_card = MemberCard.objects.create(
        member=old_card.member,
        rfid_token=MemberCard.generate_token(),
        card_number=_next_card_number(),
        issued_by=request.user,
    )
    messages.success(
        request,
        f'Card {old_card.card_number} replaced with {new_card.card_number}.'
    )
    return redirect('front_desk:member_cards', member_id=old_card.member_id)


# ---------------------------------------------------------------------------
# Card print PDF
# ---------------------------------------------------------------------------

@_front_desk_or_above
def card_print_pdf(request, card_id):
    """
    Generate a CR80-sized PDF card (85.6 mm × 53.98 mm) with member name,
    card number, gym name, and a QR code of the card number.

    Requires: reportlab, qrcode[pil]
    """
    card = get_object_or_404(MemberCard, pk=card_id)

    try:
        import qrcode
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
    except ImportError:
        return HttpResponse(
            'PDF generation requires reportlab and qrcode packages. '
            'Install with: pip install reportlab "qrcode[pil]"',
            status=503,
            content_type='text/plain',
        )

    try:
        from apps.core.models import GymProfile
        profile = GymProfile.objects.get()
        gym_name = profile.gym_name
        primary_hex = profile.primary_color or '#1a1a2e'
        accent_hex = profile.accent_color or '#e94560'
    except Exception:
        gym_name = 'My Gym'
        primary_hex = '#1a1a2e'
        accent_hex = '#e94560'

    # CR80 dimensions in mm
    CARD_W = 85.6 * mm
    CARD_H = 53.98 * mm

    def _hex_to_rgb_float(hex_color: str):
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return r / 255, g / 255, b / 255

    primary_rgb = _hex_to_rgb_float(primary_hex)
    accent_rgb = _hex_to_rgb_float(accent_hex)

    # Generate QR code image in memory
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(card.card_number)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white')
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)

    # Build PDF
    pdf_buffer = io.BytesIO()
    c = rl_canvas.Canvas(pdf_buffer, pagesize=(CARD_W, CARD_H))

    # Background
    c.setFillColorRGB(*primary_rgb)
    c.rect(0, 0, CARD_W, CARD_H, fill=True, stroke=False)

    # Accent strip at bottom
    c.setFillColorRGB(*accent_rgb)
    c.rect(0, 0, CARD_W, 8 * mm, fill=True, stroke=False)

    # Gym name
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(4 * mm, CARD_H - 8 * mm, gym_name.upper())

    # Member name
    c.setFont('Helvetica-Bold', 12)
    member_name = card.member.full_name or card.member.email
    c.drawString(4 * mm, CARD_H - 18 * mm, member_name)

    # Card number
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(*accent_rgb)
    c.drawString(4 * mm, CARD_H - 26 * mm, card.card_number)

    # Issued date
    c.setFillColor(colors.white)
    c.setFont('Helvetica', 7)
    c.drawString(4 * mm, CARD_H - 33 * mm, f'Issued: {card.issued_at:%d %b %Y}')

    # QR code (right side)
    qr_size = 34 * mm
    c.drawImage(
        qr_buffer,
        CARD_W - qr_size - 3 * mm,
        (CARD_H - qr_size) / 2,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
    )

    c.showPage()
    c.save()
    pdf_buffer.seek(0)

    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'inline; filename="card-{card.card_number}.pdf"'
    )
    return response


# ---------------------------------------------------------------------------
# Door device management
# ---------------------------------------------------------------------------

@_manager_or_owner
def device_list(request):
    """List all door devices across all locations."""
    devices = (
        DoorDevice.objects
        .select_related('location')
        .order_by('location__name', 'name')
    )
    locations = Location.objects.filter(is_active=True)
    return render(request, 'front_desk/devices.html', {
        'devices': devices,
        'locations': locations,
        'device_types': DoorDevice.DEVICE_TYPES,
    })


@_manager_or_owner
def device_register(request):
    """
    Register a new door device. On success, displays the device_token ONCE.
    The token cannot be retrieved again — it must be copied immediately.
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        device_type = request.POST.get('device_type', '')
        location_id = request.POST.get('location', '')

        errors = {}
        if not name:
            errors['name'] = 'Device name is required.'
        if device_type not in dict(DoorDevice.DEVICE_TYPES):
            errors['device_type'] = 'Select a valid device type.'
        location = None
        if location_id:
            try:
                location = Location.objects.get(pk=location_id)
            except Location.DoesNotExist:
                errors['location'] = 'Invalid location.'
        else:
            errors['location'] = 'Location is required.'

        if not errors:
            token = str(uuid.uuid4())
            device = DoorDevice.objects.create(
                name=name,
                device_type=device_type,
                location=location,
                device_token=token,
                is_active=True,
            )
            # Pass the token in context — shown ONCE, never stored retrievable
            return render(request, 'front_desk/device_registered.html', {
                'device': device,
                'device_token': token,
            })

        locations = Location.objects.filter(is_active=True)
        return render(request, 'front_desk/device_register.html', {
            'errors': errors,
            'post': request.POST,
            'locations': locations,
            'device_types': DoorDevice.DEVICE_TYPES,
        })

    locations = Location.objects.filter(is_active=True)
    return render(request, 'front_desk/device_register.html', {
        'locations': locations,
        'device_types': DoorDevice.DEVICE_TYPES,
    })


@_manager_or_owner
@require_POST
def device_deactivate(request, device_id):
    """Deactivate a door device."""
    device = get_object_or_404(DoorDevice, pk=device_id)
    device.is_active = False
    device.save(update_fields=['is_active'])
    messages.success(request, f'Device "{device.name}" deactivated.')
    return redirect('front_desk:device_list')


# ---------------------------------------------------------------------------
# CardScanLog viewer (IMMUTABLE — read-only)
# ---------------------------------------------------------------------------

@_manager_or_owner
def scan_log(request):
    """
    Paginated, filterable read-only view of all CardScanLog entries.
    Filters: card (card_number), device, result, date_from, date_to.
    """
    qs = (
        CardScanLog.objects
        .select_related('card__member__user', 'device__location')
        .order_by('-scanned_at')
    )

    # Filters
    card_q = request.GET.get('card', '').strip()
    device_id = request.GET.get('device', '').strip()
    result_q = request.GET.get('result', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if card_q:
        qs = qs.filter(card__card_number__icontains=card_q)
    if device_id:
        qs = qs.filter(device_id=device_id)
    if result_q:
        qs = qs.filter(result=result_q)
    if date_from:
        qs = qs.filter(scanned_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(scanned_at__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page', 1))

    devices = DoorDevice.objects.select_related('location').order_by('location__name', 'name')

    return render(request, 'manager/scan_log.html', {
        'page': page,
        'devices': devices,
        'results': CardScanLog.RESULTS,
        'filters': {
            'card': card_q,
            'device': device_id,
            'result': result_q,
            'date_from': date_from,
            'date_to': date_to,
        },
    })
