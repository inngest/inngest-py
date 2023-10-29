from enum import Enum

from pydantic import Field

from . import function_config, types


class DeployType(Enum):
    PING = "ping"


class RegisterRequest(types.BaseModel):
    app_name: str
    deploy_type: DeployType
    framework: str
    functions: list[function_config.FunctionConfig] = Field(min_length=1)
    sdk: str
    url: str
    v: str
