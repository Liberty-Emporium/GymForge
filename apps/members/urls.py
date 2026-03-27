from django.urls import path

from . import views
from apps.scheduling import views as scheduling_views
from apps.members import nutrition_views
from apps.members import progress_views

app_name = 'members'

urlpatterns = [
    # Home screen
    path('', views.home, name='home'),

    # Registration wizard (public / no-auth required for step 1)
    path('register/', views.register, name='register'),
    path('register/waiver/', views.register_waiver, name='register_waiver'),
    path('register/plans/', views.register_plans, name='register_plans'),
    path('register/intake/', views.register_intake, name='register_intake'),
    path('register/intake/send/', views.register_intake_send, name='register_intake_send'),
    path('register/intake/complete/', views.register_intake_complete, name='register_intake_complete'),
    path('register/welcome/', views.register_welcome, name='register_welcome'),

    # App state
    path('unavailable/', views.app_unavailable, name='app_unavailable'),

    # Workout tracking
    path('workouts/',                           views.workout_history,      name='workout_history'),
    path('workouts/log/',                       views.workout_log,          name='workout_log'),
    path('workouts/records/',                   views.personal_records,     name='personal_records'),
    path('workouts/partials/exercise-row/',     views.exercise_row_partial, name='exercise_row_partial'),

    # Progress dashboard (Step 30)
    path('progress/',               progress_views.progress_home,    name='progress'),
    path('progress/log-metric/',    progress_views.log_body_metric,  name='log_body_metric'),

    # Nutrition (Step 29)
    path('nutrition/',                              nutrition_views.nutrition_home,         name='nutrition_home'),
    path('nutrition/generate/',                     nutrition_views.generate_nutrition_plan, name='generate_nutrition_plan'),
    path('nutrition/<int:plan_id>/swap/',           nutrition_views.swap_meal_item,         name='swap_meal_item'),

    # Class booking (Step 28)
    path('classes/',                                scheduling_views.schedule,       name='class_schedule'),
    path('classes/my-bookings/',                    scheduling_views.my_bookings,    name='my_bookings'),
    path('classes/<int:session_id>/',               scheduling_views.class_detail,   name='class_detail'),
    path('classes/book/<int:session_id>/',          scheduling_views.book_class,     name='book_class'),
    path('classes/cancel/<int:booking_id>/',        scheduling_views.cancel_booking, name='cancel_booking'),
]
