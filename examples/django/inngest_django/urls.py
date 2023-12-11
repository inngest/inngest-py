from django.contrib import admin
from django.urls import path

import inngest.django
from examples import functions

from .inngest_client import inngest_client

urlpatterns = [
    path("admin/", admin.site.urls),
    inngest.django.serve(
        inngest_client,
        functions.functions_sync,
    ),
]
