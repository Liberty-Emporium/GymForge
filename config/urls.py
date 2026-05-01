"""
GymForge URL Configuration
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


def health_check(request):
    """Railway / uptime-monitor health probe. Always returns 200."""
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('django-admin/', admin.site.urls),

    # Gym owner signup wizard — public schema
    path('setup/', include('apps.setup.urls')),

    # Platform Owner — public schema only
    path('platform/', include('apps.platform_admin.urls')),

    # Staff portals — tenant schema
    path('owner/', include('apps.gym_owner.urls')),
    path('owner/leads/', include('apps.leads.urls', namespace='leads')),
    path('owner/payroll/', include('apps.payroll.urls')),
    path('manager/', include('apps.manager.urls')),
    path('trainer/', include('apps.trainer.urls')),
    path('desk/', include('apps.front_desk.urls')),
    path('cleaner/', include('apps.cleaner.urls')),
    path('nutritionist/', include('apps.nutritionist.urls')),
    path('kiosk/', include('apps.kiosk.urls')),

    # Member app — tenant schema
    path('app/', include('apps.members.urls')),
    path('app/ai/', include('apps.ai_coach.urls')),
    path('app/community/', include('apps.community.urls')),
    path('app/shop/', include('apps.shop.urls')),
    path('app/loyalty/', include('apps.loyalty.urls')),

    # Auth — works across all portals
    path('auth/', include('apps.accounts.urls')),

    # Payments and webhooks
    path('billing/', include('apps.billing.urls')),

    # REST API — for door agents and mobile
    path('api/v1/', include('apps.api.urls')),

    # Gym landing page — root of tenant domain
    path('', include('apps.landing.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
