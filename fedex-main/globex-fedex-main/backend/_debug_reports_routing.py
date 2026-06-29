from app.services.admin_client.reports.reports_workspace import is_reports_workspace, score_reports_soft
from app.services.admin_client.intent_priority import should_route_reports
from app.services.admin_client.reports.reports_intent import classify_reports_intent, _extract_run_id
from app.services.admin_client.reports.reports_reconcile import reconcile_reports_plan
from app.services.admin_client.pipeline import _should_engage

msgs = [
    "d'accord je veux que tu me previsualise le dernier reports",
    "je veux que tu me prevusiulaise le 2",
    "je veux que tu me telecharge le #1",
]
hist = """Exports récents
- #8 Tracking History (xlsx)
- #2 Tracking History (xlsx)
_Source : Centre de rapports Admin_"""

for m in msgs:
    print("===", m)
    print("workspace", is_reports_workspace(m), "score", score_reports_soft(m))
    print("route", should_route_reports(m), "route+hist", should_route_reports(m, history_text=hist))
    print("engage", _should_engage(m, has_attachment=False, history_text=hist))
    plan = classify_reports_intent(m)
    print("intent", plan.task_type, "run_id", plan.run_id, "search", plan.search_filter)
    rec = reconcile_reports_plan(m, plan)
    print("reconcile search", rec.search_filter, "run_id", rec.run_id)
    print("extract_run_id", _extract_run_id(m))
    print()
