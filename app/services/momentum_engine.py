"""
Tim's Momentum Engine
Ride strength, not hope. Enter on confirmation. Exit on rules.
No feelings. Charts and volume only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class MomentumConfig:
    """Hard gates for sniping momentum — not mean-reversion."""

    min_volume_ratio: float = 1.5          # RVOL gate
    min_momentum_pct: float = 60.0         # Position in 20d range (higher = strength)
    require_price_above_sma20: bool = True
    require_sma20_above_sma50: bool = True
    max_rsi_for_entry: float = 78.0        # Skip melt-up chase
    min_rsi_for_entry: float = 45.0        # No dip-buying
    require_macd_positive: bool = True
    min_confidence: float = 0.55
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 3.0
    atr_stop_multiplier: float = 1.5
    use_atr_stops: bool = True


def _f(indicators: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        val = indicators.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            # macd sometimes nested
            nested = val.get("value") or val.get("macd") or val.get("histogram")
            if nested is not None:
                try:
                    return float(nested)
                except (TypeError, ValueError):
                    continue
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return default


def approximate_vwap_hold(price: float, indicators: Dict[str, Any]) -> bool:
    """
    Prefer true VWAP when present; otherwise use SMA20 as session/trend proxy.
    Momentum rule: do not buy below the volume-weighted plane.
    """
    vwap = _f(indicators, "vwap", "VWAP", default=0.0)
    if vwap > 0:
        return price >= vwap
    sma20 = _f(indicators, "sma_20", "SMA20", "sma20", default=0.0)
    if sma20 > 0:
        return price >= sma20
    return True  # insufficient data — don't hard-block elsewhere


def evaluate_momentum_entry(
    price: float,
    indicators: Dict[str, Any],
    config: Optional[MomentumConfig] = None,
) -> Tuple[str, float, str]:
    """
    Returns (action, confidence, reason).
    BUY only on stacked confirmation. Otherwise HOLD or SELL (fade / exit signal).
    """
    cfg = config or MomentumConfig()
    reasons = []

    if price <= 0:
        return "HOLD", 0.0, "No valid price"

    sma20 = _f(indicators, "sma_20", "SMA20", "sma20")
    sma50 = _f(indicators, "sma_50", "SMA50", "sma50")
    rsi = _f(indicators, "rsi", "rsi_14", "RSI", default=50.0)
    macd = _f(indicators, "macd", "MACD", "macd_histogram", "macd_hist")
    volume_ratio = _f(indicators, "volume_ratio", "rvol", "relative_volume", default=1.0)
    momentum_pct = _f(indicators, "momentum_pct", default=50.0)
    prior_high = _f(indicators, "prior_high", "high_20", "breakout_level", default=0.0)

    # Exit / fade: overextended + weak tape
    if rsi >= 72 and macd < 0:
        return "SELL", 0.65, f"Momentum fade: RSI={rsi:.1f} MACD soft"

    # Entry gates (all must pass for BUY)
    gates_passed = 0
    gates_total = 0

    gates_total += 1
    if approximate_vwap_hold(price, indicators):
        gates_passed += 1
        reasons.append("above VWAP/SMA20")
    else:
        reasons.append("below VWAP/SMA20")

    if cfg.require_price_above_sma20 and sma20 > 0:
        gates_total += 1
        if price > sma20:
            gates_passed += 1
            reasons.append("price>SMA20")
        else:
            reasons.append("price<=SMA20")

    if cfg.require_sma20_above_sma50 and sma20 > 0 and sma50 > 0:
        gates_total += 1
        if sma20 > sma50:
            gates_passed += 1
            reasons.append("SMA20>SMA50")
        else:
            reasons.append("SMA20<=SMA50")

    gates_total += 1
    if volume_ratio >= cfg.min_volume_ratio:
        gates_passed += 1
        reasons.append(f"RVOL={volume_ratio:.2f}")
    else:
        reasons.append(f"weak RVOL={volume_ratio:.2f}")

    gates_total += 1
    if momentum_pct >= cfg.min_momentum_pct:
        gates_passed += 1
        reasons.append(f"mom={momentum_pct:.0f}")
    else:
        reasons.append(f"soft mom={momentum_pct:.0f}")

    if cfg.require_macd_positive:
        gates_total += 1
        if macd > 0:
            gates_passed += 1
            reasons.append("MACD+")
        else:
            reasons.append("MACD flat/neg")

    gates_total += 1
    if cfg.min_rsi_for_entry <= rsi <= cfg.max_rsi_for_entry:
        gates_passed += 1
        reasons.append(f"RSI={rsi:.0f} ok")
    else:
        reasons.append(f"RSI={rsi:.0f} out of band")

    # Optional breakout confirmation when prior high provided
    if prior_high > 0:
        gates_total += 1
        if price >= prior_high:
            gates_passed += 1
            reasons.append("breakout")
        else:
            reasons.append("no breakout")

    score = gates_passed / gates_total if gates_total else 0.0
    # Require nearly full confirmation — Tim does not half-enter
    if score >= 0.85 and gates_passed >= max(4, gates_total - 1):
        confidence = min(0.95, cfg.min_confidence + score * 0.4)
        return "BUY", confidence, "Momentum snipe: " + "; ".join(reasons)

    return "HOLD", score * 0.5, "No snipe: " + "; ".join(reasons)


def compute_stop_and_target(
    entry_price: float,
    indicators: Dict[str, Any],
    config: Optional[MomentumConfig] = None,
) -> Dict[str, float]:
    """Dollar stops from ATR when available, else fixed %."""
    cfg = config or MomentumConfig()
    atr = _f(indicators, "atr", "atr_14", "ATR")
    stop_pct = cfg.stop_loss_pct
    tp_pct = cfg.take_profit_pct

    if cfg.use_atr_stops and atr > 0 and entry_price > 0:
        stop_dist = atr * cfg.atr_stop_multiplier
        # Cap between 0.5% and 5%
        stop_pct = max(0.5, min(5.0, (stop_dist / entry_price) * 100))
        # ~2R target
        tp_pct = max(tp_pct, stop_pct * 2.0)

    stop_price = entry_price * (1 - stop_pct / 100)
    take_profit_price = entry_price * (1 + tp_pct / 100)
    return {
        "stop_loss_pct": round(stop_pct, 3),
        "take_profit_pct": round(tp_pct, 3),
        "stop_loss_price": round(stop_price, 4),
        "take_profit_price": round(take_profit_price, 4),
    }


def risk_based_shares(
    capital: float,
    entry_price: float,
    stop_price: float,
    risk_fraction: float = 0.01,
    max_position_fraction: float = 0.05,
) -> int:
    """
    Size so $ risk ≈ risk_fraction of capital.
    Never exceed max_position_fraction of capital in notional.
    """
    if capital <= 0 or entry_price <= 0 or stop_price <= 0 or stop_price >= entry_price:
        return 0
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return 0
    max_risk_dollars = capital * risk_fraction
    shares_by_risk = int(max_risk_dollars // risk_per_share)
    max_notional_shares = int((capital * max_position_fraction) // entry_price)
    return max(0, min(shares_by_risk, max_notional_shares))
