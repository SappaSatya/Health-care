#!/usr/bin/env python3
"""
Export synthetic patient data from the HealthCare_DataWebsite into JSON.

This script downloads the homepage patient list, fetches each patient's raw HL7
file, parses the messages into structured visit records, and writes everything
to a single JSON file.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://manoharshasappa.github.io/HealthCare_DataWebsite/"
DEFAULT_OUTPUT = "healthcare_data.json"
USER_AGENT = "HealthCareJsonExporter/1.0"


@dataclass
class PatientListing:
    patient_id: str
    name: str
    username: str
    password: str
    listed_visits: int
    profile_url: str
    hl7_url: str


def fetch_text(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def parse_homepage_records(homepage_html: str, base_url: str) -> list[PatientListing]:
    row_pattern = re.compile(
        r"<tr class=\"record-row\" onclick=\"window\.location\.href='(?P<href>[^']+)'\">(?P<body>.*?)</tr>",
        re.DOTALL,
    )
    cell_pattern = re.compile(r"<td(?: class=\"[^\"]*\")?>(.*?)</td>", re.DOTALL)

    patients: list[PatientListing] = []

    for match in row_pattern.finditer(homepage_html):
        href = match.group("href")
        cells = [
            normalize_whitespace(strip_tags(cell))
            for cell in cell_pattern.findall(match.group("body"))
        ]
        if len(cells) != 4:
            continue

        profile_url = urljoin(base_url, href)
        patient_id = Path(href).stem
        visits_match = re.search(r"(\d+)", cells[3])
        listed_visits = int(visits_match.group(1)) if visits_match else 0
        hl7_url = urljoin(base_url, f"raw_hl7/{patient_id}.hl7")

        patients.append(
            PatientListing(
                patient_id=patient_id,
                name=cells[0],
                username=cells[1],
                password=cells[2],
                listed_visits=listed_visits,
                profile_url=profile_url,
                hl7_url=hl7_url,
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


def split_component(value: str) -> list[str]:
    return value.split("^") if value else []


def parse_name(value: str) -> dict[str, Any]:
    parts = split_component(value)
    last = parts[0] if len(parts) > 0 else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = parts[2] if len(parts) > 2 else ""
    full = " ".join(part for part in [first, middle, last] if part)
    return {
        "raw": value,
        "last": last or None,
        "first": first or None,
        "middle": middle or None,
        "full": full or None,
    }


def parse_identifier(value: str) -> dict[str, Any]:
    parts = split_component(value)
    return {
        "raw": value,
        "id": parts[0] if len(parts) > 0 and parts[0] else None,
        "assigning_authority": parts[3] if len(parts) > 3 and parts[3] else None,
        "identifier_type": parts[4] if len(parts) > 4 and parts[4] else None,
    }


def parse_address(value: str) -> dict[str, Any]:
    parts = split_component(value)
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
    parts = split_component(value)
    return {
        "raw": value,
        "point_of_care": parts[0] if len(parts) > 0 and parts[0] else None,
        "room": parts[1] if len(parts) > 1 and parts[1] else None,
        "bed": parts[2] if len(parts) > 2 and parts[2] else None,
        "facility": parts[3] if len(parts) > 3 and parts[3] else None,
    }


def parse_coded_value(value: str) -> dict[str, Any]:
    parts = split_component(value)
    return {
        "raw": value,
        "code": parts[0] if len(parts) > 0 and parts[0] else None,
        "display": parts[1] if len(parts) > 1 and parts[1] else None,
        "system": parts[2] if len(parts) > 2 and parts[2] else None,
    }


def split_hl7_messages(raw_hl7: str) -> list[str]:
    normalized = raw_hl7.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"\n\s*\n(?=MSH\|)", normalized) if part.strip()]


def first_non_empty(values: list[str]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def parse_msh(fields: list[str]) -> dict[str, Any]:
    message_type = split_component(fields[8] if len(fields) > 8 else "")
    return {
        "sending_application": fields[2] if len(fields) > 2 else None,
        "sending_facility": fields[3] if len(fields) > 3 else None,
        "receiving_application": fields[4] if len(fields) > 4 else None,
        "receiving_facility": fields[5] if len(fields) > 5 else None,
        "message_datetime": parse_hl7_datetime(fields[6] if len(fields) > 6 else ""),
        "message_type": {
            "raw": fields[8] if len(fields) > 8 else None,
            "code": message_type[0] if len(message_type) > 0 and message_type[0] else None,
            "trigger_event": message_type[1] if len(message_type) > 1 and message_type[1] else None,
        },
        "message_control_id": fields[9] if len(fields) > 9 else None,
        "processing_id": fields[10] if len(fields) > 10 else None,
        "version": fields[11] if len(fields) > 11 else None,
    }


def parse_evn(fields: list[str]) -> dict[str, Any]:
    return {
        "event_type": fields[1] if len(fields) > 1 else None,
        "recorded_datetime": parse_hl7_datetime(fields[2] if len(fields) > 2 else ""),
    }


def parse_pid(fields: list[str]) -> dict[str, Any]:
    identifier = parse_identifier(fields[3] if len(fields) > 3 else "")
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "patient_identifier": identifier,
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


def parse_pv1(fields: list[str]) -> dict[str, Any]:
    provider_field = first_non_empty(
        [
            fields[index]
            for index in range(4, len(fields))
            if "^" in fields[index] and not fields[index].startswith("CLINIC^")
        ]
    )
    visit_number = first_non_empty([field for field in fields if re.fullmatch(r"V\d+", field or "")])
    last_timestamp = first_non_empty(list(reversed([field for field in fields if re.fullmatch(r"\d{8,14}", field or "")])))

    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "patient_class": fields[2] if len(fields) > 2 else None,
        "assigned_location": parse_location(fields[3] if len(fields) > 3 else ""),
        "provider": parse_name(provider_field or ""),
        "hospital_service": fields[9] if len(fields) > 9 and fields[9] else None,
        "visit_number": visit_number,
        "admit_datetime": parse_hl7_datetime(last_timestamp or ""),
    }


def parse_dg1(fields: list[str]) -> dict[str, Any]:
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "diagnosis": parse_coded_value(fields[3] if len(fields) > 3 else ""),
        "diagnosis_datetime": parse_hl7_datetime(fields[5] if len(fields) > 5 else ""),
        "diagnosis_type": fields[6] if len(fields) > 6 else None,
    }


def parse_rxe(fields: list[str]) -> dict[str, Any]:
    coded = split_component(fields[1] if len(fields) > 1 else "")
    return {
        "medication": {
            "raw": fields[1] if len(fields) > 1 else None,
            "code": coded[3] if len(coded) > 3 and coded[3] else None,
            "display": coded[4] if len(coded) > 4 and coded[4] else None,
        },
        "dose": fields[2] if len(fields) > 2 else None,
        "route": fields[3] if len(fields) > 3 else None,
    }


def parse_obr(fields: list[str]) -> dict[str, Any]:
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "order_number": fields[3] if len(fields) > 3 else None,
        "service": parse_coded_value(fields[4] if len(fields) > 4 else ""),
        "observation_datetime": parse_hl7_datetime(fields[7] if len(fields) > 7 else ""),
    }


def parse_obx(fields: list[str]) -> dict[str, Any]:
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "value_type": fields[2] if len(fields) > 2 else None,
        "observation": parse_coded_value(fields[3] if len(fields) > 3 else ""),
        "value": fields[5] if len(fields) > 5 else None,
        "units": fields[6] if len(fields) > 6 else None,
        "reference_range": fields[7] if len(fields) > 7 else None,
        "abnormal_flag": fields[8] if len(fields) > 8 else None,
        "result_status": fields[11] if len(fields) > 11 else None,
    }


def parse_nte(fields: list[str]) -> dict[str, Any]:
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "note": fields[3] if len(fields) > 3 else None,
    }


def parse_al1(fields: list[str]) -> dict[str, Any]:
    return {
        "set_id": fields[1] if len(fields) > 1 else None,
        "allergy": parse_coded_value(fields[3] if len(fields) > 3 else ""),
    }


def parse_hl7_message(message_text: str) -> dict[str, Any]:
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
        "raw_message": message_text,
    }

    for line in message_text.splitlines():
        line = line.strip()
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            visit["message_header"] = parse_msh(fields)
        elif segment == "EVN":
            visit["event"] = parse_evn(fields)
        elif segment == "PID":
            visit["patient"] = parse_pid(fields)
        elif segment == "PV1":
            visit["visit"] = parse_pv1(fields)
        elif segment == "DG1":
            visit["diagnoses"].append(parse_dg1(fields))
        elif segment == "RXE":
            visit["medications"].append(parse_rxe(fields))
        elif segment == "OBR":
            visit["orders"].append(parse_obr(fields))
        elif segment == "OBX":
            visit["observations"].append(parse_obx(fields))
        elif segment == "NTE":
            visit["notes"].append(parse_nte(fields))
        elif segment == "AL1":
            visit["allergies"].append(parse_al1(fields))

    return visit


def summarize_patient_from_visits(visits: list[dict[str, Any]]) -> dict[str, Any]:
    first_patient = next((visit["patient"] for visit in visits if visit.get("patient")), None)
    allergies: list[dict[str, Any]] = []
    seen_allergies: set[str] = set()

    for visit in visits:
        for allergy in visit.get("allergies", []):
            key = allergy.get("allergy", {}).get("raw") or json.dumps(allergy, sort_keys=True)
            if key not in seen_allergies:
                seen_allergies.add(key)
                allergies.append(allergy)

    return {
        "demographics": first_patient,
        "allergies": allergies,
    }


def build_patient_record(listing: PatientListing, timeout: int, include_raw_hl7: bool) -> dict[str, Any]:
    raw_hl7 = fetch_text(listing.hl7_url, timeout=timeout)
    messages = split_hl7_messages(raw_hl7)
    visits = [parse_hl7_message(message) for message in messages]
    summary = summarize_patient_from_visits(visits)

    record = {
        "patient_id": listing.patient_id,
        "name": listing.name,
        "username": listing.username,
        "password": listing.password,
        "listed_visits": listing.listed_visits,
        "profile_url": listing.profile_url,
        "hl7_url": listing.hl7_url,
        "demographics": summary["demographics"],
        "allergies": summary["allergies"],
        "visits": visits,
    }

    if include_raw_hl7:
        record["raw_hl7"] = raw_hl7

    return record


def export_data(
    base_url: str,
    output_path: Path,
    timeout: int,
    limit: int | None,
    include_raw_hl7: bool,
) -> dict[str, Any]:
    homepage_html = fetch_text(base_url, timeout=timeout)
    listings = parse_homepage_records(homepage_html, base_url)
    if limit is not None:
        listings = listings[:limit]

    patients: list[dict[str, Any]] = []

    for index, listing in enumerate(listings, start=1):
        print(f"[{index}/{len(listings)}] Exporting {listing.patient_id} {listing.name}")
        patients.append(build_patient_record(listing, timeout=timeout, include_raw_hl7=include_raw_hl7))

    payload = {
        "source": base_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "patient_count": len(patients),
        "patients": patients,
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the HealthCare_DataWebsite dataset and export it as JSON."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Website base URL to scrape. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Path for the generated JSON file. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP request timeout in seconds. Default: 20",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of patients to export for testing.",
    )
    parser.add_argument(
        "--include-raw-hl7",
        action="store_true",
        help="Include the unparsed raw HL7 text for each patient in the JSON output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()

    try:
        payload = export_data(
            base_url=args.base_url,
            output_path=output_path,
            timeout=args.timeout,
            limit=args.limit,
            include_raw_hl7=args.include_raw_hl7,
        )
    except HTTPError as error:
        print(f"HTTP error while downloading data: {error.code} {error.reason}")
        return 1
    except URLError as error:
        print(f"Network error while downloading data: {error.reason}")
        return 1

    print(f"\nExport complete: {payload['patient_count']} patients written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
