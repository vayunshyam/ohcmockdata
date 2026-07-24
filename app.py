#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
EMPLOYEES_CSV = BASE_DIR / "employees.csv"
SKILLS_CSV = BASE_DIR / "skills.csv"
CERTIFICATIONS_CSV = BASE_DIR / "certifications.csv"


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


DEFAULT_REQUIRED_SKILLS = [
    {
        "skillName": "OCI Generative AI",
        "aliases": [
            "Oracle Cloud Infrastructure Generative AI",
            "OCI Gen AI",
            "OCI AI",
            "Generative AI",
            "Automation",
            "Python",
            "Cloud Architecture",
            "System Design",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "CRITICAL",
        "source": "USER_PROVIDED",
    },
    {
        "skillName": "React",
        "aliases": [
            "React.js",
            "ReactJS",
            "React Framework",
            "Frontend Development",
            "UI Design",
            "Figma",
            "Prototyping",
            "Design Systems",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "CRITICAL",
        "source": "USER_PROVIDED",
    },
    {
        "skillName": "API Integration",
        "aliases": [
            "API Development",
            "API Design",
            "API Connectivity",
            "API Management",
            "APIs",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "CRITICAL",
        "source": "USER_PROVIDED",
    },
    {
        "skillName": "Cloud Security",
        "aliases": [
            "Cloud Security Architecture",
            "Cloud Security Engineering",
            "Cloud Security Management",
            "Security",
            "Identity Management",
            "Cloud Support",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "HIGH",
        "source": "USER_PROVIDED",
    },
    {
        "skillName": "Product Management",
        "aliases": [
            "Product Owner",
            "Product Strategy",
            "Product Planning",
            "Roadmapping",
            "Stakeholder Management",
            "Analytics",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "HIGH",
        "source": "USER_PROVIDED",
    },
    {
        "skillName": "Support Operations",
        "aliases": [
            "Customer Support Operations",
            "Support Process Management",
            "Support Services",
            "Customer Support",
            "Knowledge Base",
            "Troubleshooting",
            "Escalation Management",
        ],
        "requiredPeople": 0,
        "minimumProficiency": "MEDIUM",
        "criticality": "HIGH",
        "source": "USER_PROVIDED",
    },
]


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def send_json(status: int, payload: dict):
    response = app.response_class(
        response=json_bytes(payload),
        status=status,
        mimetype="application/json",
    )
    return response


def normalize_text(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def dedupe_normalized(values: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for value in values:
        n = normalize_text(value)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def skill_record_matches(skill_name: str, alias_norms: list[str]) -> bool:
    skill_norm = normalize_text(skill_name)
    if not skill_norm:
        return False

    for alias in alias_norms:
        if skill_norm == alias:
            return True
        if alias in skill_norm:
            return True
        if skill_norm in alias:
            return True
    return False


def parse_required_skills():
    """
    Optional override:
      /team-skills?skills=Skill A,Skill B,Skill C

    Advanced override:
      /team-skills?skills=Skill A|Alias 1|Alias 2,Skill B|Alias 3|Alias 4
    """
    raw = (request.args.get("skills") or "").strip()
    if not raw:
        return DEFAULT_REQUIRED_SKILLS

    parsed = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        parts = [p.strip() for p in chunk.split("|") if p.strip()]
        canonical = parts[0]
        aliases = parts[1:]

        parsed.append(
            {
                "skillName": canonical,
                "aliases": aliases,
                "requiredPeople": 0,
                "minimumProficiency": "MEDIUM",
                "criticality": "MEDIUM",
                "source": "USER_PROVIDED",
            }
        )

    return parsed or DEFAULT_REQUIRED_SKILLS


def employee_payload(employee: dict[str, str]) -> dict:
    employee_id = employee["employee_id"]
    return {
        "employee_id": employee_id,
        "display_name": employee.get("display_name", ""),
        "department": employee.get("department", ""),
        "role": employee.get("role", ""),
        "location": employee.get("location", ""),
        "employment_type": employee.get("employment_type", ""),
        "manager_id": employee.get("manager_id", ""),
        "capacity": to_int(employee.get("capacity", 0)),
        "certifications": CERTS_BY_EMPLOYEE.get(employee_id, []),
        "skills": SKILLS_BY_EMPLOYEE.get(employee_id, []),
    }


def analyze_team(required_skills: list[dict]) -> dict:
    employees = [employee_payload(emp) for emp in EMPLOYEES]
    required_names = [req["skillName"] for req in required_skills]
    required_name_set = set(required_names)

    matches_by_skill = []
    covered_skills = []
    missing_skills = []
    matched_employee_ids = set()
    qualified_employee_ids = set()

    # Per-employee map of which required skills are covered
    employee_required_matches = {}

    for emp in employees:
        emp_id = emp["employee_id"]
        emp_skill_names = [s.get("skill_name", "") for s in emp.get("skills", [])]
        matched_required = []

        for req in required_skills:
            alias_norms = dedupe_normalized([req["skillName"], *req.get("aliases", [])])

            matched_skill_names = []
            for skill_name in emp_skill_names:
                if skill_record_matches(skill_name, alias_norms):
                    matched_skill_names.append(skill_name)

            if matched_skill_names:
                matched_required.append(
                    {
                        "requiredSkill": req["skillName"],
                        "matchedSkills": matched_skill_names,
                    }
                )

        employee_required_matches[emp_id] = matched_required
        if matched_required:
            matched_employee_ids.add(emp_id)

    for req in required_skills:
        alias_norms = dedupe_normalized([req["skillName"], *req.get("aliases", [])])

        skill_matches = []
        for emp in employees:
            emp_id = emp["employee_id"]
            emp_skill_names = [s.get("skill_name", "") for s in emp.get("skills", [])]

            matched_skill_names = []
            for skill_name in emp_skill_names:
                if skill_record_matches(skill_name, alias_norms):
                    matched_skill_names.append(skill_name)

            if matched_skill_names:
                skill_matches.append(
                    {
                        "employee_id": emp_id,
                        "display_name": emp.get("display_name", ""),
                        "department": emp.get("department", ""),
                        "role": emp.get("role", ""),
                        "location": emp.get("location", ""),
                        "capacity": emp.get("capacity", 0),
                        "matchedSkills": matched_skill_names,
                    }
                )

        if skill_matches:
            covered_skills.append(req["skillName"])
        else:
            missing_skills.append(req["skillName"])

        matches_by_skill.append(
            {
                "requiredSkill": req["skillName"],
                "aliases": req.get("aliases", []),
                "criticality": req.get("criticality", ""),
                "minimumProficiency": req.get("minimumProficiency", ""),
                "requiredPeople": req.get("requiredPeople", 0),
                "matchCount": len(skill_matches),
                "matches": skill_matches,
            }
        )

    for emp in employees:
        emp_id = emp["employee_id"]
        matched_required_names = {
            m["requiredSkill"] for m in employee_required_matches.get(emp_id, [])
        }
        if required_name_set and required_name_set.issubset(matched_required_names):
            qualified_employee_ids.add(emp_id)

    coverage_pct = (
        round((len(covered_skills) / len(required_skills)) * 100)
        if required_skills
        else 0
    )
    min_evidence_pct = to_float(request.args.get("min_evidence_pct", 80), 80.0)
    min_profiles = to_int(request.args.get("min_profiles", 3), 3)

    sufficient_evidence = (
        coverage_pct >= min_evidence_pct and len(qualified_employee_ids) >= min_profiles
    )

    # Enrich employees with required-skill matches so the workflow can read it directly.
    enriched_employees = []
    for emp in employees:
        emp_id = emp["employee_id"]
        enriched_employees.append(
            {
                **emp,
                "requiredSkillMatches": employee_required_matches.get(emp_id, []),
            }
        )

    return {
        "count": len(enriched_employees),
        "requiredSkills": required_skills,
        "items": enriched_employees,
        "matchesBySkill": matches_by_skill,
        "coveredSkills": covered_skills,
        "missingSkills": missing_skills,
        "coveragePct": coverage_pct,
        "matchedEmployeeCount": len(matched_employee_ids),
        "qualifiedEmployeeCount": len(qualified_employee_ids),
        "minEvidencePct": min_evidence_pct,
        "minProfiles": min_profiles,
        "sufficientEvidence": sufficient_evidence,
    }


@app.get("/health")
def health():
    return send_json(200, {"status": "ok"})


@app.get("/employees")
def employees():
    rows = EMPLOYEES.copy()

    department = request.args.get("department")
    role = request.args.get("role")
    location = request.args.get("location")
    manager_id = request.args.get("manager_id")
    employment_type = request.args.get("employment_type")

    if department:
        rows = [r for r in rows if r["department"].lower() == department.lower()]
    if role:
        rows = [r for r in rows if r["role"].lower() == role.lower()]
    if location:
        rows = [r for r in rows if r["location"].lower() == location.lower()]
    if manager_id:
        rows = [r for r in rows if r.get("manager_id", "") == manager_id]
    if employment_type:
        rows = [
            r for r in rows if r["employment_type"].lower() == employment_type.lower()
        ]

    return send_json(200, {"items": rows, "count": len(rows)})


@app.get("/employees/<employee_id>")
def employee_detail(employee_id: str):
    employee = EMPLOYEE_INDEX.get(employee_id)
    if not employee:
        return send_json(
            404, {"error": "Employee not found", "employee_id": employee_id}
        )
    return send_json(200, {"items": [employee], "count": 1})


@app.get("/employees/<employee_id>/skills")
def employee_skills(employee_id: str):
    skills = SKILLS_BY_EMPLOYEE.get(employee_id, [])
    return send_json(200, {"items": skills, "count": len(skills)})


@app.get("/employees/<employee_id>/certifications")
def employee_certifications(employee_id: str):
    certs = CERTS_BY_EMPLOYEE.get(employee_id, [])
    return send_json(200, {"items": certs, "count": len(certs)})


@app.get("/team-skills")
def team_skills():
    """
    Default behavior:
      - uses the current initiative's required skills
      - computes coveragePct / coveredSkills / missingSkills / sufficientEvidence
      - returns enriched employee rows in items[]
    """
    required_skills = parse_required_skills()
    return send_json(200, analyze_team(required_skills))


if __name__ == "__main__":
    port = int(request.environ.get("PORT", 8000)) if request else 8000
    app.run(host="0.0.0.0", port=port)
