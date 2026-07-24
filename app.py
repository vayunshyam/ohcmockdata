from __future__ import annotations

import csv
from pathlib import Path
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
EMPLOYEES_CSV = BASE_DIR / "employees.csv"
SKILLS_CSV = BASE_DIR / "skills.csv"
CERTIFICATIONS_CSV = BASE_DIR / "certifications.csv"

app = Flask(__name__)


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path.name}")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


EMPLOYEES = load_csv(EMPLOYEES_CSV)
SKILLS = load_csv(SKILLS_CSV)
CERTIFICATIONS = load_csv(CERTIFICATIONS_CSV)

EMPLOYEE_INDEX = {row["employee_id"]: row for row in EMPLOYEES}
SKILLS_BY_EMPLOYEE: dict[str, list[dict[str, str]]] = {}
for row in SKILLS:
    SKILLS_BY_EMPLOYEE.setdefault(row["employee_id"], []).append(row)

CERTS_BY_EMPLOYEE: dict[str, list[dict[str, str]]] = {}
for row in CERTIFICATIONS:
    CERTS_BY_EMPLOYEE.setdefault(row["employee_id"], []).append(row)


def as_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except ValueError:
        return default


def employee_payload(employee: dict[str, str], include_skills: bool = False, include_certs: bool = False) -> dict:
    payload = {
        "employee_id": employee["employee_id"],
        "display_name": employee["display_name"],
        "department": employee["department"],
        "role": employee["role"],
        "location": employee["location"],
        "capacity": as_int(employee.get("capacity")),
        "employment_type": employee.get("employment_type", ""),
        "manager_id": employee.get("manager_id", ""),
    }
    if include_skills:
        payload["skills"] = SKILLS_BY_EMPLOYEE.get(employee["employee_id"], [])
    if include_certs:
        payload["certifications"] = CERTS_BY_EMPLOYEE.get(employee["employee_id"], [])
    return payload


def filter_employees(rows: list[dict[str, str]], args) -> list[dict[str, str]]:
    department = args.get("department")
    role = args.get("role")
    location = args.get("location")
    manager_id = args.get("manager_id")
    employment_type = args.get("employment_type")

    if department:
        rows = [r for r in rows if r["department"].lower() == department.lower()]
    if role:
        rows = [r for r in rows if r["role"].lower() == role.lower()]
    if location:
        rows = [r for r in rows if r["location"].lower() == location.lower()]
    if manager_id:
        rows = [r for r in rows if r.get("manager_id", "") == manager_id]
    if employment_type:
        rows = [r for r in rows if r.get("employment_type", "").lower() == employment_type.lower()]
    return rows


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def root():
    return jsonify({
        "name": "mock-workforce-api",
        "endpoints": [
            "/health",
            "/team-skills",
            "/employees",
            "/employees/<employee_id>",
            "/employees/<employee_id>/skills",
            "/employees/<employee_id>/certifications",
        ],
    })


@app.get("/employees")
def employees():
    rows = filter_employees(EMPLOYEES.copy(), request.args)
    include_skills = request.args.get("include_skills", "false").lower() in {"1", "true", "yes", "y"}
    include_certs = request.args.get("include_certifications", "false").lower() in {"1", "true", "yes", "y"}
    items = [employee_payload(emp, include_skills=include_skills, include_certs=include_certs) for emp in rows]
    return jsonify({"items": items, "count": len(items)})


@app.get("/employees/<employee_id>")
def employee_detail(employee_id: str):
    employee = EMPLOYEE_INDEX.get(employee_id)
    if not employee:
        return jsonify({"error": "Employee not found", "employee_id": employee_id}), 404
    return jsonify({"items": [employee_payload(employee)], "count": 1})


@app.get("/employees/<employee_id>/skills")
def employee_skills(employee_id: str):
    employee = EMPLOYEE_INDEX.get(employee_id)
    if not employee:
        return jsonify({"error": "Employee not found", "employee_id": employee_id}), 404
    skills = SKILLS_BY_EMPLOYEE.get(employee_id, [])
    return jsonify({"employee_id": employee_id, "display_name": employee["display_name"], "items": skills, "count": len(skills)})


@app.get("/employees/<employee_id>/certifications")
def employee_certs(employee_id: str):
    employee = EMPLOYEE_INDEX.get(employee_id)
    if not employee:
        return jsonify({"error": "Employee not found", "employee_id": employee_id}), 404
    certs = CERTS_BY_EMPLOYEE.get(employee_id, [])
    return jsonify({"employee_id": employee_id, "display_name": employee["display_name"], "items": certs, "count": len(certs)})


@app.get("/team-skills")
def team_skills():
    rows = filter_employees(EMPLOYEES.copy(), request.args)
    items = []
    for emp in rows:
        payload = employee_payload(emp, include_skills=True, include_certs=True)
        items.append(payload)
    return jsonify({"items": items, "count": len(items)})


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    # Local dev only. Render should use gunicorn.
    app.run(host="0.0.0.0", port=8000, debug=True)
