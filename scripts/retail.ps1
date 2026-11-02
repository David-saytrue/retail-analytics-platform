param(
    [ValidateSet('Start','PrepareDemo','Trigger','Status','Stop','CopyAirflowPassword')]
    [string]$Action = 'Status'
)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
$credentialFile = Join-Path $projectDirectory 'artifacts/local-credentials.clixml'
function New-LocalSecret {
    $randomBytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
    ConvertTo-SecureString ([Convert]::ToHexString($randomBytes)) -AsPlainText -Force
}
if (-not (Test-Path -LiteralPath $credentialFile)) {
    if ($Action -ne 'Start') { throw 'Run -Action Start first.' }
    $existingVolumes = & docker volume ls --filter 'label=com.docker.compose.project=retail-analytics' --format '{{.Name}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker is unavailable.' }
    if ($existingVolumes) {
        throw 'Existing volumes found without saved credentials. Restore artifacts/local-credentials.clixml; do not reset volumes or generate a replacement password.'
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $credentialFile) | Out-Null
    [pscustomobject]@{RetailPassword=New-LocalSecret; AirflowPassword=New-LocalSecret} |
        Export-Clixml -LiteralPath $credentialFile
}
$secrets = Import-Clixml -LiteralPath $credentialFile
$previousRetailPassword = $env:RETAIL_DB_PASSWORD
$previousAirflowPassword = $env:AIRFLOW_DB_PASSWORD
$env:RETAIL_DB_PASSWORD = ([pscredential]::new('retail',$secrets.RetailPassword)).GetNetworkCredential().Password
$env:AIRFLOW_DB_PASSWORD = ([pscredential]::new('airflow',$secrets.AirflowPassword)).GetNetworkCredential().Password
$composeArguments = @('compose','-f','compose.yaml','-f','compose.airflow.yaml','--profile','airflow')
function Invoke-RetailCompose([string[]]$CommandArguments) {
    & docker @composeArguments @CommandArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed ($LASTEXITCODE)." }
}
try {
    switch ($Action) {
        Start {
            Invoke-RetailCompose @('build','app','airflow')
            Invoke-RetailCompose @('up','-d','--wait','airflow')
            Write-Output 'Airflow: http://localhost:8086 (user admin). New DAGs start paused.'
        }
        PrepareDemo {
            Invoke-RetailCompose @('run','--rm','--no-deps','--entrypoint','python','app','pipeline.py','prepare-demo')
        }
        Trigger {
            Invoke-RetailCompose @('exec','-T','airflow','airflow','dags','unpause','retail_daily_ingestion')
            Invoke-RetailCompose @('exec','-T','airflow','airflow','dags','trigger','retail_daily_ingestion')
        }
        Status {
            Invoke-RetailCompose @('ps')
            Invoke-RetailCompose @('exec','-T','airflow','airflow','dags','list-runs','retail_daily_ingestion','--output','table')
        }
        Stop { Invoke-RetailCompose @('stop','airflow','airflow-db','db') }
        CopyAirflowPassword {
            $readPassword = 'import json, pathlib, os; p=pathlib.Path(os.environ["AIRFLOW_HOME"])/"simple_auth_manager_passwords.json.generated"; print(json.loads(p.read_text())["admin"])'
            $generatedPassword = & docker @composeArguments exec -T airflow python -c $readPassword
            if ($LASTEXITCODE -ne 0) { throw 'Airflow password is not available yet.' }
            Set-Clipboard -Value ($generatedPassword -join '').Trim()
            Write-Output 'Airflow admin password copied to the clipboard. Paste it into the local login form.'
        }
    }
} finally {
    $env:RETAIL_DB_PASSWORD = $previousRetailPassword
    $env:AIRFLOW_DB_PASSWORD = $previousAirflowPassword
}
