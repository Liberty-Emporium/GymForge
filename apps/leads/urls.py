from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('',                                            views.pipeline,          name='pipeline'),
    path('new/',                                        views.quick_add,         name='quick_add'),
    path('export/',                                     views.export_csv,        name='export_csv'),
    path('<int:pk>/',                                   views.lead_detail,       name='detail'),
    path('<int:pk>/update/',                            views.lead_update,       name='update'),
    path('<int:pk>/followup/',                          views.followup_create,   name='followup_create'),
    path('<int:pk>/followup/<int:followup_pk>/done/',   views.followup_complete, name='followup_complete'),
    path('<int:pk>/ai-draft/',                          views.ai_draft,          name='ai_draft'),
]
