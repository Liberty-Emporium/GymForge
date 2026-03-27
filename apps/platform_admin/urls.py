from django.urls import path
from . import views

app_name = 'platform_admin'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Tenant management
    path('tenants/', views.tenant_list, name='tenant_list'),
    path('tenants/create/', views.tenant_create, name='tenant_create'),
    path('tenants/<int:pk>/', views.tenant_detail, name='tenant_detail'),
    path('tenants/<int:pk>/suspend/', views.tenant_suspend, name='tenant_suspend'),
    path('tenants/<int:pk>/cancel/', views.tenant_cancel, name='tenant_cancel'),
    path('tenants/<int:pk>/reactivate/', views.tenant_reactivate, name='tenant_reactivate'),
    path('tenants/<int:pk>/impersonate/', views.tenant_impersonate, name='tenant_impersonate'),

    # Audit log
    path('audit-log/', views.audit_log, name='audit_log'),

    # Plan management
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/create/', views.plan_create, name='plan_create'),
    path('plans/<int:pk>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:pk>/deactivate/', views.plan_deactivate, name='plan_deactivate'),
]
