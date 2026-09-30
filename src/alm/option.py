"""European option models with Black-Scholes-Merton pricing.

All options are European-style (exercise at expiry only).

# TODO: Add American option support via binomial tree or finite difference methods.
#       American puts have early exercise premium not captured by BSM.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from scipy.optimize import brentq
from scipy.stats import norm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Black-Scholes-Merton building blocks
# ---------------------------------------------------------------------------


def _d1(S: float, K: float, T: float, r: float, sigma: float, q: float) -> float:
    """BSM d1 term."""
    return (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float, q: float) -> float:
    """BSM d2 term."""
    return _d1(S, K, T, r, sigma, q) - sigma * math.sqrt(T)


# ---------------------------------------------------------------------------
# Standalone pricing functions
# ---------------------------------------------------------------------------


def bs_call(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """Black-Scholes-Merton price of a European call option.

    Parameters
    ----------
    S : float
        Current underlying price.
    K : float
        Strike price.
    T : float
        Time to expiry in years.
    r : float
        Continuously compounded risk-free rate (decimal).
    sigma : float
        Annualised volatility of the underlying (decimal).
    q : float
        Continuously compounded dividend yield (decimal). Default 0.

    Returns
    -------
    float
        Call option price.

    Examples
    --------
    >>> round(bs_call(100, 100, 1.0, 0.05, 0.20), 4)
    10.4506
    """
    if T <= 0:
        return max(S - K, 0.0)
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_put(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """Black-Scholes-Merton price of a European put option.

    Parameters
    ----------
    S : float
        Current underlying price.
    K : float
        Strike price.
    T : float
        Time to expiry in years.
    r : float
        Continuously compounded risk-free rate (decimal).
    sigma : float
        Annualised volatility of the underlying (decimal).
    q : float
        Continuously compounded dividend yield (decimal). Default 0.

    Returns
    -------
    float
        Put option price.

    Examples
    --------
    >>> round(bs_put(100, 100, 1.0, 0.05, 0.20), 4)
    5.5735
    """
    if T <= 0:
        return max(K - S, 0.0)
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0
) -> dict[str, float]:
    """All BSM Greeks for both a call and put on the same underlying.

    Parameters
    ----------
    S : float
        Current underlying price.
    K : float
        Strike price.
    T : float
        Time to expiry in years.
    r : float
        Continuously compounded risk-free rate (decimal).
    sigma : float
        Annualised volatility of the underlying (decimal).
    q : float
        Continuously compounded dividend yield (decimal). Default 0.

    Returns
    -------
    dict[str, float]
        Keys: call_delta, put_delta, gamma, vega, call_theta, put_theta,
        call_rho, put_rho.  Vega and gamma are identical for calls and puts.

    Notes
    -----
    - Theta is expressed as value change *per calendar day* (divide by 365).
    - Vega is expressed per 1 % move in volatility (multiply raw vega by 0.01).
    - Rho is expressed per 1 % move in the risk-free rate.
    """
    if T <= 0:
        return {
            "call_delta": 1.0 if S > K else 0.0,
            "put_delta": -1.0 if S < K else 0.0,
            "gamma": 0.0,
            "vega": 0.0,
            "call_theta": 0.0,
            "put_theta": 0.0,
            "call_rho": 0.0,
            "put_rho": 0.0,
        }

    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    sqrt_T = math.sqrt(T)
    exp_qT = math.exp(-q * T)
    exp_rT = math.exp(-r * T)
    pdf_d1 = norm.pdf(d1)

    call_delta = exp_qT * norm.cdf(d1)
    put_delta = exp_qT * (norm.cdf(d1) - 1)
    gamma = exp_qT * pdf_d1 / (S * sigma * sqrt_T)
    # Raw vega (per unit vol); scale by 0.01 for "per 1 % vol move"
    vega = S * exp_qT * pdf_d1 * sqrt_T * 0.01
    # Theta per calendar day
    call_theta = (
        (-S * exp_qT * pdf_d1 * sigma / (2 * sqrt_T))
        - r * K * exp_rT * norm.cdf(d2)
        + q * S * exp_qT * norm.cdf(d1)
    ) / 365
    put_theta = (
        (-S * exp_qT * pdf_d1 * sigma / (2 * sqrt_T))
        + r * K * exp_rT * norm.cdf(-d2)
        - q * S * exp_qT * norm.cdf(-d1)
    ) / 365
    # Rho per 1 % rate move
    call_rho = K * T * exp_rT * norm.cdf(d2) * 0.01
    put_rho = -K * T * exp_rT * norm.cdf(-d2) * 0.01

    return {
        "call_delta": call_delta,
        "put_delta": put_delta,
        "gamma": gamma,
        "vega": vega,
        "call_theta": call_theta,
        "put_theta": put_theta,
        "call_rho": call_rho,
        "put_rho": put_rho,
    }


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str,
    q: float = 0.0,
    tol: float = 1e-6,
) -> float:
    """Implied volatility from a market option price using Brent's method.

    Parameters
    ----------
    market_price : float
        Observed market price of the option.
    S : float
        Current underlying price.
    K : float
        Strike price.
    T : float
        Time to expiry in years.
    r : float
        Continuously compounded risk-free rate (decimal).
    option_type : str
        ``"call"`` or ``"put"``.
    q : float
        Continuously compounded dividend yield (decimal). Default 0.
    tol : float
        Solver tolerance. Default 1e-6.

    Returns
    -------
    float
        Implied volatility as a decimal (e.g. 0.20 for 20 %).

    Raises
    ------
    ValueError
        If ``option_type`` is not ``"call"`` or ``"put"``, or if no implied
        volatility can be found in [1e-6, 10.0] (e.g. price violates
        arbitrage bounds).
    """
    option_type = option_type.lower()
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    pricer = bs_call if option_type == "call" else bs_put

    def objective(sigma: float) -> float:
        return pricer(S, K, T, r, sigma, q) - market_price

    try:
        return brentq(objective, 1e-6, 10.0, xtol=tol)
    except ValueError as exc:
        raise ValueError(
            f"Could not find implied vol for {option_type} price={market_price} "
            f"(S={S}, K={K}, T={T}, r={r}, q={q}). "
            "Price may violate arbitrage bounds."
        ) from exc


# ---------------------------------------------------------------------------
# Option dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _Option:
    """Base class for European options.

    Not intended to be instantiated directly — use :class:`CallOption` or
    :class:`PutOption`.

    Parameters
    ----------
    spot : float
        Current underlying price (S).
    strike : float
        Exercise price (K).
    time_to_expiry : float
        Time to expiry in years (T).
    risk_free_rate : float
        Continuously compounded risk-free rate as a decimal (r).
    volatility : float
        Annualised volatility of the underlying as a decimal (σ).
    dividend_yield : float
        Continuously compounded dividend yield as a decimal (q). Default 0.
    """

    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    dividend_yield: float = 0.0

    # Subclasses set this to "call" or "put"
    _option_type: str = field(default="", init=False, repr=False)

    @property
    def _pricer(self):
        return bs_call if self._option_type == "call" else bs_put

    def price(self) -> float:
        """BSM option price."""
        return self._pricer(
            self.spot,
            self.strike,
            self.time_to_expiry,
            self.risk_free_rate,
            self.volatility,
            self.dividend_yield,
        )

    def greeks(self) -> dict[str, float]:
        """All BSM Greeks. See :func:`bs_greeks` for key descriptions."""
        return bs_greeks(
            self.spot,
            self.strike,
            self.time_to_expiry,
            self.risk_free_rate,
            self.volatility,
            self.dividend_yield,
        )

    def delta(self) -> float:
        """Price sensitivity to a unit move in the underlying (∂V/∂S)."""
        g = self.greeks()
        return g["call_delta"] if self._option_type == "call" else g["put_delta"]

    def gamma(self) -> float:
        """Second-order price sensitivity to underlying moves (∂²V/∂S²)."""
        return self.greeks()["gamma"]

    def vega(self) -> float:
        """Price sensitivity per 1 % move in volatility (∂V/∂σ · 0.01)."""
        return self.greeks()["vega"]

    def theta(self) -> float:
        """Price decay per calendar day (∂V/∂t · 1/365)."""
        g = self.greeks()
        return g["call_theta"] if self._option_type == "call" else g["put_theta"]

    def rho(self) -> float:
        """Price sensitivity per 1 % move in the risk-free rate (∂V/∂r · 0.01)."""
        g = self.greeks()
        return g["call_rho"] if self._option_type == "call" else g["put_rho"]

    def implied_vol(self, market_price: float) -> float:
        """Implied volatility given an observed market price.

        Parameters
        ----------
        market_price : float
            Observed market price of this option.

        Returns
        -------
        float
            Implied volatility as a decimal.
        """
        return implied_vol(
            market_price,
            self.spot,
            self.strike,
            self.time_to_expiry,
            self.risk_free_rate,
            self._option_type,
            self.dividend_yield,
        )


@dataclass
class CallOption(_Option):
    """European call option priced with Black-Scholes-Merton.

    Parameters
    ----------
    spot : float
        Current underlying price (S).
    strike : float
        Exercise price (K).
    time_to_expiry : float
        Time to expiry in years (T).
    risk_free_rate : float
        Continuously compounded risk-free rate as a decimal (r).
    volatility : float
        Annualised volatility of the underlying as a decimal (σ).
    dividend_yield : float
        Continuously compounded dividend yield as a decimal (q). Default 0.

    Examples
    --------
    >>> c = CallOption(spot=100, strike=100, time_to_expiry=1.0,
    ...                risk_free_rate=0.05, volatility=0.20)
    >>> round(c.price(), 4)
    10.4506
    >>> round(c.delta(), 4)
    0.6368
    """

    def __post_init__(self):
        self._option_type = "call"


@dataclass
class PutOption(_Option):
    """European put option priced with Black-Scholes-Merton.

    Parameters
    ----------
    spot : float
        Current underlying price (S).
    strike : float
        Exercise price (K).
    time_to_expiry : float
        Time to expiry in years (T).
    risk_free_rate : float
        Continuously compounded risk-free rate as a decimal (r).
    volatility : float
        Annualised volatility of the underlying as a decimal (σ).
    dividend_yield : float
        Continuously compounded dividend yield as a decimal (q). Default 0.

    Examples
    --------
    >>> p = PutOption(spot=100, strike=100, time_to_expiry=1.0,
    ...               risk_free_rate=0.05, volatility=0.20)
    >>> round(p.price(), 4)
    5.5735
    >>> round(p.delta(), 4)
    -0.3632
    """

    def __post_init__(self):
        self._option_type = "put"
