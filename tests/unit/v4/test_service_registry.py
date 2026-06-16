import pytest

from homllm_v4.registry.service_registry import ServiceRegistry


class DemoService:
    pass


class OtherService:
    pass


def test_register_and_get_typed_service() -> None:
    registry = ServiceRegistry()
    service = DemoService()

    registry.register("demo", service)

    assert registry.get("demo", DemoService) is service
    assert registry.names() == ("demo",)


def test_duplicate_registration_fails() -> None:
    registry = ServiceRegistry()
    registry.register("demo", DemoService())

    with pytest.raises(ValueError, match="service_already_registered"):
        registry.register("demo", DemoService())


def test_missing_lookup_fails() -> None:
    registry = ServiceRegistry()

    with pytest.raises(ValueError, match="service_not_registered"):
        registry.get("missing", DemoService)


def test_wrong_expected_type_fails() -> None:
    registry = ServiceRegistry()
    registry.register("demo", DemoService())

    with pytest.raises(TypeError, match="service_type_mismatch"):
        registry.get("demo", OtherService)


def test_names_are_stable_sorted_tuple() -> None:
    registry = ServiceRegistry()

    registry.register("zeta", DemoService())
    registry.register("alpha", DemoService())
    registry.register("middle", DemoService())

    assert registry.names() == ("alpha", "middle", "zeta")
