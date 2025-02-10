import inngest.django
from django.contrib import admin
from django.urls import path

from .functions import hello
from .inngest_client import inngest_client

urlpatterns = [
    path("admin/", admin.site.urls),
    inngest.django.serve(
        inngest_client,
        [hello],
    ),
]
