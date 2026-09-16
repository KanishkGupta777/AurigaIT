from pricing.money import rupees_to_paisa, paisa_to_rupees_str, allocate, round_half_up


def test_rupees_to_paisa_basic():
    assert rupees_to_paisa(150) == 15000
    assert rupees_to_paisa(99.5) == 9950
    assert rupees_to_paisa("20.25") == 2025


def test_round_half_up_not_bankers_rounding():
    # Python's builtin round(2.5) == 2 (banker's rounding) -- wrong for money.
    assert round_half_up(2.5) == 3
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2  # half-up, not half-to-even


def test_allocate_sums_exactly_even_with_remainder():
    # 100 paisa split 3 ways by equal weight -> can't divide evenly (33.33 each)
    result = allocate(100, [1, 1, 1])
    assert sum(result) == 100
    assert result == [34, 33, 33]  # remainder goes to first by tie-break order


def test_allocate_proportional():
    result = allocate(1000, [3, 1])  # 3:1 ratio
    assert sum(result) == 1000
    assert result == [750, 250]


def test_allocate_zero_total():
    assert allocate(0, [5, 5]) == [0, 0]


def test_allocate_single_weight():
    assert allocate(999, [1]) == [999]


def test_paisa_to_rupees_str_formats_two_decimals():
    assert paisa_to_rupees_str(15000) == "150.00"
    assert paisa_to_rupees_str(9950) == "99.50"
    assert paisa_to_rupees_str(1) == "0.01"
