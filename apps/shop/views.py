"""
Shop views — member-facing /app/shop/ and owner management /owner/shop/.

Model corrections vs spec:
  ShopProduct.stock           (not stock_quantity; no available_at_pos field)
  ShopOrder.total_amount      (not total)
  ShopOrder.stripe_payment_intent  (not stripe_payment_intent_id)
  ShopOrder.ordered_at        (not created_at)
  ShopOrder has no 'source' field; use payment_method='stripe' for app purchases
  award_loyalty_points() has no amount_spent kwarg — use description string instead

Cart stored in request.session['cart'] as {str(product_id): qty}.
"""
import json
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.loyalty.utils import award_loyalty_points
from apps.shop.models import ShopOrder, ShopProduct


LOW_STOCK_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _member_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'member_profile'):
            return redirect('members:home')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _owner_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('gym_owner', 'platform_admin'):
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Cart helpers (session-based)
# ---------------------------------------------------------------------------

def _get_cart(request) -> dict:
    """Return cart dict {str(product_id): qty}."""
    return request.session.get('cart', {})


def _save_cart(request, cart: dict):
    request.session['cart'] = cart
    request.session.modified = True


def _cart_with_products(cart: dict) -> tuple[list, Decimal]:
    """Resolve product objects for each cart entry. Returns (items, total)."""
    if not cart:
        return [], Decimal('0.00')
    product_ids = [int(k) for k in cart]
    products = {p.pk: p for p in ShopProduct.objects.filter(pk__in=product_ids, is_active=True)}
    items = []
    total = Decimal('0.00')
    for pid_str, qty in cart.items():
        product = products.get(int(pid_str))
        if product:
            line = product.price * qty
            total += line
            items.append({'product': product, 'qty': qty, 'line_total': line})
    return items, total


# ===========================================================================
# MEMBER SHOP VIEWS
# ===========================================================================

@_member_required
def catalog(request):
    category = request.GET.get('category', '')
    qs = ShopProduct.objects.filter(is_active=True)
    if category:
        qs = qs.filter(category=category)
    products = qs.order_by('category', 'name')

    categories = ShopProduct.CATEGORY_CHOICES

    cart = _get_cart(request)
    cart_count = sum(cart.values())

    return render(request, 'member/shop_catalog.html', {
        'products': products,
        'categories': categories,
        'active_category': category,
        'cart_count': cart_count,
    })


@_member_required
@require_POST
def cart_add(request, product_pk):
    product = get_object_or_404(ShopProduct, pk=product_pk, is_active=True)
    qty = max(1, int(request.POST.get('qty', 1)))
    cart = _get_cart(request)
    key = str(product.pk)
    cart[key] = cart.get(key, 0) + qty
    # Cap at stock
    if product.stock > 0:
        cart[key] = min(cart[key], product.stock)
    _save_cart(request, cart)
    messages.success(request, f"Added {product.name} to cart.")
    return redirect('shop:cart')


@_member_required
@require_POST
def cart_update(request, product_pk):
    cart = _get_cart(request)
    key = str(product_pk)
    qty = int(request.POST.get('qty', 0))
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = qty
    _save_cart(request, cart)
    return redirect('shop:cart')


@_member_required
@require_POST
def cart_remove(request, product_pk):
    cart = _get_cart(request)
    cart.pop(str(product_pk), None)
    _save_cart(request, cart)
    return redirect('shop:cart')


@_member_required
def cart_view(request):
    cart = _get_cart(request)
    items, total = _cart_with_products(cart)
    return render(request, 'member/shop_cart.html', {
        'items': items,
        'total': total,
        'stripe_publishable_key': getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
    })


@_member_required
def checkout(request):
    cart = _get_cart(request)
    items, total = _cart_with_products(cart)

    if not items:
        messages.error(request, "Your cart is empty.")
        return redirect('shop:catalog')

    member = request.user.member_profile

    if request.method == 'POST':
        payment_intent_id = request.POST.get('payment_intent_id', '').strip()

        with db_transaction.atomic():
            order_items = [
                {
                    'product_id': item['product'].pk,
                    'name': item['product'].name,
                    'qty': item['qty'],
                    'price': float(item['product'].price),
                    'line_total': float(item['product'].price * item['qty']),
                }
                for item in items
            ]

            # Calculate loyalty points from product settings
            total_points = sum(
                item['product'].loyalty_points_earned * item['qty']
                for item in items
            )

            order = ShopOrder.objects.create(
                member=member,
                items=order_items,
                total_amount=total,
                payment_method='stripe',
                status='completed',
                stripe_payment_intent=payment_intent_id,
                loyalty_points_earned=total_points,
            )

            # Deduct stock
            for item in items:
                if item['product'].stock > 0:
                    ShopProduct.objects.filter(pk=item['product'].pk).update(
                        stock=item['product'].stock - item['qty']
                    )

            # Award loyalty points
            if total_points > 0:
                award_loyalty_points(
                    member,
                    'product_purchase',
                    description=f"Shop purchase — order #{order.pk}",
                )

        _save_cart(request, {})
        messages.success(request, f"Order #{order.pk} confirmed! Thank you.")
        return redirect('shop:order_detail', order_pk=order.pk)

    # GET — create Stripe PaymentIntent
    client_secret = ''
    try:
        import stripe
        stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if stripe.api_key:
            intent = stripe.PaymentIntent.create(
                amount=int(total * 100),   # cents
                currency='usd',
                metadata={'member_id': member.pk},
            )
            client_secret = intent.client_secret
    except Exception:
        pass  # Stripe not configured — allow fallback checkout

    return render(request, 'member/shop_checkout.html', {
        'items': items,
        'total': total,
        'client_secret': client_secret,
        'stripe_publishable_key': getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
    })


