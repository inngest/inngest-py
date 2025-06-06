import enum
import importlib.metadata
import typing

AUTHOR: typing.Final = "inngest"
DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_API_ORIGIN: typing.Final = "https://inn.gs/"
DEFAULT_SERVE_PATH: typing.Final = "/api/inngest"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
VERSION: typing.Final = importlib.metadata.version("inngest")


class EnvKey(enum.Enum):
    ALLOW_IN_BAND_SYNC = "INNGEST_ALLOW_IN_BAND_SYNC"
    API_BASE_URL = "INNGEST_API_BASE_URL"

    # Sets both API and EVENT base URLs. API_BASE_URL and EVENT_API_BASE_URL
    # take precedence
    BASE_URL = "INNGEST_BASE_URL"

    # Can be a boolean string ("true", "1", "false", "0") or a URL
    DEV = "INNGEST_DEV"

    EVENT_API_BASE_URL = "INNGEST_EVENT_API_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    ENV = "INNGEST_ENV"

    # The ThreadPoolExecutor max_workers arg. If set to 0, the thread pool will
    # not be created. There probably isn't a use case for disabling, though we
    # should have it until we get lots of feedback on the thread pool.
    THREAD_POOL_MAX_WORKERS = "INNGEST_THREAD_POOL_MAX_WORKERS"

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

    # Controls the "streaming" feature, which sends keepalive bytes until the
    # response is complete.
    STREAMING = "INNGEST_STREAMING"

    # Vercel deployment's git branch
    # https://vercel.com/docs/concepts/projects/environment-variables/system-environment-variables#system-environment-variables
    VERCEL_GIT_BRANCH = "VERCEL_GIT_COMMIT_REF"


class Streaming(enum.Enum):
    """
    Controls the "streaming" feature, which sends keepalive bytes until the
    response is complete.
    """

    DISABLE = "disable"
    FORCE = "force"
