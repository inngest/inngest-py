from enum import Enum

from pydantic import Field

from .function_config import FunctionConfig
from .types import BaseModel


class DeployType(Enum):
    PING = "ping"


class RegisterRequest(BaseModel):
    app_name: str
    deploy_type: DeployType
    framework: str
    functions: list[FunctionConfig] = Field(min_length=1)
    sdk: str
    url: str
    v: str
