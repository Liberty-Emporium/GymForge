from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    # Login / logout
    path('login/', auth_views.LoginView.as_view(template_name='base/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/auth/login/'), name='logout'),

    # Password reset flow (Django built-ins)
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(template_name='base/password_reset.html'),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='base/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='base/password_reset_confirm.html'),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(template_name='base/password_reset_complete.html'),
        name='password_reset_complete',
    ),

    # Role-based post-login redirect (Step 24+)
    path('redirect/', views.role_redirect, name='role_redirect'),
]
