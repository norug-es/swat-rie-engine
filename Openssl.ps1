param(
    [int]$Bytes = 32,
    [switch]$WriteEnv,
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

function New-SecureHex {
    param([int]$LengthBytes)

    $buffer = New-Object byte[] $LengthBytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return (($buffer | ForEach-Object { $_.ToString("x2") }) -join "")
}

$API_KEY = New-SecureHex -LengthBytes $Bytes
$EVIDENCE_SIGNING_SECRET = New-SecureHex -LengthBytes $Bytes

Write-Host "Generated secure secrets:" -ForegroundColor Cyan
Write-Host ""
Write-Host "RIE_API_KEY=$API_KEY"
Write-Host "EVIDENCE_SIGNING_SECRET=$EVIDENCE_SIGNING_SECRET"

if ($WriteEnv) {
    if (-not (Test-Path $EnvFile)) {
        New-Item -ItemType File -Path $EnvFile -Force | Out-Null
    }

    $content = Get-Content $EnvFile -ErrorAction SilentlyContinue

    function Upsert-EnvValue {
        param(
            [string[]]$Lines,
            [string]$Key,
            [string]$Value
        )

        $found = $false
        $result = @()

        foreach ($line in $Lines) {
            if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
                $found = $true
                $result += "$Key=$Value"
            }
            else {
                $result += $line
            }
        }

        if (-not $found) {
            $result += "$Key=$Value"
        }

        return $result
    }

    $content = Upsert-EnvValue -Lines $content -Key "RIE_API_KEY" -Value $API_KEY
    $content = Upsert-EnvValue -Lines $content -Key "EVIDENCE_SIGNING_SECRET" -Value $EVIDENCE_SIGNING_SECRET

    Set-Content -Path $EnvFile -Value $content -Encoding UTF8

    Write-Host ""
    Write-Host "[OK] Secrets written to $EnvFile" -ForegroundColor Green
    Write-Host "[INFO] Recreate dependent containers so they load the new values." -ForegroundColor Yellow
}