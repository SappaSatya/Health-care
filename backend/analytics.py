from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT_DIR / "data" / "healthcare_data.json"


def load_dataset() -> dict[str, Any]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _safe_parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _iter_patient_visits(dataset: dict[str, Any]):
    for patient in dataset.get("patients", []):
        for visit in patient.get("visits", []):
            yield patient, visit


def _diagnosis_name(diagnosis: dict[str, Any]) -> str:
    detail = diagnosis.get("diagnosis", {})
    code = detail.get("code") or "Unknown"
    label = detail.get("display") or "Unknown diagnosis"
    return f"{label} ({code})"


def _observation_name(observation: dict[str, Any]) -> str:
    detail = observation.get("observation", {})
    code = detail.get("code") or "Unknown"
    label = detail.get("display") or "Unknown observation"
    return f"{label} ({code})"


def summarize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    patients = dataset.get("patients", [])
    total_visits = sum(len(patient.get("visits", [])) for patient in patients)
    total_diagnoses = 0
    total_medications = 0
    total_observations = 0
    abnormal_observations = 0
    patients_with_multiple_diagnoses = 0

    for patient in patients:
        unique_diagnoses: set[str] = set()
        for visit in patient.get("visits", []):
            diagnoses = visit.get("diagnoses", [])
            medications = visit.get("medications", [])
            observations = visit.get("observations", [])

            total_diagnoses += len(diagnoses)
            total_medications += len(medications)
            total_observations += len(observations)

            for diagnosis in diagnoses:
                unique_diagnoses.add(_diagnosis_name(diagnosis))

            for observation in observations:
                if observation.get("abnormal_flag") and observation.get("abnormal_flag") != "N":
                    abnormal_observations += 1

        if len(unique_diagnoses) > 1:
            patients_with_multiple_diagnoses += 1

    average_visits = round(total_visits / len(patients), 2) if patients else 0

    return {
        "total_patients": len(patients),
        "total_visits": total_visits,
        "average_visits_per_patient": average_visits,
        "total_diagnoses": total_diagnoses,
        "total_medications": total_medications,
        "total_observations": total_observations,
        "abnormal_observations": abnormal_observations,
        "patients_with_multiple_diagnoses": patients_with_multiple_diagnoses,
    }


def visits_by_month(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()

    for _, visit in _iter_patient_visits(dataset):
        message_header = visit.get("message_header", {})
        timestamp = _safe_parse_datetime(message_header.get("message_datetime"))
        if not timestamp:
            timestamp = _safe_parse_datetime(visit.get("visit", {}).get("admit_datetime"))
        if timestamp:
            counts[timestamp.strftime("%Y-%m")] += 1

    rows = []
    for month_key in sorted(counts):
        month_date = datetime.strptime(month_key, "%Y-%m")
        rows.append(
            {
                "month_key": month_key,
                "month_label": month_date.strftime("%b %Y"),
                "visits": counts[month_key],
            }
        )
    return rows


def gender_breakdown(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    labels = {"M": "Male", "F": "Female"}

    for patient in dataset.get("patients", []):
        sex = patient.get("demographics", {}).get("sex") or "Unknown"
        counter[labels.get(sex, sex)] += 1

    return [{"label": label, "count": count} for label, count in counter.most_common()]


def top_diseases(dataset: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    visit_counter: Counter[str] = Counter()
    patient_tracker: defaultdict[str, set[str]] = defaultdict(set)

    for patient, visit in _iter_patient_visits(dataset):
        patient_id = patient.get("patient_id")
        for diagnosis in visit.get("diagnoses", []):
            name = _diagnosis_name(diagnosis)
            visit_counter[name] += 1
            if patient_id:
                patient_tracker[name].add(patient_id)

    rows = []
    for disease, visit_count in visit_counter.most_common(limit):
        rows.append(
            {
                "disease": disease,
                "visit_count": visit_count,
                "patient_count": len(patient_tracker[disease]),
            }
        )
    return rows


def top_patients_by_visits(dataset: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    rows = []
    for patient in dataset.get("patients", []):
        visit_count = len(patient.get("visits", []))
        disease_set = {
            _diagnosis_name(diagnosis)
            for visit in patient.get("visits", [])
            for diagnosis in visit.get("diagnoses", [])
        }
        rows.append(
            {
                "patient_id": patient.get("patient_id"),
                "name": patient.get("name"),
                "visits": visit_count,
                "distinct_diseases": len(disease_set),
            }
        )

    rows.sort(key=lambda row: (-row["visits"], row["name"] or ""))
    return rows[:limit]


def patients_with_multiple_diseases(dataset: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for patient in dataset.get("patients", []):
        disease_counter: Counter[str] = Counter()
        for visit in patient.get("visits", []):
            for diagnosis in visit.get("diagnoses", []):
                disease_counter[_diagnosis_name(diagnosis)] += 1

        if len(disease_counter) > 1:
            rows.append(
                {
                    "patient_id": patient.get("patient_id"),
                    "name": patient.get("name"),
                    "disease_count": len(disease_counter),
                    "visits": len(patient.get("visits", [])),
                    "diseases": list(disease_counter.keys()),
                }
            )

    rows.sort(key=lambda row: (-row["disease_count"], -row["visits"], row["name"] or ""))
    return rows[:limit]


def observation_alerts(dataset: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()

    for _, visit in _iter_patient_visits(dataset):
        for observation in visit.get("observations", []):
            if observation.get("abnormal_flag") and observation.get("abnormal_flag") != "N":
                counter[_observation_name(observation)] += 1

    return [{"observation": label, "count": count} for label, count in counter.most_common(limit)]


def dashboard_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": dataset.get("source"),
        "generated_at": dataset.get("generated_at"),
        "patient_count": dataset.get("patient_count"),
        "summary": summarize_dataset(dataset),
        "visits_by_month": visits_by_month(dataset),
        "gender_breakdown": gender_breakdown(dataset),
        "top_diseases": top_diseases(dataset),
        "top_patients_by_visits": top_patients_by_visits(dataset),
        "patients_with_multiple_diseases": patients_with_multiple_diseases(dataset),
        "observation_alerts": observation_alerts(dataset),
    }


def ai_context_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    payload = dashboard_payload(dataset)
    return {
        "summary": payload["summary"],
        "top_diseases": payload["top_diseases"][:5],
        "top_patients_by_visits": payload["top_patients_by_visits"][:5],
        "observation_alerts": payload["observation_alerts"][:5],
    }
