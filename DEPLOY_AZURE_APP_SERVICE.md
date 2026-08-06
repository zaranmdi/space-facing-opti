# Azure App Service Deployment

This project can run on Azure App Service for Linux.

## Pre-reqs

- Azure subscription access
- Azure CLI installed and signed in with `az login`
- Snowflake credentials that work without `externalbrowser`

## Required app settings

Create these in Azure App Service under Settings > Environment variables.

- `SCM_DO_BUILD_DURING_DEPLOYMENT` = `true`
- `SNOWFLAKE_ACCOUNT` = `bunnings.australia-east.privatelink`
- `SNOWFLAKE_USER` = your Snowflake user
- `SNOWFLAKE_ROLE` = `SPACE_PRODUCTIVITY_ANALYST_DE_GENERAL_PRD`
- `SNOWFLAKE_WAREHOUSE` = `PRD_DEVELOPER_WH`

Then choose one authentication pattern:

- Password auth:
  - `SNOWFLAKE_PASSWORD`
  - optional `SNOWFLAKE_AUTHENTICATOR=username_password_mfa`
- Named connection:
  - `SNOWFLAKE_CONNECTION_NAME`
- OAuth:
  - `SNOWFLAKE_TOKEN`
  - `SNOWFLAKE_AUTHENTICATOR=oauth`

## Create the App Service

```powershell
$resourceGroupName = "space-facing-opti-rg"
$appName = "space-facing-opti-zahra"
$location = "australiaeast"

az login
az webapp up `
  --name $appName `
  --resource-group $resourceGroupName `
  --location $location `
  --runtime "PYTHON:3.14" `
  --sku B1 `
  --logs
```

## Configure the startup command

Azure App Service auto-detects Flask and Django, not Streamlit. Set the startup command to run the script in this repo.

```powershell
az webapp config set `
  --resource-group $resourceGroupName `
  --name $appName `
  --startup-file "bash startup.sh"
```

## Add app settings

```powershell
az webapp config appsettings set `
  --resource-group $resourceGroupName `
  --name $appName `
  --settings `
    SCM_DO_BUILD_DURING_DEPLOYMENT=true `
    SNOWFLAKE_ACCOUNT=bunnings.australia-east.privatelink `
    SNOWFLAKE_USER=<your-user> `
    SNOWFLAKE_ROLE=SPACE_PRODUCTIVITY_ANALYST_DE_GENERAL_PRD `
    SNOWFLAKE_WAREHOUSE=PRD_DEVELOPER_WH `
    SNOWFLAKE_PASSWORD=<your-password>
```

If your account requires MFA for programmatic sign-in, replace password-only auth with the approved non-interactive method from your Snowflake team.

## Deploy updates from the repo folder

```powershell
az webapp up `
  --name $appName `
  --resource-group $resourceGroupName `
  --runtime "PYTHON:3.14"
```

## Dashboard link

After deployment, your dashboard URL is:

```text
https://<appName>.azurewebsites.net
```

## Logs

```powershell
az webapp log config `
  --resource-group $resourceGroupName `
  --name $appName `
  --web-server-logging filesystem

az webapp log tail `
  --resource-group $resourceGroupName `
  --name $appName
```

## Important note

If the Snowflake PrivateLink endpoint is not reachable from the selected App Service environment, the app will start but queries will fail. In that case, deploy the same repo to an Azure environment with the required private networking in place.