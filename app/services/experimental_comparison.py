"""Conservative, deterministic experimental optical-gap comparisons."""
from __future__ import annotations
from itertools import combinations
from app.schemas.experimental_knowledge import (
    ComparisonReason, ComparisonReport, ExperimentalObservation, PairComparison,
)

IDENTITY = ("formula", "phase", "doping")
METHOD = ("measurement_technique", "analysis_method", "transition_assumption")
CONTEXT = ("preparation_method", "preparation_temperature", "preparation_time",
           "preparation_atmosphere", "measurement_conditions")

def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().split())

def compare_pair(left: ExperimentalObservation, right: ExperimentalObservation) -> PairComparison:
    if left.tenant_id != right.tenant_id:
        raise ValueError("cross tenant comparison forbidden")
    if left.observation_id == right.observation_id:
        raise ValueError("duplicate observation")
    reasons = []
    if left.property_name != right.property_name or left.property_unit != right.property_unit:
        reasons.append(ComparisonReason(code="property_mismatch", field="property_name",
                                        detail="Different measured property or units"))
        return PairComparison(left_id=left.observation_id, right_id=right.observation_id,
                              status="incompatible", reasons=reasons)
    missing, identity_diff, method_diff, context_diff = [], [], [], []
    for name in (*IDENTITY, *METHOD, *CONTEXT):
        a, b = getattr(left, name), getattr(right, name)
        if a.status != "reported" or b.status != "reported":
            missing.append(ComparisonReason(code="missing_or_ambiguous", field=name,
                                            detail="At least one record lacks unambiguous evidence"))
        elif _norm(a.value) != _norm(b.value):
            reason = ComparisonReason(code="reported_values_differ", field=name,
                                      detail=f"{a.value!r} vs {b.value!r}; no causal inference")
            (identity_diff if name in IDENTITY else method_diff if name in METHOD
             else context_diff).append(reason)
    if identity_diff:
        status = "incompatible"
    elif missing:
        status = "insufficient_evidence"
    elif method_diff or context_diff:
        status = "caution"
    else:
        status = "comparable"
    reasons = identity_diff + missing + method_diff + context_diff
    if left.verification_status != "human_verified" or right.verification_status != "human_verified":
        reasons.append(ComparisonReason(code="human_review_required",
                                        field="verification_status",
                                        detail="One or both observations have not been human-reviewed"))
        if status == "comparable":
            status = "caution"
    if not reasons:
        reasons.append(ComparisonReason(code="tracked_fields_match", field="record",
                                        detail="Tracked fields agree; unreported factors may remain"))
    return PairComparison(left_id=left.observation_id, right_id=right.observation_id,
                          status=status, reasons=reasons)

def compare_observations(observations: list[ExperimentalObservation]) -> ComparisonReport:
    if len(observations) > 50:
        raise ValueError("maximum 50 observations per comparison")
    if len({o.observation_id for o in observations}) != len(observations):
        raise ValueError("duplicate observation ID")
    if len({o.tenant_id for o in observations}) > 1:
        raise ValueError("cross tenant comparison forbidden")
    return ComparisonReport(
        observations=observations,
        comparisons=[compare_pair(a, b) for a, b in combinations(observations, 2)],
    )
