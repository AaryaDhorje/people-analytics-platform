"""Pydantic response models, one per metric shape.

Every field mirrors a key returned by the corresponding function in `app/metrics/`.
Models exist at the route boundary so a shape change breaks loudly in a test rather than
silently reshaping the API, and so `/docs` documents real field names.

`extra="forbid"` is deliberate: if a metric function grows a key that no model declares,
the route fails immediately instead of dropping it on the floor where the frontend would
have to guess why the field never arrives.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class MetricModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Retention --------------------------------------------------------------


class HeadcountPoint(MetricModel):
    period: date
    headcount: int
    active_start: int
    active_end: int
    avg_headcount: float | None
    hires: int
    terminations: int
    total_fte: float | None


class AttritionPoint(MetricModel):
    period: date
    terminations: int
    voluntary_terminations: int
    involuntary_terminations: int
    avg_headcount: float | None
    annualized_rate: float | None


class AttritionTotal(MetricModel):
    terminations: int
    voluntary_terminations: int
    involuntary_terminations: int
    voluntary_share: float | None
    headcount_months: float | None
    months: int
    annualized_rate: float | None


class RegrettedAttrition(MetricModel):
    total_exits: int
    voluntary_exits: int
    regretted_exits: int
    regretted_share: float | None


class TenureBand(MetricModel):
    tenure_band: str
    headcount: int


class CohortRetention(MetricModel):
    source_id: int | None
    months_since_hire: int
    cohort_size: int
    still_active: int
    retention_rate: float | None


class SurvivalPoint(MetricModel):
    months_since_hire: int
    cohort_size: int
    still_active: int
    survival_rate: float


class ManagerAttrition(MetricModel):
    period: date
    manager_id: str
    department_id: int | None
    reports: int
    avg_reports: float | None
    terminations: int
    voluntary_terminations: int
    headcount_months: float | None
    annualized_rate: float | None


class Mobility(MetricModel):
    promotions: int
    lateral_transfers: int
    mobility_events: int
    headcount_months: float | None
    months: int
    avg_headcount: float | None
    mobility_rate: float | None


class MobilityYear(Mobility):
    year: int


# --- Acquisition ------------------------------------------------------------


class TimeToFill(MetricModel):
    requisitions: int
    filled_positions: int
    day_sum: int
    mean_days: float | None


class TimeToHire(MetricModel):
    observations: int
    day_sum: int
    mean_days: float | None


class FunnelStage(MetricModel):
    stage: str
    applications: int
    conversion_from_previous: float | None
    mean_dwell_days: float | None
    still_in_stage: int


class OfferAcceptance(MetricModel):
    offers_extended: int
    offers_accepted: int
    offers_declined: int
    acceptance_rate: float | None


class CostPerHire(MetricModel):
    department_id: int | None
    period: date
    total_cost: float | None
    internal_cost: float | None
    external_cost: float | None
    hires: int
    cost_per_hire: float | None


class RequisitionAging(MetricModel):
    department_id: int | None
    open_requisitions: int
    aged_requisitions: int
    max_age_days: int | None
    threshold_days: int


class SourceEffectiveness(MetricModel):
    source_id: int | None
    applications: int
    offers_extended: int
    hires: int
    conversion_rate: float | None


class SourceRetention(MetricModel):
    source_id: int | None
    hires: int
    eligible_90d: int
    retained_90d: int
    retention_90d: float | None
    eligible_180d: int
    retained_180d: int
    retention_180d: float | None


class QualityOfHire(MetricModel):
    source_id: int | None
    eligible_180d: int
    retained_180d: int
    quality_hires: int
    quality_rate: float | None


# --- Engagement -------------------------------------------------------------


class Enps(MetricModel):
    responses: int
    promoters: int
    passives: int
    detractors: int
    enps: float | None


class EnpsPoint(MetricModel):
    period: date
    responses: int
    promoters: int
    detractors: int
    enps: float | None


class EngagementIndex(MetricModel):
    responses: int
    engagement_index: float | None


class DriverPoint(MetricModel):
    """Driver means for one period. The five driver keys are added dynamically, so this is
    the one model that permits extras."""

    model_config = ConfigDict(extra="allow")

    period: date
    responses: int
    engagement_index: float | None


class DriverDepartmentPoint(MetricModel):
    """Driver means for one department. Same shape as DriverPoint but keyed by department
    rather than period — a separate model rather than making `period` optional, because
    an optional discriminator lets a genuinely malformed row validate."""

    model_config = ConfigDict(extra="allow")

    department_id: int | None
    responses: int
    engagement_index: float | None


class Participation(MetricModel):
    survey_id: int
    period: date
    responses: int
    eligible_employees: int
    participation_rate: float | None


class QuartileAttrition(MetricModel):
    quartile: int
    respondent_observations: int
    terminations: int
    headcount_months: float
    annualized_rate: float | None


class Absenteeism(MetricModel):
    unplanned_days: float
    planned_days: float
    total_absence_days: float
    avg_headcount: float
    workdays: int | None
    available_workdays: float
    absenteeism_rate: float | None


class CommentTheme(MetricModel):
    theme: str
    sentiment: str
    volume: int
    mean_confidence: float | None


# --- Productivity -----------------------------------------------------------


class Utilization(MetricModel):
    billable_hours: float
    non_billable_hours: float
    available_hours: float
    employee_weeks: int
    utilization: float | None


class Overtime(MetricModel):
    total_hours: float
    overtime_hours: float
    threshold_hours: int
    overtime_rate: float | None


class OutputPerHead(MetricModel):
    output_units: float
    fte_weeks: float
    employee_weeks: int
    output_per_fte: float | None


class RevenuePerFte(MetricModel):
    department_id: int | None
    period: date
    revenue_amount: float
    fte_months: float
    months_observed: int
    avg_fte: float | None
    revenue_per_fte: float | None


class SpanOfControl(MetricModel):
    managers: int
    direct_reports: int
    largest_team: int | None
    span: float | None


class GoalAttainment(MetricModel):
    goals: int
    goals_with_target: int
    capped_attainment_sum: float
    completed_goals: int
    missed_goals: int
    cap: float
    attainment: float | None


class Training(MetricModel):
    training_hours: float
    assigned: int
    completed: int
    completion_rate: float | None
    headcount_months: float
    months: int
    avg_headcount: float | None
    hours_per_head: float | None


# --- Flight risk ------------------------------------------------------------


class FlightRisk(MetricModel):
    employee_id: str
    as_of_month: date
    score: float
    band: str
    components: dict[str, Any]


class RiskBandCount(MetricModel):
    band: str
    employees: int


# --- Overview ---------------------------------------------------------------


class Kpi(MetricModel):
    key: str
    label: str
    value: float | None
    previous: float | None
    delta: float | None
    delta_pct: float | None
    #: Formatting hint only — the API returns raw numbers and the frontend formats them,
    #: per CLAUDE.md. "rate" means a 0-1 fraction, not a percentage.
    unit: str
    #: None where direction is genuinely ambiguous. Headcount rising is neither good nor
    #: bad without context, and a green arrow would assert otherwise.
    higher_is_better: bool | None
    sparkline: list[float | None]


class Overview(MetricModel):
    as_of: date | None
    period_from: date | None
    period_to: date | None
    comparison_from: date | None
    comparison_to: date | None
    kpis: list[Kpi]
