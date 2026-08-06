# Space Facing Optimisation Dashboard

Streamlit dashboard for reviewing kitchen department space optimisation outputs from CSV or Excel extracts.

## What it does

- Loads the latest local `space_opt_2_*.csv` extract or a manually uploaded CSV or Excel file.
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

## Data source

The app is currently file-based. It does not require Snowflake credentials.

For hosted Streamlit use, either commit a safe sample extract or upload a file through the app after it starts.

## Repository notes

Local CSV and Excel extracts are ignored by Git by default.