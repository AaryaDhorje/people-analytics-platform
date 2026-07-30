"""SQLAlchemy ORM models — the star schema.

Populated in phase 1. Dimensions (employee, department, location, job_level,
source, requisition, survey, date spine) and facts (employment_event,
monthly_headcount_snapshot, application, application_stage_event,
survey_response, timesheet_week, goal, absence, performance_review).

Every model subclasses `app.db.Base`. Alembic's autogenerate discovers models
through this package, so each new module must be imported here.
"""

from app.db import Base

__all__ = ["Base"]
