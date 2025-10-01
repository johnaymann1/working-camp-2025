# Working Camp 2025 Dashboard

This is a Streamlit dashboard that displays live counts from a Google Sheets worksheet for the Working Camp 2025 project.

## Local development

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run WorkingCamp2025_Fixed.py
```

## Deployment (Streamlit Community Cloud)

1. Create a GitHub repository and push this project.
2. In Streamlit Community Cloud, create a new app and link your GitHub repo.
3. Add your Google service account JSON as a secret (key name: `GOOGLE_SERVICE_ACCOUNT_JSON`) in Streamlit app settings.
4. Ensure `requirements.txt` is present and `service_account.json` is added to `.gitignore`.

## Security

- Never commit `service_account.json` to GitHub. Use host secrets instead.
