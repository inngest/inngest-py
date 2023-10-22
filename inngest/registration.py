from pydantic import Field

from .function_config import FunctionConfig
from .types import BaseModel


class RegisterRequest(BaseModel):
    app_name: str = Field(..., serialization_alias="appName")
    framework: str
    functions: list[FunctionConfig]
    sdk: str
    url: str
    v: str