@_member_required
def order_history(request):
    member = request.user.member_profile
    orders = ShopOrder.objects.filter(member=member).order_by('-ordered_at')
    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'member/shop_orders.html', {'page_obj': page_obj})


@_member_required
def order_detail(request, order_pk):
    member = request.user.member_profile
    order = get_object_or_404(ShopOrder, pk=order_pk, member=member)
    return render(request, 'member/shop_order_detail.html', {'order': order})


# ===========================================================================
# OWNER SHOP MANAGEMENT VIEWS
# ===========================================================================

@_owner_required
def owner_product_list(request):
    products = ShopProduct.objects.all().order_by('category', 'name')
    low_stock = [p for p in products if 0 < p.stock < LOW_STOCK_THRESHOLD]
    return render(request, 'gym_owner/shop_products.html', {
        'products': products,
        'low_stock': low_stock,
        'low_stock_threshold': LOW_STOCK_THRESHOLD,
    })


@_owner_required
def owner_product_form(request, pk=None):
    product = get_object_or_404(ShopProduct, pk=pk) if pk else None
    categories = ShopProduct.CATEGORY_CHOICES

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'other')
        price = request.POST.get('price', '0')
        stock = request.POST.get('stock', '0')
        sku = request.POST.get('sku', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        loyalty_points_earned = int(request.POST.get('loyalty_points_earned', 0) or 0)
        image = request.FILES.get('image')

        if not name:
            messages.error(request, "Product name is required.")
            return render(request, 'gym_owner/shop_product_form.html', {
                'product': product, 'categories': categories,
            })

        if product:
            product.name = name
            product.description = description
            product.category = category
            product.price = Decimal(price)
            product.stock = int(stock)
            product.sku = sku
            product.is_active = is_active
            product.loyalty_points_earned = loyalty_points_earned
            if image:
                product.image = image
            product.save()
            messages.success(request, f"'{product.name}' updated.")
        else:
            product = ShopProduct.objects.create(
                name=name,
                description=description,
                category=category,
                price=Decimal(price),
                stock=int(stock),
                sku=sku,
                is_active=is_active,
                loyalty_points_earned=loyalty_points_earned,
                image=image,
            )
            messages.success(request, f"'{product.name}' created.")

        return redirect('gym_owner:shop_products')

    return render(request, 'gym_owner/shop_product_form.html', {
        'product': product,
        'categories': categories,
    })


@_owner_required
@require_POST
def owner_product_deactivate(request, pk):
    product = get_object_or_404(ShopProduct, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    state = "activated" if product.is_active else "deactivated"
    messages.success(request, f"'{product.name}' {state}.")
    return redirect('gym_owner:shop_products')


@_owner_required
@require_POST
def owner_stock_update(request, pk):
    product = get_object_or_404(ShopProduct, pk=pk)
    new_stock = int(request.POST.get('stock', product.stock) or 0)
    product.stock = max(0, new_stock)
    product.save(update_fields=['stock'])
    messages.success(request, f"Stock for '{product.name}' updated to {product.stock}.")
    return redirect('gym_owner:shop_products')


@_owner_required
def owner_order_list(request):
    qs = ShopOrder.objects.all().select_related('member__user').order_by('-ordered_at')

    # Filters
    status = request.GET.get('status', '')
    payment = request.GET.get('payment', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if status:
        qs = qs.filter(status=status)
    if payment:
        qs = qs.filter(payment_method=payment)
    if date_from:
        qs = qs.filter(ordered_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(ordered_at__date__lte=date_to)

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    total_revenue = qs.filter(status='completed').aggregate(t=Sum('total_amount'))['t'] or 0

    return render(request, 'gym_owner/shop_orders.html', {
        'page_obj': page_obj,
        'status_filter': status,
        'payment_filter': payment,
        'date_from': date_from,
        'date_to': date_to,
        'total_revenue': total_revenue,
        'status_choices': ShopOrder.STATUS_CHOICES,
        'payment_choices': ShopOrder.PAYMENT_METHOD_CHOICES,
    })


@_owner_required
@require_POST
def owner_order_fulfill(request, order_pk):
    order = get_object_or_404(ShopOrder, pk=order_pk)
    order.status = 'completed'
    order.save(update_fields=['status'])
    messages.success(request, f"Order #{order.pk} marked as fulfilled.")
    return redirect('gym_owner:shop_orders')
