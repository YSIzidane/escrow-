class DealEngineError(Exception):
    default_reason = "deal_engine_error"

    def __init__(self, reason=None, result=None):
        self.reason = reason or self.default_reason
        self.result = result
        super().__init__(self.reason)


class InvalidTransition(DealEngineError):
    default_reason = "invalid_transition"


class PermissionDeniedForTransition(DealEngineError):
    default_reason = "permission_denied"
