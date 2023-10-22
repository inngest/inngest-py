class InngestError(Exception):
    pass


class InvalidBaseURL(Exception):
    code = "invalid_base_url"


class InvalidRequestSignature(Exception):
    code = "invalid_request_signature"


class InvalidResponseShape(Exception):
    code = "invalid_response_shape"


class MissingEventKey(Exception):
    code = "missing_event_key"


class MissingHeader(Exception):
    code = "missing_header"


class MissingSigningKey(Exception):
    code = "missing_signing_key"


class NonRetriableError(Exception):
    code = "non_retriable_error"
