import os
import sys

from django.conf import settings
from django.core.management import execute_from_command_line
from django.core.wsgi import get_wsgi_application

import inngest
import inngest.django
from examples import functions

settings.configure(
    DEBUG=True,
    ROOT_URLCONF=__name__,
    SECRET_KEY="fake",  # noqa: S106
)


inngest_client = inngest.Inngest(
    app_id="django_example",
    is_production=os.getenv("ENV") == "production",
)

urlpatterns = [
    inngest.django.serve(
        inngest_client,
        functions.create_sync_functions(inngest_client),
    ),
]


application = get_wsgi_application()


if __name__ == "__main__":
    execute_from_command_line(sys.argv)
