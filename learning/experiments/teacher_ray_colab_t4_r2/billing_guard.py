"""Responsive account checks with explicit allowance for delayed CU balance.

An unchanged balance does not prove a stale response or zero charges. Admission
uses exact owned T4 identity, bounded requests, positive quoted rate, a fixed
rate ceiling and continuous elapsed time. Estimates are conservative under that
ceiling; Google's unversioned meter cannot establish a hard billing guarantee.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    maximum_assigned_seconds: int = 900
    teardown_reserve_seconds: int = 120
    discovery_seconds: int = 120
    maximum_rate_CU_per_hour: float = 3.0
    maximum_debit_CU: float = 8.0
    stop_work_debit_CU: float = 6.0
    maximum_request_seconds: int = 15


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


class BillingGuard:
    def __init__(self, initial_balance, allocation_start, config=Config()):
        if config != Config():
            raise ValueError("DODGE-059 billing limits may not be relaxed")
        if not finite_number(allocation_start):
            raise ValueError("Allocation clock unavailable")
        if not finite_number(initial_balance) or initial_balance < config.maximum_debit_CU:
            raise ValueError("Existing compute-unit balance unavailable/insufficient")
        self.initial_balance = self.last_balance = initial_balance
        self.allocation_start = self.last_observed = allocation_start
        self.progress_seen = False
        self.admitted = False
        self.config = config

    def observe(self, raw, assignments, owned_endpoint, now, *, request_started,
                fixtures_started=False):
        if not finite_number(now) or now < self.last_observed:
            raise ValueError("Billing observation clock reversed")
        if not finite_number(request_started) or not 0 <= now - request_started <= self.config.maximum_request_seconds:
            raise ValueError("Stale/overlong billing request")
        elapsed = now - self.allocation_start
        if elapsed >= self.config.maximum_assigned_seconds - self.config.teardown_reserve_seconds:
            raise ValueError("Assignment work deadline;120s reserved for receipt/teardown")
        if not self.admitted and elapsed > self.config.discovery_seconds:
            raise ValueError("Rate discovery exceeded120s")
        balance, rate, count = (raw.get(key) for key in
                               ("currentBalance", "consumptionRateHourly", "assignmentsCount"))
        if not finite_number(balance) or balance < 0 or not finite_number(rate) or not 0 < rate <= self.config.maximum_rate_CU_per_hour:
            raise ValueError("Unavailable/zero/nonfinite/over-ceiling live CU/hour rate or balance")
        if type(count) is not int or count != 1 or len(assignments) != 1:
            raise ValueError("Exactly one live assignment required")
        assignment = assignments[0]
        if assignment.get("endpoint") != owned_endpoint or assignment.get("accelerator") != "T4":
            raise ValueError("Exact owned T4 assignment required")
        if balance > self.last_balance:
            raise ValueError("Billing balance rose; debit accounting incoherent")
        self.progress_seen = self.progress_seen or balance < self.last_balance
        debit = self.initial_balance - balance
        # Adding the whole elapsed ceiling estimate deliberately double-counts
        # already reported cost. Delayed balance updates cannot lower it.
        unreported = elapsed * self.config.maximum_rate_CU_per_hour / 3600
        accounted = debit + unreported
        if accounted >= self.config.stop_work_debit_CU:
            raise ValueError("Estimated/observed6CU work cutoff;2CU teardown headroom")
        projected = accounted + max(0, self.config.maximum_assigned_seconds - elapsed) * self.config.maximum_rate_CU_per_hour / 3600
        if projected > self.config.maximum_debit_CU:
            raise ValueError("Projected assigned-runtime debit exceeds8CU")
        self.last_balance = balance; self.last_observed = now
        self.admitted = True
        return {"fixtures_admitted": True, "observed_debit_CU": debit,
                "live_rate_CU_per_hour": rate, "projected_total_CU": projected,
                "elapsed_assigned_seconds_upper_bound": elapsed,
                "balance_progress_seen": self.progress_seen,
                "balance_freshness_proven": False,
                "unreported_charge_upper_estimate_CU": unreported,
                "accounted_cost_upper_estimate_CU": accounted}
