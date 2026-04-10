from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.account import Account, Contact


def test_reachability_hint_optional() -> None:
    a = Account(
        account_id=1,
        company="C",
        industry="Health system",
        us_employees=5000,
        contact=Contact(),
    )
    assert a.reachability_hint is None


@pytest.mark.parametrize("bad", [-1, 101])
def test_reachability_hint_bounds(bad: int) -> None:
    with pytest.raises(ValidationError):
        Account(
            account_id=1,
            company="C",
            industry="Health system",
            us_employees=5000,
            contact=Contact(),
            reachability_hint=bad,
        )


def test_reachability_hint_valid_range() -> None:
    a = Account(
        account_id=1,
        company="C",
        industry="Health system",
        us_employees=5000,
        contact=Contact(),
        reachability_hint=50,
    )
    assert a.reachability_hint == 50
