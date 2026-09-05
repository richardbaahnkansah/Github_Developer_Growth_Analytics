from django.urls import path
from . import views

urlpatterns = [
    path("developer/<str:username>/", views.developer_detail),
    path("developer/<str:username>/sync/", views.sync),
    path("developer/<str:username>/dashboard/", views.dashboard),
    path("developer/<str:username>/timeline/", views.timeline),
    path("developer/<str:username>/languages/", views.languages),
    path("developer/<str:username>/repositories/", views.repositories),
]
