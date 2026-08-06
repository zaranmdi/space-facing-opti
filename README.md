# Space Facing Optimisation Dashboard

Streamlit dashboard for reviewing kitchen department space optimisation outputs from Snowflake.

## What it does

- Runs the optimisation SQL from `space_opti_code.sql` against Snowflake.
- Surfaces space-add, donor, high-WOS, and no-sales opportunities.
- Summarises opportunities across planograms, stores, and item-locations.

## Local run

1. Install dependencies:

   ```powershell
   py -3 -m pip install -r requirements.txt
   ```

2. Start the app:

   ```powershell
   py -3 -m streamlit run app.py
   ```

## Snowflake access

The app uses the connection helper in `snowflakes.py`. Do not commit credentials or secret files.

For hosted deployments, configure Snowflake credentials through environment variables. The helper supports password, named-connection, or OAuth-style non-interactive auth. If no non-interactive settings are present, local runs fall back to `externalbrowser`.

## Azure App Service

Azure App Service deployment steps are documented in `DEPLOY_AZURE_APP_SERVICE.md`.

The repo includes `startup.sh` for the App Service startup command.

GitHub Actions deployment is available in `.github/workflows/deploy-azure-app-service.yml`.

## Streamlit Community Cloud

Streamlit Community Cloud deployment steps are documented in `DEPLOY_STREAMLIT_CLOUD.md`.

Use `streamlit_secrets.example.toml` as the template for hosted Streamlit secrets.

## Repository notes

Local CSV and Excel extracts are ignored by Git because the dashboard is intended to query Snowflake live.