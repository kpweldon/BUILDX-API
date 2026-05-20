class DescriptAPIError(Exception):
    def __init__(self, status: int, message: str, body: object = None):
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.body = body


class DescriptAuthError(DescriptAPIError):
    pass


class DescriptRateLimitError(DescriptAPIError):
    pass
