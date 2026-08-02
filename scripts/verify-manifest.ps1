param(
    [string]$ManifestPath = "$PSScriptRoot\..\public\manifest.json",
    [string]$PayloadPath = "$PSScriptRoot\..\manifest.payload.json",
    [string]$PublicKeyPath = "$PSScriptRoot\..\manifest-signing-public.pem"
)

$ErrorActionPreference = 'Stop'
$openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
if (-not (Test-Path -LiteralPath $openssl)) {
    $openssl = 'openssl'
}

$resolvedManifest = (Resolve-Path -LiteralPath $ManifestPath).Path
$resolvedPayload = (Resolve-Path -LiteralPath $PayloadPath).Path
$resolvedPublicKey = (Resolve-Path -LiteralPath $PublicKeyPath).Path
$envelope = Get-Content -Raw -LiteralPath $resolvedManifest | ConvertFrom-Json

if ($envelope.algorithm -ne 'ECDSA_P256_SHA256') {
    throw "Unsupported manifest algorithm: $($envelope.algorithm)"
}

$payloadBytes = [Convert]::FromBase64String($envelope.payload)
$signatureBytes = [Convert]::FromBase64String($envelope.signature)
$expectedBytes = [System.IO.File]::ReadAllBytes($resolvedPayload)
if (-not [System.Linq.Enumerable]::SequenceEqual([byte[]]$payloadBytes, [byte[]]$expectedBytes)) {
    throw 'The signed payload does not match manifest.payload.json byte for byte.'
}

$payloadTemp = [System.IO.Path]::GetTempFileName()
$signatureTemp = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllBytes($payloadTemp, $payloadBytes)
    [System.IO.File]::WriteAllBytes($signatureTemp, $signatureBytes)
    & $openssl dgst -sha256 -verify $resolvedPublicKey -signature $signatureTemp $payloadTemp
    if ($LASTEXITCODE -ne 0) {
        throw 'Endpoint manifest signature verification failed.'
    }
}
finally {
    Remove-Item -LiteralPath $payloadTemp -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $signatureTemp -Force -ErrorAction SilentlyContinue
}

$payload = [System.Text.Encoding]::UTF8.GetString($payloadBytes) | ConvertFrom-Json
Write-Host "Verified manifest version $($payload.version), valid until $($payload.expiresAt)."
