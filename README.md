# Health Care Data Repository

This repository stores scraped synthetic healthcare data from:

`https://manoharshasappa.github.io/HealthCare_DataWebsite/`

## Structure

```text
Health-care/
|-- data/
|   `-- healthcare_data.json
|-- raw/
|   `-- .gitkeep
|-- scrapping.py
|-- README.md
`-- .gitignore
```

## Folders

- `data/` contains the final structured JSON dataset.
- `raw/` is reserved for raw downloaded files such as HTML pages or HL7 files.
- `scrapping.py` contains the script used to scrape and export the data.

## Run

```powershell
python scrapping.py
```

This will export the structured dataset to `data/healthcare_data.json`.
