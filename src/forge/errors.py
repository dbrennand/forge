from __future__ import annotations


class ForgeError(Exception):
    """Base exception for user-facing Forge failures."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        """Initialize a Forge error with an exit status.

        Args:
            message: Human-readable error message.
            exit_code: Process exit code associated with the error.
        """
        super().__init__(message)
        self.exit_code = exit_code


class ValidationError(ForgeError):
    """Raised when user input or host configuration fails validation."""

    def __init__(self, message: str) -> None:
        """Initialize a validation error with the validation exit code.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, exit_code=2)


class DockerUnavailableError(ForgeError):
    """Raised when Forge cannot reach the Docker daemon."""

    pass


class ContainerRuntimeError(ForgeError):
    """Raised when Docker fails during container lifecycle operations."""

    pass
