#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""statcheck-style consistency check of reported test statistics vs p-values (pure Python).

Vendored from academic-peer-review (skills/paper-review/scripts/stat_and_integrity_audit.py,
commit 71fb74c): p-value recalculation, statistic patterns and `run_statcheck`. Keep in sync
by hand when the upstream implementation changes.
"""

from __future__ import annotations

import math
import re
from typing import Any


def _norm_two_tailed_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def _betacf(a: float, b: float, x: float) -> float:
    max_iter = 200
    eps = 3.0e-12
    fpmin = 1.0e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        rm = d * c
        h *= rm
        if abs(rm - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _gammaincc(a: float, x: float) -> float:
    if x <= 0.0:
        return 1.0
    if a <= 0.0:
        return 0.0
    if x < a + 1.0:
        ap = a
        total = 1.0 / a
        del_val = total
        for _ in range(200):
            ap += 1.0
            del_val *= x / ap
            total += del_val
            if abs(del_val) < abs(total) * 3.0e-12:
                break
        p = total * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return max(0.0, 1.0 - p)
    fpmin = 1.0e-30
    b = x + 1.0 - a
    c = 1.0 / fpmin
    d = 1.0 / b
    h = d
    for i in range(1, 200):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < fpmin:
            d = fpmin
        c = b + an / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        del_val = d * c
        h *= del_val
        if abs(del_val - 1.0) < 3.0e-12:
            break
    return max(0.0, min(1.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h))


def calc_p_value(stat_type: str, stat_val: float, df1: float, df2: float | None = None) -> float | None:
    try:
        if stat_type == "z":
            return _norm_two_tailed_p(stat_val)
        if stat_type == "t":
            if df1 <= 0:
                return None
            x = df1 / (df1 + stat_val * stat_val)
            return _betainc(0.5 * df1, 0.5, x)
        if stat_type == "F":
            if df1 <= 0 or not df2 or df2 <= 0 or stat_val < 0:
                return None
            x = df2 / (df2 + df1 * stat_val)
            return _betainc(0.5 * df2, 0.5 * df1, x)
        if stat_type == "r":
            if df1 <= 0 or abs(stat_val) >= 1.0:
                return 0.0 if abs(stat_val) >= 1.0 else None
            t_val = abs(stat_val) * math.sqrt(df1 / (1.0 - stat_val * stat_val))
            x = df1 / (df1 + t_val * t_val)
            return _betainc(0.5 * df1, 0.5, x)
        if stat_type == "chi2":
            if df1 <= 0 or stat_val < 0:
                return None
            return _gammaincc(0.5 * df1, 0.5 * stat_val)
    except Exception:
        return None
    return None


# Numbers accept a decimal point or a decimal comma (Portuguese/Spanish manuscripts), and the
# p label may be lowercase (APA) or uppercase (many medical journals).
_NUM = r"[+-]?\d+(?:[.,]\d+)?"
_PVAL = r"(\d*[.,]?\d+(?:[eE][+-]?\d+)?)"
_P_TAIL = r"\s*[,;]\s*[pP]\s*([=<>≤≥])\s*" + _PVAL

STAT_PATTERNS = [
    ("t", re.compile(r"\bt\s*\(\s*(\d+(?:[.,]\d+)?)\s*\)\s*=\s*(" + _NUM + ")" + _P_TAIL)),
    (
        "F",
        re.compile(
            r"\bF\s*\(\s*(\d+(?:\.\d+)?)\s*[,;]\s*(\d+(?:\.\d+)?)\s*\)\s*=\s*(" + _NUM + ")" + _P_TAIL
        ),
    ),
    ("r", re.compile(r"\br\s*\(\s*(\d+(?:[.,]\d+)?)\s*\)\s*=\s*([+-]?0?[.,]\d+)" + _P_TAIL)),
    (
        "chi2",
        re.compile(
            r"(?:χ2|χ\^2|chi2|chi-square[d]?)\s*\(\s*(\d+(?:[.,]\d+)?)(?:\s*[,;]\s*[Nn]\s*=\s*\d+)?\s*\)\s*=\s*("
            + _NUM + ")" + _P_TAIL,
            re.IGNORECASE,
        ),
    ),
    ("z", re.compile(r"\b[zZ]\s*=\s*(" + _NUM + ")" + _P_TAIL)),
]

STANDALONE_P_REGEX = re.compile(
    r"\b[pP]\s*([=<>≤≥])\s*(0?[.,]\d+(?:[eE][+-]?\d+)?|\d+(?:\.\d+)?[eE][+-]?\d+)\b"
)


def _num(value: str) -> float:
    return float(value.replace(",", "."))


def _decimals(value: str) -> int:
    """Number of reported decimal places (0 for integers or scientific notation)."""
    mantissa = re.split(r"[eE]", value)[0]
    sep = max(mantissa.rfind("."), mantissa.rfind(","))
    return len(mantissa) - sep - 1 if sep >= 0 else 0


def normalize_stats_text(text: str) -> str:
    """Undo PDF-extraction artefacts that hide test statistics from the regexes."""
    return (
        text.replace("\u2212", "-")  # Unicode minus sign
        .replace("χ²", "χ2")
        .replace("Χ²", "χ2")
        .replace("chi²", "chi2")
    )


def run_statcheck(text: str, alpha: float = 0.05) -> dict[str, Any]:
    results = []
    inconsistencies = []
    decision_errors = []
    text = normalize_stats_text(text)

    for stat_type, pattern in STAT_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(0)
            try:
                if stat_type == "F":
                    df1 = _num(m.group(1))
                    df2 = _num(m.group(2))
                    stat_val = _num(m.group(3))
                    op = m.group(4)
                    reported_p = _num(m.group(5))
                elif stat_type == "z":
                    df1 = 0.0
                    df2 = None
                    stat_val = _num(m.group(1))
                    op = m.group(2)
                    reported_p = _num(m.group(3))
                else:
                    df1 = _num(m.group(1))
                    df2 = None
                    stat_val = _num(m.group(2))
                    op = m.group(3)
                    reported_p = _num(m.group(4))
            except ValueError:
                continue
            if not 0.0 <= reported_p <= 1.0:
                continue

            recalc_p = calc_p_value(stat_type, stat_val, df1, df2)
            if recalc_p is None:
                continue

            # statcheck-style rounding tolerance: the reported statistic stands for an interval
            # (e.g. 1.96 = [1.955, 1.965]) and the reported p for its own rounding interval.
            stat_str = m.group(3) if stat_type == "F" else (m.group(1) if stat_type == "z" else m.group(2))
            p_str = m.group(5) if stat_type == "F" else (m.group(3) if stat_type == "z" else m.group(4))
            stat_half = 0.5 * 10 ** -_decimals(stat_str)
            p_half = 0.5 * 10 ** -_decimals(p_str) if op == "=" else 0.0
            abs_stat = abs(stat_val)
            upper_stat = abs_stat + stat_half
            lower_stat = max(0.0, abs_stat - stat_half)
            if stat_type == "r":
                upper_stat = min(upper_stat, 0.999999)
            p_low = calc_p_value(stat_type, upper_stat, df1, df2)
            p_high = calc_p_value(stat_type, lower_stat, df1, df2)
            if p_low is None or p_high is None:
                p_low = p_high = recalc_p

            is_inconsistent = False
            if op == "=":
                is_inconsistent = reported_p + p_half < p_low or reported_p - p_half > p_high
            elif op in ("<", "≤"):
                is_inconsistent = p_low > reported_p
            elif op in (">", "≥"):
                is_inconsistent = p_high < reported_p

            if op in (">", "≥"):
                # "p > x" never asserts significance (e.g. "p > .01" is not a significant result).
                reported_sig = False
            else:
                reported_sig = (reported_p < alpha) or (op in ("<", "≤") and reported_p <= alpha)
            actual_sig = recalc_p < alpha
            # As in statcheck, a decision error is an inconsistency that also flips significance.
            is_decision_error = is_inconsistent and reported_sig != actual_sig

            entry = {
                "raw": raw,
                "type": stat_type,
                "reported_p": reported_p,
                "operator": op,
                "recalculated_p_two_tailed": round(recalc_p, 6),
                "inconsistent": is_inconsistent,
                "decision_error_at_005": is_decision_error,
            }
            results.append(entry)
            if is_inconsistent:
                inconsistencies.append(entry)
            if is_decision_error:
                decision_errors.append(entry)

    fragile_p = []
    for m in STANDALONE_P_REGEX.finditer(text):
        op, val_str = m.group(1), m.group(2)
        try:
            p_val = _num(val_str)
        except ValueError:
            continue
        # "p = .03" / "p ≤ .03" are fragile; "p < .01" is not (it only says p is below .01).
        if (op in ("=", "≤") and 0.01 <= p_val < 0.05) or (op == "<" and 0.01 < p_val < 0.05):
            fragile_p.append(m.group(0))

    return {
        "tests_checked": len(results),
        "inconsistencies_count": len(inconsistencies),
        "decision_errors_count": len(decision_errors),
        "inconsistencies": inconsistencies[:20],
        "decision_errors": decision_errors[:20],
        "fragile_p_values_001_to_005_count": len(fragile_p),
        "fragile_p_examples": fragile_p[:15],
    }


