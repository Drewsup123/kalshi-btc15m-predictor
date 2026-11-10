"""Distance-to-strike Brownian / normal-CDF baseline. No future bars."""

from __future__ import annotations

import math

EPS = 1e-12


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))


def realized_sigma(closes: list[float], n: int) -> float | None:
    if len(closes) < 2:
        return None
    take = min(int(n), len(closes) - 1)
    rets = []
    for i in range(1, take + 1):
        a = float(closes[-1 - i])
        b = float(closes[-i])
        if a > 0 and b > 0:
            rets.append(math.log(b / a))
    if not rets:
        return None
    return math.sqrt(sum(r * r for r in rets) / len(rets))


def p_yes_brownian(
    r_t: float | None,
    s_t: float | None,
    sigma: float | None,
    tau_minutes: float,
) -> tuple[float | None, float | None]:
    if r_t is None or s_t is None or sigma is None:
        return None, None
    if r_t <= 0 or s_t <= 0:
        return None, None
    tau = max(float(tau_minutes), 1.0 / 60.0)
    sig = max(float(sigma), EPS)
    z = math.log(r_t / s_t) / (sig * math.sqrt(tau))
    return norm_cdf(z), z
