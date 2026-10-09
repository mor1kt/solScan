import pytest

from src.outcomes import calculate_return


@pytest.mark.parametrize(
    ("initial", "current", "expected"),
    [(100, 125, 25), (100, 50, -50), (100, 0, -100), (None, 10, None), (0, 10, None)],
)
def test_calculate_return(initial, current, expected) -> None:
    assert calculate_return(initial, current) == expected
