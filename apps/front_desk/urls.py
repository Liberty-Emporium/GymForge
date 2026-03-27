from django.urls import path

from apps.checkin import views as checkin_views
from apps.front_desk import views

app_name = 'front_desk'

urlpatterns = [
    # Main dashboard
    path('',                    views.dashboard,      name='dashboard'),

    # Check-in actions
    path('checkin/card/',       views.card_checkin,   name='card_checkin'),
    path('checkin/manual/',     views.manual_checkin, name='manual_checkin'),
    path('checkin/guest/',      views.guest_checkin,  name='guest_checkin'),
    path('checkout/<int:checkin_pk>/', views.checkout, name='checkout'),

    # Member lookup
    path('members/',                    views.member_lookup, name='member_lookup'),
    path('members/<int:member_pk>/',    views.member_detail, name='member_detail'),

    # Walk-in registration
    path('walk-in/',            views.walk_in,        name='walk_in'),

    # Card management (Step 31)
    path('cards/<int:member_id>/',          checkin_views.member_cards,    name='member_cards'),
    path('cards/<int:member_id>/issue/',    checkin_views.card_issue,      name='card_issue'),
    path('cards/deactivate/<int:card_id>/', checkin_views.card_deactivate, name='card_deactivate'),
    path('cards/replace/<int:card_id>/',    checkin_views.card_replace,    name='card_replace'),
    path('cards/print/<int:card_id>/',      checkin_views.card_print_pdf,  name='card_print_pdf'),

    # Device management (manager/owner only, mounted here for /desk/ prefix convenience)
    path('devices/',                            checkin_views.device_list,       name='device_list'),
    path('devices/register/',                   checkin_views.device_register,   name='device_register'),
    path('devices/deactivate/<int:device_id>/', checkin_views.device_deactivate, name='device_deactivate'),
]
