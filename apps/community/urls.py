from django.urls import path
from apps.community import views

app_name = 'community'

urlpatterns = [
    path('',                                    views.feed,             name='feed'),
    path('post/',                               views.create_post,      name='create_post'),
    path('post/<int:post_pk>/react/',           views.react,            name='react'),
    path('challenges/',                         views.challenges,       name='challenges'),
    path('challenges/<int:challenge_pk>/',      views.challenge_detail, name='challenge_detail'),
    path('challenges/<int:challenge_pk>/join/', views.join_challenge,   name='join_challenge'),
]
