import enum
import importlib.metadata
import typing

DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_API_ORIGIN: typing.Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
VERSION: typing.Final = importlib.metadata.version("inngest")


class EnvKey(enum.Enum):
    API_BASE_URL = "INNGEST_API_BASE_URL"

    # Sets both API and EVENT base URLs. API_BASE_URL and EVENT_API_BASE_URL
    # take precedence
    BASE_URL = "INNGEST_BASE_URL"

    # Can be a boolean string ("true", "1", "false", "0") or a URL
    DEV = "INNGEST_DEV"

    EVENT_API_BASE_URL = "INNGEST_EVENT_API_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    ENV = "INNGEST_ENV"

    # Railway deployment's git branch
    # https://docs.railway.app/develop/variables#railway-provided-variables
    RAILWAY_GIT_BRANCH = "RAILWAY_GIT_BRANCH"

    # Render deployment's git branch
    # https://render.com/docs/environment-variables#all-services
    RENDER_GIT_BRANCH = "RENDER_GIT_BRANCH"

    SERVE_ORIGIN = "INNGEST_SERVE_ORIGIN"
    SERVE_PATH = "INNGEST_SERVE_PATH"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"
    SIGNING_KEY_FALLBACK = "INNGEST_SIGNING_KEY_FALLBACK"

    # Vercel deployment's git branch
    # https://vercel.com/docs/concepts/projects/environment-variables/system-environment-variables#system-environment-variables
    VERCEL_GIT_BRANCH = "VERCEL_GIT_COMMIT_REF"
