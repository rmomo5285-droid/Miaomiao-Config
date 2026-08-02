param(
    [Parameter(Mandatory = $true)]
    [string]$PrivateKeyPath,

    [Parameter(Mandatory = $true)]
    [string]$PassphraseFile,

    [string]$PayloadPath = "$PSScriptRoot\..\manifest.payload.json",
    [string]$OutputPath = "$PSScriptRoot\..\public\manifest.json"
)

$ErrorActionPreference = 'Stop'
$openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
if (-not (Test-Path -LiteralPath $openssl)) {
    $openssl = 'openssl'
}

$resolvedPayload = (Resolve-Path -LiteralPath $PayloadPath).Path
$resolvedKey = (Resolve-Path -LiteralPath $PrivateKeyPath).Path
$resolvedPassphrase = (Resolve-Path -LiteralPath $PassphraseFile).Path
$outputDirectory = Split-Path -Parent $OutputPath
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null

$signaturePath = [System.IO.Path]::GetTempFileName()
try {
    & $openssl dgst -sha256 -sign $resolvedKey -passin "file:$resolvedPassphrase" -out $signaturePath $resolvedPayload
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSSL failed to sign the endpoint manifest."
    }

    $envelope = [ordered]@{
        algorithm = 'ECDSA_P256_SHA256'
        payload = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($resolvedPayload))
        signature = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($signaturePath))
    }
    $json = ($envelope | ConvertTo-Json -Depth 4).Replace("`r`n", "`n")
    [System.IO.File]::WriteAllText($OutputPath, "$json`n", [System.Text.UTF8Encoding]::new($false))
}
finally {
    Remove-Item -LiteralPath $signaturePath -Force -ErrorAction SilentlyContinue
}
