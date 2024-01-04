import enum

import pydantic

from . import const, function_config, types


class DeployType(enum.Enum):
    PING = "ping"


class RegisterRequest(types.BaseModel):
    app_name: str = pydantic.Field(..., serialization_alias="appname")
    deploy_type: DeployType
    framework: const.Framework
    functions: list[function_config.FunctionConfig] = pydantic.Field(
        min_length=1
    )
    sdk: str
    url: str
    v: str
