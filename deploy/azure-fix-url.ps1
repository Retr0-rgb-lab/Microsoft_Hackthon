# Correct the Foundry endpoint and verify the settings that are in place.
$rg = 'inside-the-game-hackathon'
$app = 'nextplay-ai'

az webapp config appsettings set --name $app --resource-group $rg --settings `
  ITG_MODEL_BASE_URL="https://itg-foundry-2026.cognitiveservices.azure.com/openai/v1" `
  --output none
Write-Host "set exit=$LASTEXITCODE"

Write-Host "== settings (the key is not printed) =="
az webapp config appsettings list --name $app --resource-group $rg --output json |
  ForEach-Object { ($_ | ConvertFrom-Json) } |
  ForEach-Object { if ($_.name -eq 'ITG_MODEL_API_KEY') { "$($_.name)=<set, length $($_.value.Length)>" } else { "$($_.name)=$($_.value)" } }
