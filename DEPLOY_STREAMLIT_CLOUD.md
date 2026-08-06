# Streamlit Community Cloud Deployment

Source repository:

- `https://github.com/zaranmdi/space-facing-opti`

## What this gives you

If deployment succeeds, Streamlit Community Cloud gives you a hosted app URL in the form:

```text
https://<your-app-name>.streamlit.app
```

## Important constraint

This app queries Snowflake live. Streamlit Community Cloud can host it only if both of these are true:

1. Snowflake authentication is non-interactive.
2. The Snowflake endpoint is reachable from Streamlit Community Cloud.

Your current Snowflake account uses a PrivateLink-style hostname. If that endpoint is not reachable from Streamlit Community Cloud, the deployment may start but queries will fail.

## Repository is prepared for Streamlit secrets

The app now reads Snowflake settings from either:

1. environment variables
2. Streamlit secrets
3. local `.env`

Use `streamlit_secrets.example.toml` as the template for hosted secrets.

## Deploy steps

1. Open Streamlit Community Cloud.
2. Select `Create app`.
3. Choose the GitHub repo `zaranmdi/space-facing-opti`.
4. Set the main file path to `app.py`.
5. Open `Advanced settings`.
6. Paste secrets based on `streamlit_secrets.example.toml`.
7. Deploy the app.

## Recommended secrets payload

```toml
SNOWFLAKE_ACCOUNT = "bunnings.australia-east.privatelink"
SNOWFLAKE_USER = "your_user"
SNOWFLAKE_ROLE = "SPACE_PRODUCTIVITY_ANALYST_DE_GENERAL_PRD"
SNOWFLAKE_WAREHOUSE = "PRD_DEVELOPER_WH"
SNOWFLAKE_PASSWORD = "your_password"
```

If password auth is not approved, replace it with the non-interactive auth method approved by your Snowflake team.

## Result

After Streamlit finishes deploying, it will show the dashboard URL directly in the Streamlit workspace.

## If deployment fails

Typical reasons for failure here are:

1. Snowflake auth still expects browser login.
2. Streamlit Cloud cannot reach the Snowflake PrivateLink endpoint.
3. Snowflake credentials are missing or invalid.