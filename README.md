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

## Repository notes

Local CSV and Excel extracts are ignored by Git because the dashboard is intended to query Snowflake live.