#!/usr/bin/env python3
"""
Mock Workforce REST API

Run:
    python mock_workforce_api.py

Expected files in the same folder:
    employees.csv
    skills.csv
    certifications.csv

Endpoints:
    GET /health
    GET /employees
    GET /employees/<employee_id>
    GET /employees/<employee_id>/skills
    GET /employees/<employee_id>/certifications

All responses use the shape:
    {"items": [...], "count": N}
"""

from __future__ import annotations

import csv
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
EMPLOYEES_CSV = BASE_DIR / "employees.csv"
SKILLS_CSV = BASE_DIR / "skills.csv"
CERTIFICATIONS_CSV = BASE_DIR / "certifications.csv"
PORT = 8000


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


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json_bytes(payload)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class MockAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep console output clean for demos.
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path == "/health":
            return send_json(self, 200, {"status": "ok"})

        if path == "/employees":
            rows = EMPLOYEES.copy()

            department = query.get("department", [None])[0]
            role = query.get("role", [None])[0]
            location = query.get("location", [None])[0]
            manager_id = query.get("manager_id", [None])[0]
            employment_type = query.get("employment_type", [None])[0]

            if department:
                rows = [r for r in rows if r["department"].lower() == department.lower()]
            if role:
                rows = [r for r in rows if r["role"].lower() == role.lower()]
            if location:
                rows = [r for r in rows if r["location"].lower() == location.lower()]
            if manager_id:
                rows = [r for r in rows if r.get("manager_id", "") == manager_id]
            if employment_type:
                rows = [r for r in rows if r["employment_type"].lower() == employment_type.lower()]

            return send_json(self, 200, {"items": rows, "count": len(rows)})

        if path.startswith("/employees/"):
            parts = path.strip("/").split("/")
            if len(parts) == 2:
                employee_id = parts[1]
                employee = EMPLOYEE_INDEX.get(employee_id)
                if not employee:
                    return send_json(self, 404, {"error": "Employee not found", "employee_id": employee_id})
                return send_json(self, 200, {"items": [employee], "count": 1})

            if len(parts) == 3 and parts[2] == "skills":
                employee_id = parts[1]
                skills = SKILLS_BY_EMPLOYEE.get(employee_id, [])
                return send_json(self, 200, {"items": skills, "count": len(skills)})

            if len(parts) == 3 and parts[2] == "certifications":
                employee_id = parts[1]
                certs = CERTS_BY_EMPLOYEE.get(employee_id, [])
                return send_json(self, 200, {"items": certs, "count": len(certs)})

        return send_json(self, 404, {"error": "Not found", "path": path})


def main() -> None:
    server = HTTPServer(("0.0.0.0", PORT), MockAPIHandler)
    print(f"Mock workforce API running on http://localhost:{PORT}")
    print("Try:")
    print("  GET /employees")
    print("  GET /employees/101")
    print("  GET /employees/101/skills")
    print("  GET /employees/101/certifications")
    server.serve_forever()


if __name__ == "__main__":
    main()
