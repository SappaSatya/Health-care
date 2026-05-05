# Health Care Analytics Repository

This repository stores scraped synthetic healthcare data from:

`https://manoharshasappa.github.io/HealthCare_DataWebsite/`

It now also includes a lightweight dashboard app that turns the JSON dataset into charts, summaries, and optional AI-generated insights.

## Structure

```text
Health-care/
|-- backend/
|   |-- analytics.py
|   `-- app.py
|-- data/
|   `-- healthcare_data.json
|-- frontend/
|   |-- app.js
|   |-- index.html
|   `-- styles.css
|-- raw/
|   `-- .gitkeep
|-- scrapping.py
|-- .env.example
|-- README.md
`-- .gitignore
```

## What Each Part Does

- `data/` contains the final structured JSON dataset.
- `raw/` is reserved for raw downloaded files such as HTML pages or HL7 files.
- `scrapping.py` contains the scraping/export logic for rebuilding the JSON file.
- `backend/app.py` runs a local HTTP server and exposes analytics API endpoints.
- `backend/analytics.py` calculates the dashboard metrics from the JSON file.
- `frontend/` contains the dashboard UI.

## Run The Dashboard

```powershell
python backend/app.py
```

Then open:

`http://127.0.0.1:8000`

## Optional OpenAI Insights

The dashboard includes an AI insight panel powered by the OpenAI Responses API. For security, do not hardcode your key in the repository.

Create a local `.env`-style environment in your shell before running:

```powershell
$env:OPENAI_API_KEY="your_rotated_key_here"
$env:OPENAI_MODEL="gpt-4.1-mini"
python backend/app.py
```

The backend reads `OPENAI_API_KEY` from the environment and sends a compact data snapshot to the model for narrative insights.

## Rebuild The Dataset

```powershell
python scrapping.py
```

This will export the structured dataset to `data/healthcare_data.json`.
