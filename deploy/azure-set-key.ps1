# Put the model key in the instance's settings. The key never enters the
# repository: it is read from the local secret file and handed to Azure as an
# encrypted app setting.
$ErrorActionPreference = 'Continue'
$rg = 'inside-the-game-hackathon'
$app = 'nextplay-ai'

# The key lives in the WSL home, not the Windows one. WSL shares its
# filesystem under \\wsl.localhost, so the file is read in place and never
# copied to a Windows-visible path.
$keyPath = '\\wsl.localhost\Ubuntu\home\peleclic\.itg-foundry-key'
if (-not (Test-Path $keyPath)) { $keyPath = '\\wsl$\Ubuntu\home\peleclic\.itg-foundry-key' }
if (-not (Test-Path $keyPath)) {
  Write-Host "no key file at $keyPath"
  exit 1
}
$key = (Get-Content $keyPath -Raw).Trim()
if ($key.Length -lt 20) {
  Write-Host "key file looks wrong (length $($key.Length))"
  exit 1
}
Write-Host "key length=$($key.Length)"

az webapp config appsettings set --name $app --resource-group $rg --settings `
  ITG_MODEL_API_KEY="$key" `
  --output none
Write-Host "exit=$LASTEXITCODE"

# Show the setting names only, never the value.
az webapp config appsettings list --name $app --resource-group $rg --query '[].name' --output tsv
