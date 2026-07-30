# Metric Catalog

This is the contract. Every metric below is implemented exactly as specified, and every
formula is verified by a pytest fixture where the expected value was computed by hand
(`backend/tests/fixtures/tiny_org.py`).

**Rules that apply to every metric in this document:**

- All rate metrics use **average headcount for the period** as the denominator, never
  end-of-period headcount.
- The API returns raw numbers. Formatting (percentages, currency, rounding) happens in
  the frontend.
- Every metric endpoint accepts the same optional filters: `date_from`, `date_to`,
  `department_id`, `location_id`, `level`, `manager_id`.
- If a formula below is ambiguous for a given edge case, stop and ask. Do not guess.

---

## 1. Talent Acquisition

| Metric | Formula | Grain |
|---|---|---|
| Time to Fill | `AVG(offer_accepted_date - requisition_opened_date)` | Req, dept, month |
| Time to Hire | `AVG(offer_accepted_date - first_application_date)` | Req, source |
| Funnel Conversion | `stage_n_count / stage_n-1_count` across Applied → Screen → Interview → Offer → Hired | Source, dept |
| Offer Acceptance Rate | `offers_accepted / offers_extended` | Dept, level, month |
| Cost per Hire | `(internal_cost + external_cost) / hires_in_period` | Dept, quarter |
| Source Effectiveness | `hires_from_source / applications_from_source`, plus 90-day retention of those hires | Source |
| Requisition Aging | `COUNT(reqs WHERE status='open' AND age_days > 60)` | Dept |
| Quality of Hire | `% of new hires still employed at day 180 AND performance_rating >= 3` | Source, manager |

## 2. Retention

| Metric | Formula | Grain |
|---|---|---|
| Headcount | `COUNT(active employees)` at month-end snapshot | Dept, location, level |
| Attrition Rate (annualized) | `(terminations_in_month / avg_headcount_in_month) * 12` | Dept, manager, month |
| Voluntary vs Involuntary | Split of the above by `termination_type` | Dept |
| Regretted Attrition | `voluntary_exits WHERE last_performance_rating >= 4 / total_voluntary_exits` | Dept |
| Tenure Distribution | Bucketed: <6m, 6–12m, 1–2y, 2–5y, 5y+ | Dept |
| New Hire 12-Month Retention | `% of a hire cohort still active at month 12` (cohort survival curve) | Hire quarter, source |
| Attrition by Manager | Attrition rate where `manager_id = X`, min 8 reports | Manager |
| Internal Mobility Rate | `(promotions + lateral_transfers) / avg_headcount` | Dept, year |
| Flight Risk Score | Logistic-style weighted score: tenure band, months since last promotion, engagement delta, manager attrition rate, comp percentile vs band | Employee |

## 3. Engagement

| Metric | Formula | Grain |
|---|---|---|
| eNPS | `%promoters (9–10) − %detractors (0–6)` | Company, dept, quarter |
| Engagement Index | Mean of 5 driver scores, normalized 0–100 | Dept, quarter |
| Driver Breakdown | Mean score per driver: Manager, Growth, Recognition, Workload, Belonging | Dept |
| Survey Participation | `responses / eligible_employees` | Dept, survey |
| Engagement → Attrition Link | Attrition rate of employees in bottom engagement quartile vs top quartile | Dept |
| Comment Themes | Claude-extracted themes from open text, with sentiment and volume | Dept, quarter |
| Absenteeism Rate | `unplanned_absence_days / available_workdays` | Dept, month |

## 4. Productivity

| Metric | Formula | Grain |
|---|---|---|
| Revenue per FTE | `revenue_in_period / avg_FTE` | Dept, quarter |
| Utilization | `billable_hours / available_hours` | Employee, team, week |
| Overtime Rate | `hours_over_40 / total_hours` | Team, month |
| Span of Control | `AVG(direct_reports per manager)` | Dept, level |
| Goal Attainment | `AVG(goal_actual / goal_target)` capped at 1.5 | Team, quarter |
| Output per Head | Tickets closed or story points per active FTE | Team, sprint |
| Training Hours | `SUM(training_hours) / headcount`, plus completion rate | Dept |

---

## MVP cut line

If the build falls behind, ship 5–6 metrics per domain, not all of them. Depth on
Retention — the domain HR leaders actually buy — beats thin coverage everywhere.

Implementation order is fixed: **Retention → Acquisition → Engagement → Productivity.**
