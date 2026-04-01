"""Generic Result / Success / Failure types for pyclaude operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True)
class Success(Generic[T]):
    """Represents a successful operation carrying a value of type *T*."""

    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:  # type: ignore[override]
        return self.value

    def map(self, fn: Callable[[T], U]) -> Result[U, Any]:
        return Success(fn(self.value))

    def flat_map(self, fn: Callable[[T], Result[U, Any]]) -> Result[U, Any]:
        return fn(self.value)

    def __repr__(self) -> str:
        return f"Success({self.value!r})"


@dataclass(frozen=True)
class Failure(Generic[E]):
    """Represents a failed operation carrying an error of type *E*."""

    error: E
    context: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Any:
        raise RuntimeError(f"Called unwrap on a Failure: {self.error}")

    def unwrap_or(self, default: Any) -> Any:
        return default

    def map(self, fn: Callable[..., Any]) -> Failure[E]:
        return self  # propagate failure unchanged

    def flat_map(self, fn: Callable[..., Any]) -> Failure[E]:
        return self

    def __repr__(self) -> str:
        ctx = f", context={self.context!r}" if self.context else ""
        return f"Failure({self.error!r}{ctx})"


# The union type callers should use for annotations.
Result = Union[Success[T], Failure[E]]


# ---------------------------------------------------------------------------
# Helper constructors
# ---------------------------------------------------------------------------

def ok(value: T) -> Success[T]:
    """Shorthand for ``Success(value)``."""
    return Success(value)


def err(error: E, context: Optional[str] = None) -> Failure[E]:
    """Shorthand for ``Failure(error, context)``."""
    return Failure(error, context)


def from_exception(fn: Callable[..., T], *args: Any, **kwargs: Any) -> Result[T, str]:
    """Call *fn* and wrap the return in ``Success`` or any exception in ``Failure``."""
    try:
        return Success(fn(*args, **kwargs))
    except Exception as exc:
        return Failure(str(exc), context=type(exc).__name__)
