from __future__ import annotations


class ForgeError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ValidationError(ForgeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=2)


class DockerUnavailableError(ForgeError):
    pass


class ContainerRuntimeError(ForgeError):
    pass
