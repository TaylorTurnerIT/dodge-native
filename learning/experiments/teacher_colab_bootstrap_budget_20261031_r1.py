"""Pure financial controls for separately reviewed A100 training.

This module performs no network, allocation, game, seed, or ledger operation.
An unchanged balance is allowed and never proves zero cost or freshness.
Long-run accounting uses max(observed debit, prior allowance + elapsed ceiling
cost), avoiding double counting of reported charges. The prior allowance covers
earlier owned synthetic assignments. Server-meter and network limits
prevent any claim of a hard billing guarantee.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Config:
    maximum_assigned_seconds: int = 23000
    setup_seconds: int = 1200
    teardown_reserve_seconds: int = 480
    maximum_rate_CU_per_hour: float = 7.0
    maximum_existing_CU: float = 48.0
    stop_work_CU: float = 47.0
    prior_pending_charge_allowance_CU: float = 3.1
    maximum_request_seconds: int = 15


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


class TrainingBudget:
    def __init__(self, initial_balance, allocation_start, config=Config()):
        if config != Config(): raise ValueError('Training budget limits differ')
        if not finite(initial_balance) or initial_balance < config.maximum_existing_CU:
            raise ValueError('Existing credit balance unavailable/insufficient')
        if not finite(allocation_start): raise ValueError('Allocation clock unavailable')
        self.initial_balance=self.last_balance=initial_balance
        self.allocation_start=self.last_observed=allocation_start
        self.training_started=False;self.balance_progress_seen=False;self.config=config
        self.retrieval_started=False

    def accounting(self, raw, now, request_started):
        if not finite(now) or now < self.last_observed:
            raise ValueError('Observation clock reversed')
        if not finite(request_started) or not 0 <= now-request_started <= self.config.maximum_request_seconds:
            raise ValueError('Account request unavailable/overlong')
        balance=raw.get('currentBalance')
        if not finite(balance) or balance < 0 or balance > self.last_balance:
            raise ValueError('Credit balance unavailable/nonfinite/incoherent')
        elapsed=now-self.allocation_start
        if elapsed > self.config.maximum_assigned_seconds:
            raise ValueError('Total assigned-time ceiling exceeded')
        observed=self.initial_balance-balance
        ceiling=elapsed*self.config.maximum_rate_CU_per_hour/3600
        accounted=max(observed,self.config.prior_pending_charge_allowance_CU+ceiling)
        remaining=max(0,self.config.maximum_assigned_seconds-elapsed)
        projected=accounted+remaining*self.config.maximum_rate_CU_per_hour/3600
        self.balance_progress_seen=self.balance_progress_seen or balance < self.last_balance
        self.last_balance=balance;self.last_observed=now
        return dict(observed_debit_CU=observed,elapsed_assigned_seconds_upper_bound=elapsed,
            accounted_cost_upper_estimate_CU=accounted,projected_total_CU=projected,
            balance_progress_seen=self.balance_progress_seen,balance_freshness_proven=False)

    def observe(self, raw, assignments, owned_endpoint, now, *,request_started,phase):
        if phase not in {'setup','training','retrieval'}: raise ValueError('Unknown work phase')
        if self.retrieval_started and phase!='retrieval': raise ValueError('Retrieval cannot rearm work')
        if self.training_started and phase=='setup': raise ValueError('Work phase cannot reverse')
        result=self.accounting(raw,now,request_started)
        elapsed=result['elapsed_assigned_seconds_upper_bound']
        if phase!='retrieval' and elapsed >= self.config.maximum_assigned_seconds-self.config.teardown_reserve_seconds:
            raise ValueError('Work deadline reserves480s for retrieval/teardown')
        if phase=='setup' and elapsed > self.config.setup_seconds:
            raise ValueError('Native setup exceeded1200s')
        rate=raw.get('consumptionRateHourly');count=raw.get('assignmentsCount')
        if not finite(rate) or not 0 < rate <= self.config.maximum_rate_CU_per_hour:
            raise ValueError('Unavailable/zero/nonfinite/over-ceiling live price')
        if type(count) is not int or count!=1 or len(assignments)!=1:
            raise ValueError('Exactly one live assignment required')
        assignment=assignments[0]
        if assignment.get('endpoint')!=owned_endpoint or assignment.get('accelerator')!='A100':
            raise ValueError('Exact owned A100 assignment required')
        if result['projected_total_CU'] > self.config.maximum_existing_CU:
            raise ValueError('Projected cost exceeds48CU')
        if phase!='retrieval' and result['accounted_cost_upper_estimate_CU'] >= self.config.stop_work_CU:
            raise ValueError('47CU work cutoff reserves teardown allowance')
        self.training_started=self.training_started or phase=='training'
        self.retrieval_started=self.retrieval_started or phase=='retrieval'
        return dict(result,work_admitted=phase!='retrieval',receipt_retrieval_admitted=phase=='retrieval',
                    phase=phase,live_rate_CU_per_hour=rate)

    def final(self, raw, assignments, now, *,request_started):
        result=self.accounting(raw,now,request_started)
        if raw.get('assignmentsCount')!=0 or assignments:
            raise ValueError('Fresh zero-assignment proof absent')
        if result['accounted_cost_upper_estimate_CU'] > self.config.maximum_existing_CU:
            raise ValueError('Final conservative cost exceeds48CU')
        return dict(result,assignment_absence_confirmed=True,budget_within_limits=True)
