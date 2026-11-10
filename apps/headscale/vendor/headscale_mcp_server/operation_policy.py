"""Headscale's reviewed operation selectors, independent of either admin core."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OperationSpec:
    operations: tuple[str, ...]
    parameter: str | None = None
    default: str | None = None
    includes: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def requirements(self, operation: str) -> set[str]:
        return {operation, *self.includes.get(operation, ())}

    def denied(self, operations) -> set[str]:
        return set(operations)

    def resolve(self, arguments) -> set[str] | None:
        if not isinstance(arguments, dict):
            return None
        if self.parameter is None:
            operation = self.default
        else:
            operation = arguments.get(self.parameter)
        if type(operation) is not str or operation not in self.operations:
            return None
        return self.requirements(operation)
