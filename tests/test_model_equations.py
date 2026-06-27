import pytest

from analytical_models import (
    chu_lmax,
    cirpka_domain_length,
    cirpka_lmax,
    ham_lmax,
    liedl_domain_length,
    liedl_lmax,
    liedl3d_lmax,
)
from empirical_models import birla_lmax, maier_lmax


@pytest.mark.parametrize(
    ("equation", "args", "expected"),
    [
        (liedl_lmax, (3.5, 0.001, 3.5, 8.0, 5.0), 6954.61186817383),
        (chu_lmax, (2.0, 0.01, 1.5, 8.0, 5.0, 0.0), 69.02913545485386),
        (ham_lmax, (5.0, 0.01, 3.5, 8.0, 5.0), 951.9765883182215),
        (liedl3d_lmax, (10.0, 0.01, 0.01, 7.0, 0.5, 8.0, 5.0, 3.0), 2812.579673018557),
        (cirpka_lmax, (10.0, 0.1, 3.5, 8.0, 5.0), 766.1749639695388),  # erfinv (Orlando), was erfcinv
        (maier_lmax, (5.0, 0.01, 3.5, 8.0, 5.0), 1580.863715550744),
        (birla_lmax, (2.0, 0.001, 3.5, 8.0, 5.0, 1.0), 2129.668933744322),
    ],
)
def test_known_equation_outputs(equation, args, expected):
    assert equation(*args) == pytest.approx(expected)


def test_cirpka_domain_length_is_one_and_a_half_times_lmax():
    assert cirpka_domain_length(123.16162908381922) == pytest.approx(184.74244362572884)


@pytest.mark.parametrize("domain_length", [cirpka_domain_length, liedl_domain_length])
def test_automatic_domain_length_matches_old_explicit_path(domain_length):
    lmax = 123.16162908381922
    old_explicit_ld = 1.5 * lmax

    assert domain_length(lmax) == pytest.approx(old_explicit_ld)
    assert domain_length(lmax, old_explicit_ld) == pytest.approx(old_explicit_ld)
    assert domain_length(lmax, 0) == pytest.approx(old_explicit_ld)


def test_domain_length_accepts_positive_power_user_override():
    assert cirpka_domain_length(123.16162908381922, 250.0) == pytest.approx(250.0)


def test_domain_length_rejects_negative_override():
    with pytest.raises(ValueError, match="override LD must be positive"):
        liedl_domain_length(123.16162908381922, -1.0)
