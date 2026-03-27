from django.urls import path

from . import views

app_name = 'ai_coach'

urlpatterns = [
    path('',              views.chat,             name='chat'),
    path('send/',         views.chat_send,        name='chat_send'),
    path('new/',          views.new_conversation, name='new_conversation'),
    path('session-type/', views.set_session_type, name='set_session_type'),
]
