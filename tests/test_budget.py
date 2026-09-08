import pytest

from app.services.budget import ContextBudget


def test_input_allocation_reserves_output_and_margin() -> None:
    assert ContextBudget(8192, 2048, 1024).input_tokens == 5120


@pytest.mark.parametrize("values", [(0, 1, 1), (100, 0, 1), (100, 1, 0), (100, 90, 10)])
def test_invalid_allocation(values: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        ContextBudget(*values)
