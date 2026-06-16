from typing import TypeVar

T = TypeVar("T")


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, object] = {}

    def register(self, name: str, service: object) -> None:
        if name in self._services:
            raise ValueError(f"service_already_registered: {name}")
        self._services[name] = service

    def get(self, name: str, expected_type: type[T]) -> T:
        if name not in self._services:
            raise ValueError(f"service_not_registered: {name}")
        service = self._services[name]
        if not isinstance(service, expected_type):
            raise TypeError(
                f"service_type_mismatch: {name} expected "
                f"{expected_type.__name__} got {type(service).__name__}"
            )
        return service

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._services))
