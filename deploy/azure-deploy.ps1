# Deploy the NextPlay AI dashboard to Azure App Service.
# The az CLI is a .cmd shim on Windows, so cmd.exe re-parses the command line
# and a literal "|" in --runtime would become a pipe. The stop-parsing token
# (--%) hands the arguments to the command untouched.
$ErrorActionPreference = 'Continue'
$rg = 'inside-the-game-hackathon'
$app = 'nextplay-ai'
$plan = 'itg-plan'

Write-Host "== plan =="
az appservice plan show --name $plan --resource-group $rg --query '{name:name,sku:sku.name,state:state}' --output json
if ($LASTEXITCODE -ne 0) {
  az appservice plan create --name $plan --resource-group $rg --location germanywestcentral --sku B1 --output none
}

Write-Host "== web app =="
az webapp show --name $app --resource-group $rg --query '{url:defaultHostName,state:state}' --output json
if ($LASTEXITCODE -ne 0) {
  az --% webapp create --name nextplay-ai --resource-group inside-the-game-hackathon --plan itg-plan --runtime "PYTHON|3.12" --output none
}

Write-Host "== configuration =="
az webapp config set --name $app --resource-group $rg --startup-file startup.sh
az webapp config set --name $app --resource-group $rg --always-on true
az webapp config set --name $app --resource-group $rg --http20-enabled true

$publicHost = az webapp show --name $app --resource-group $rg --query defaultHostName --output tsv
Write-Host "publicHost=$publicHost"
az webapp config appsettings set --name $app --resource-group $rg --settings `
  ITG_ALLOWED_HOSTS="$publicHost" `
  ITG_MODEL_BASE_URL="https://itg-foundry.openai.azure.com/openai/v1" `
  ITG_MODEL_NAME="gpt-4.1-mini" `
  ITG_DAILY_CALL_CAP="200" `
  WEBSITES_PORT="8000" `
  --output none

Write-Host "== state =="
az webapp show --name $app --resource-group $rg --query '{url:defaultHostName,state:state,runtime:siteConfig.pythonVersion,startup:siteConfig.appCommandLine}' --output json
