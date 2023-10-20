from .function_config import FunctionConfig
from .types import BaseModel


class RegisterRequest(BaseModel):
    app_name: str
    framework: str
    functions: list[FunctionConfig]
    hash: str
    sdk: str
    url: str
    v: str
