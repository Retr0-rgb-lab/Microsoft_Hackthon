# Upload the application package to the App Service instance.
$ErrorActionPreference = 'Continue'
$rg = 'inside-the-game-hackathon'
$app = 'nextplay-ai'
$zip = 'E:\College_Projects\Microsoft_Hackathon\.deploy\app.zip'

Write-Host "== deploy =="
az webapp deploy --name $app --resource-group $rg --src-path $zip --type zip --timeout 1800 --output json
Write-Host "exit=$LASTEXITCODE"
