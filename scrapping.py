#!/usr/bin/env python3
"""
Scrape the HealthCare_DataWebsite and export the data into a repository layout.

Output:
- data/healthcare_data.json
- raw/ (reserved for raw source files)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://manoharshasappa.github.io/HealthCare_DataWebsite/"
USER_AGENT = "HealthCareRepositoryScraper/1.0"
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = ROOT_DIR / "raw"
OUTPUT_FILE = DATA_DIR / "healthcare_data.json"


@dataclass
class PatientRow:
    patient_id: str
    name: str
    username: str
    password: str
    listed_visits: int
    profile_url: str
    hl7_url: str


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_homepage(html: str) -> list[PatientRow]:
    row_pattern = re.compile(
        r"<tr class=\"record-row\" onclick=\"window\.location\.href='(?P<href>[^']+)'\">(?P<body>.*?)</tr>",
        re.DOTALL,
    )
    cell_pattern = re.compile(r"<td(?: class=\"[^\"]*\")?>(.*?)</td>", re.DOTALL)

    patients: list[PatientRow] = []
    for match in row_pattern.finditer(html):
        href = match.group("href")
        cells = [clean_text(cell) for cell in cell_pattern.findall(match.group("body"))]
        if len(cells) != 4:
            continue

        patient_id = Path(href).stem
        visits_match = re.search(r"\d+", cells[3])
        listed_visits = int(visits_match.group()) if visits_match else 0

        patients.append(
            PatientRow(
                patient_id=patient_id,
                name=cells[0],
                username=cells[1],
                password=cells[2],
                listed_visits=listed_visits,
                profile_url=urljoin(BASE_URL, href),
                hl7_url=urljoin(BASE_URL, f"raw_hl7/{patient_id}.hl7"),
            )
        )

    return patients


def parse_hl7_datetime(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None

    formats = {
        8: "%Y%m%d",
        12: "%Y%m%d%H%M",
        14: "%Y%m%d%H%M%S",
    }
    fmt = formats.get(len(value))
    if not fmt:
        return value

    try:
        return datetime.strptime(value, fmt).isoformat()
    except ValueError:
        return value


def split_components(value: str) -> list[str]:
    return value.split("^") if value else []


def parse_name(value: str) -> dict[str, Any]:
    parts = split_components(value)
    last = parts[0] if len(parts) > 0 else None
    first = parts[1] if len(parts) > 1 else None
    middle = parts[2] if len(parts) > 2 else None
    full = " ".join(part for part in [first, middle, last] if part)
    return {
        "raw": value,
        "last": last,
        "first": first,
        "middle": middle,
        "full": full or None,
    }


def parse_identifier(value: str) -> dict[str, Any]:
    parts = split_components(value)
    return {
        "raw": value,
        "id": parts[0] if len(parts) > 0 and parts[0] else None,
        "assigning_authority": parts[3] if len(parts) > 3 and parts[3] else None,
        "identifier_type": parts[4] if len(parts) > 4 and parts[4] else None,
    }


def parse_address(value: str) -> dict[str, Any]:
    parts = split_components(value)
    return {
        "raw": value,
        "street": parts[0] if len(parts) > 0 and parts[0] else None,
        "other": parts[1] if len(parts) > 1 and parts[1] else None,
        "city": parts[2] if len(parts) > 2 and parts[2] else None,
        "state": parts[3] if len(parts) > 3 and parts[3] else None,
        "postal_code": parts[4] if len(parts) > 4 and parts[4] else None,
        "country": parts[5] if len(parts) > 5 and parts[5] else None,
    }


def parse_location(value: str) -> dict[str, Any]:
    parts = split_components(value)
    return {
        "raw": value,
        "point_of_care": parts[0] if len(parts) > 0 and parts[0] else None,
        "room": parts[1] if len(parts) > 1 and parts[1] else None,
        "bed": parts[2] if len(parts) > 2 and parts[2] else None,
        "facility": parts[3] if len(parts) > 3 and parts[3] else None,
    }


def parse_code(value: str) -> dict[str, Any]:
    parts = split_components(value)
    return {
        "raw": value,
        "code": parts[0] if len(parts) > 0 and parts[0] else None,
        "display": parts[1] if len(parts) > 1 and parts[1] else None,
        "system": parts[2] if len(parts) > 2 and parts[2] else None,
    }


def split_messages(raw_hl7: str) -> list[str]:
    normalized = raw_hl7.replace("\r\n", "\n").replace("\r", "\n").strip()
    return [part.strip() for part in re.split(r"\n\s*\n(?=MSH\|)", normalized) if part.strip()]


def first_matching_provider(fields: list[str]) -> str:
    for field in fields:
        if "^" in field and not field.startswith("CLINIC^"):
            return field
    return ""


def parse_message(message: str) -> dict[str, Any]:
    visit: dict[str, Any] = {
        "message_header": None,
        "event": None,
        "patient": None,
        "visit": None,
        "diagnoses": [],
        "medications": [],
        "orders": [],
        "observations": [],
        "notes": [],
        "allergies": [],
        "raw_message": message,
    }

    for line in message.splitlines():
        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            message_type = split_components(fields[8] if len(fields) > 8 else "")
            visit["message_header"] = {
                "sending_application": fields[2] if len(fields) > 2 else None,
                "sending_facility": fields[3] if len(fields) > 3 else None,
                "receiving_application": fields[4] if len(fields) > 4 else None,
                "receiving_facility": fields[5] if len(fields) > 5 else None,
                "message_datetime": parse_hl7_datetime(fields[6] if len(fields) > 6 else ""),
                "message_type": {
                    "raw": fields[8] if len(fields) > 8 else None,
                    "code": message_type[0] if len(message_type) > 0 else None,
                    "trigger_event": message_type[1] if len(message_type) > 1 else None,
                },
                "message_control_id": fields[9] if len(fields) > 9 else None,
                "processing_id": fields[10] if len(fields) > 10 else None,
                "version": fields[11] if len(fields) > 11 else None,
            }
        elif segment == "EVN":
            visit["event"] = {
                "event_type": fields[1] if len(fields) > 1 else None,
                "recorded_datetime": parse_hl7_datetime(fields[2] if len(fields) > 2 else ""),
            }
        elif segment == "PID":
            visit["patient"] = {
                "set_id": fields[1] if len(fields) > 1 else None,
                "patient_identifier": parse_identifier(fields[3] if len(fields) > 3 else ""),
                "name": parse_name(fields[5] if len(fields) > 5 else ""),
                "date_of_birth": parse_hl7_datetime(fields[7] if len(fields) > 7 else ""),
                "sex": fields[8] if len(fields) > 8 else None,
                "race_code": fields[10] if len(fields) > 10 else None,
                "address": parse_address(fields[11] if len(fields) > 11 else ""),
                "phone": fields[13] if len(fields) > 13 else None,
                "marital_status": fields[16] if len(fields) > 16 else None,
                "account_number": fields[18] if len(fields) > 18 else None,
                "ssn": fields[19] if len(fields) > 19 else None,
            }
        elif segment == "PV1":
            visit_number = next((field for field in fields if re.fullmatch(r"V\d+", field)), None)
            admit_datetime = next(
                (field for field in reversed(fields) if re.fullmatch(r"\d{8,14}", field)),
                "",
            )
            visit["visit"] = {
                "set_id": fields[1] if len(fields) > 1 else None,
                "patient_class": fields[2] if len(fields) > 2 else None,
                "assigned_location": parse_location(fields[3] if len(fields) > 3 else ""),
                "provider": parse_name(first_matching_provider(fields[4:])),
                "hospital_service": fields[9] if len(fields) > 9 else None,
                "visit_number": visit_number,
                "admit_datetime": parse_hl7_datetime(admit_datetime),
            }
        elif segment == "DG1":
            visit["diagnoses"].append(
                {
                    "set_id": fields[1] if len(fields) > 1 else None,
                    "diagnosis": parse_code(fields[3] if len(fields) > 3 else ""),
                    "diagnosis_datetime": parse_hl7_datetime(fields[5] if len(fields) > 5 else ""),
                    "diagnosis_type": fields[6] if len(fields) > 6 else None,
                }
            )
        elif segment == "RXE":
            medication_parts = split_components(fields[1] if len(fields) > 1 else "")
            visit["medications"].append(
                {
                    "medication": {
                        "raw": fields[1] if len(fields) > 1 else None,
                        "code": medication_parts[3] if len(medication_parts) > 3 else None,
                        "display": medication_parts[4] if len(medication_parts) > 4 else None,
                    },
                    "dose": fields[2] if len(fields) > 2 else None,
                    "route": fields[3] if len(fields) > 3 else None,
                }
            )
        elif segment == "OBR":
            visit["orders"].append(
                {
                    "set_id": fields[1] if len(fields) > 1 else None,
                    "order_number": fields[3] if len(fields) > 3 else None,
                    "service": parse_code(fields[4] if len(fields) > 4 else ""),
                    "observation_datetime": parse_hl7_datetime(fields[7] if len(fields) > 7 else ""),
                }
            )
        elif segment == "OBX":
            visit["observations"].append(
                {
                    "set_id": fields[1] if len(fields) > 1 else None,
                    "value_type": fields[2] if len(fields) > 2 else None,
                    "observation": parse_code(fields[3] if len(fields) > 3 else ""),
                    "value": fields[5] if len(fields) > 5 else None,
                    "units": fields[6] if len(fields) > 6 else None,
                    "reference_range": fields[7] if len(fields) > 7 else None,
                    "abnormal_flag": fields[8] if len(fields) > 8 else None,
                    "result_status": fields[11] if len(fields) > 11 else None,
                }
            )
        elif segment == "NTE":
            visit["notes"].append(
                {
                    "set_id": fields[1] if len(fields) > 1 else None,
                    "note": fields[3] if len(fields) > 3 else None,
                }
            )
        elif segment == "AL1":
            visit["allergies"].append(
                {
                    "set_id": fields[1] if len(fields) > 1 else None,
                    "allergy": parse_code(fields[3] if len(fields) > 3 else ""),
                }
            )

    return visit


def unique_allergies(visits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for visit in visits:
        for allergy in visit["allergies"]:
            key = allergy["allergy"]["raw"]
            if key not in seen:
                seen.add(key)
                results.append(allergy)

    return results


def build_patient_record(row: PatientRow) -> dict[str, Any]:
    raw_hl7 = fetch_text(row.hl7_url)
    messages = split_messages(raw_hl7)
    visits = [parse_message(message) for message in messages]
    demographics = next((visit["patient"] for visit in visits if visit["patient"]), None)

    return {
        "patient_id": row.patient_id,
        "name": row.name,
        "username": row.username,
        "password": row.password,
        "listed_visits": row.listed_visits,
        "profile_url": row.profile_url,
        "hl7_url": row.hl7_url,
        "demographics": demographics,
        "allergies": unique_allergies(visits),
        "visits": visits,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    homepage_html = fetch_text(BASE_URL)
    patients = parse_homepage(homepage_html)

    records: list[dict[str, Any]] = []
    for index, patient in enumerate(patients, start=1):
        print(f"[{index}/{len(patients)}] {patient.patient_id} {patient.name}")
        records.append(build_patient_record(patient))

    payload = {
        "source": BASE_URL,
        "generated_at": datetime.now(UTC).isoformat(),
        "patient_count": len(records),
        "patients": records,
    }

    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved JSON to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
