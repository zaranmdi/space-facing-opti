# Azure App Service Deployment

This project can run on Azure App Service for Linux.

## GitHub repository

Source repository:

- `https://github.com/zaranmdi/space-facing-opti`

## Pre-reqs

- Azure subscription access
- Azure CLI installed and signed in with `az login`
- Snowflake credentials that work without `externalbrowser`
- A created Azure App Service instance
- GitHub repository secrets and variables configured for deployment

## GitHub Actions workflow

This repo includes `.github/workflows/deploy-azure-app-service.yml`.

It deploys on pushes to `main` and on manual runs from the Actions tab.

### GitHub repository secrets

Create these in GitHub under Settings > Secrets and variables > Actions > Secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

These are for Azure OIDC login, which Microsoft recommends over publish profiles.

### GitHub repository variables

Create these in GitHub under Settings > Secrets and variables > Actions > Variables:

- `AZURE_WEBAPP_NAME`
- `AZURE_RESOURCE_GROUP`

The workflow reads those values to target the correct App Service.

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

The GitHub Actions workflow also applies this startup command on each deployment.

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

## Deploy updates from GitHub Actions

Once the GitHub secrets and variables are configured, any push to `main` will trigger a deployment automatically.

You can also run it manually:

1. Open the Actions tab in the GitHub repository.
2. Open `Deploy Streamlit Dashboard to Azure App Service`.
3. Select `Run workflow`.

## Dashboard link

After deployment, your dashboard URL is:

```text
https://<appName>.azurewebsites.net
```

For this repo, once deployed, the link format will be:

```text
https://<your-azure-webapp-name>.azurewebsites.net
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

## OIDC setup note

Before the workflow can log in, Azure must trust this GitHub repository through a federated credential for the `main` branch or through App Service Deployment Center. The Microsoft guidance for GitHub Actions with App Service recommends OIDC over publish profiles.