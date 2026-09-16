"""
All monetary arithmetic happens in integer paisa (1 rupee = 100 paisa).
Never do money math in float/Decimal rupees beyond the input boundary --
float rounding errors are exactly the kind of bug this problem statement
is testing for ("total to the exact paisa").
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List


def rupees_to_paisa(amount) -> int:
    """Convert a rupee amount (str/float/Decimal/int) to integer paisa."""
    d = Decimal(str(amount))
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paisa_to_rupees_str(paisa: int) -> str:
    """Format integer paisa as a '1234.56' rupee string for display."""
    d = (Decimal(paisa) / 100).quantize(Decimal("0.01"))
    return f"{d:.2f}"


def round_half_up(x: float) -> int:
    """Round a float paisa value to the nearest integer paisa, half-up.
    (Python's builtin round() is banker's rounding -- wrong for money.)"""
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allocate(total: int, weights: List[int]) -> List[int]:
    """
    Split an integer `total` (paisa) across `weights` (proportionally),
    such that the parts are all integers and sum EXACTLY to `total`.

    Uses the largest-remainder method: floor each proportional share,
    then hand out the leftover paisa one-by-one to the shares with the
    biggest fractional remainder. This is how you keep a discount/tax
    allocation exact to the paisa across multiple line items instead of
    drifting by a paisa or two from naive per-line rounding.
    """
    n = len(weights)
    if n == 0 or total == 0:
        return [0] * n
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0] * n

    raw = [total * w / weight_sum for w in weights]
    floors = [int(r) for r in raw]
    remainder = total - sum(floors)

    order = sorted(range(n), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[order[i]] += 1
    return floors
