from django.urls import path

from . import views
from apps.checkin import views as checkin_views

app_name = 'manager'

urlpatterns = [
    # Dashboard
    path('',                                views.dashboard,            name='dashboard'),

    # Live check-in feed
    path('checkins/',                       views.checkin_feed,         name='checkin_feed'),

    # Class scheduling
    path('schedule/',                       views.schedule,             name='schedule'),
    path('schedule/create/',                views.class_session_form,   name='class_session_create'),
    path('schedule/<int:pk>/edit/',         views.class_session_form,   name='class_session_edit'),
    path('schedule/<int:pk>/cancel/',       views.class_session_cancel, name='class_session_cancel'),

    # Staff shifts
    path('shifts/',                         views.staff_shifts,         name='staff_shifts'),
    path('shifts/<int:pk>/attendance/',     views.shift_attendance,     name='shift_attendance'),

    # Maintenance tickets
    path('maintenance/',                    views.maintenance,          name='maintenance'),
    path('maintenance/create/',             views.ticket_create,        name='ticket_create'),
    path('maintenance/<int:pk>/update/',    views.ticket_update,        name='ticket_update'),

    # Member notes
    path('member-notes/',                   views.member_notes,         name='member_notes'),
    path('member-notes/add/',               views.member_note_add,      name='member_note_add'),

    # CardScanLog viewer (read-only, from checkin app)
    path('scan-log/',                       checkin_views.scan_log,     name='scan_log'),
]
