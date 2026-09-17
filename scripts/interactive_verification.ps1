function Write-VerificationInternalRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Record
    )

    if ($Record -match "[`r`n]") {
        throw "internal verification record must be one physical line"
    }

    $Record | Microsoft.PowerShell.Utility\Out-File -LiteralPath $Context.LogPath -Append -Encoding utf8
    Microsoft.PowerShell.Utility\Write-Host $Record
}

function Write-VerificationLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Context,

        [Parameter(ValueFromPipeline = $true)]
        [AllowNull()]
        [object]$InputObject
    )

    process {
        Write-VerificationField -Context $Context -Name "DETAIL" -Value $InputObject
    }
}

function ConvertTo-VerificationJsonString {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$Value
    )

    $text = if ($null -eq $Value) { "" } else { [string]$Value }
    return (Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $text -Compress)
}

function Write-VerificationField {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Context,

        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Z0-9_]+$')]
        [string]$Name,

        [AllowNull()]
        [object]$Value
    )

    $encoded = ConvertTo-VerificationJsonString -Value $Value
    Write-VerificationInternalRecord -Context $Context -Record ("{0}={1}" -f $Name, $encoded)
}

function Invoke-VerificationNative {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Command,

        [string[]]$Arguments = @(),

        [string]$DisplayCommand,

        [int[]]$AcceptedExitCodes = @(0)
    )

    $actualCommand = (@($Command) + $Arguments) -join " "
    $argumentsJson = Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject @($Arguments) -Compress

    Write-VerificationField -Context $Context -Name "COMMAND" -Value $actualCommand
    Write-VerificationField -Context $Context -Name "COMMAND_EXECUTABLE" -Value $Command
    Write-VerificationInternalRecord -Context $Context -Record ("COMMAND_ARGUMENTS_JSON={0}" -f $argumentsJson)

    if (-not [string]::IsNullOrWhiteSpace($DisplayCommand) -and $DisplayCommand -ne $actualCommand) {
        Write-VerificationField -Context $Context -Name "DISPLAY_COMMAND" -Value $DisplayCommand
    }

    $resolvedCommand = Microsoft.PowerShell.Core\Get-Command `
        -Name $Command `
        -CommandType Application `
        -ErrorAction SilentlyContinue |
        Microsoft.PowerShell.Utility\Select-Object -First 1

    if ($null -eq $resolvedCommand) {
        Write-VerificationInternalRecord -Context $Context -Record "EXIT_CODE=UNAVAILABLE"
        throw ("native executable was not found: {0}" -f $Command)
    }

    if ($resolvedCommand -isnot [System.Management.Automation.ApplicationInfo]) {
        Write-VerificationInternalRecord -Context $Context -Record "EXIT_CODE=UNAVAILABLE"
        throw ("native command did not resolve to an application: {0}" -f $Command)
    }

    $resolvedPath = $resolvedCommand.Source
    if (
        [string]::IsNullOrWhiteSpace($resolvedPath) -or
        -not [System.IO.Path]::IsPathRooted($resolvedPath)
    ) {
        Write-VerificationInternalRecord -Context $Context -Record "EXIT_CODE=UNAVAILABLE"
        throw ("native executable resolved without a usable path: {0}" -f $Command)
    }

    Write-VerificationField -Context $Context -Name "COMMAND_RESOLVED" -Value $resolvedPath

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $global:LASTEXITCODE = $null
        $ErrorActionPreference = "Continue"
        $output = & $resolvedPath @Arguments 2>&1
        $exitCode = $global:LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($item in $output) {
        Write-VerificationField -Context $Context -Name "NATIVE_OUTPUT" -Value $item
    }

    if ($null -eq $exitCode) {
        Write-VerificationInternalRecord -Context $Context -Record "EXIT_CODE=UNAVAILABLE"
        throw ("native command did not produce an exit code: {0}" -f $actualCommand)
    }

    Write-VerificationInternalRecord -Context $Context -Record ("EXIT_CODE={0}" -f $exitCode)

    if ($AcceptedExitCodes -notcontains $exitCode) {
        throw ("native command failed with exit code {0}: {1}" -f $exitCode, $actualCommand)
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Stop-VerificationBlocked {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $exception = [System.InvalidOperationException]::new($Message)
    $exception.Data["VerificationOutcome"] = "BLOCKED"
    throw $exception
}

function Invoke-VerificationAttempt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9._-]+$')]
        [string]$ProjectName,

        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9._-]+$')]
        [string]$Purpose,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Body,

        [string]$LogRoot
    )

    $ErrorActionPreference = "Stop"

    if ([string]::IsNullOrWhiteSpace($LogRoot)) {
        if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
            throw "TEMP is not available and LogRoot was not provided"
        }
        $LogRoot = Microsoft.PowerShell.Management\Join-Path $env:TEMP ("{0}-logs\{1}" -f $ProjectName, $Purpose)
    }

    Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $LogRoot | Microsoft.PowerShell.Core\Out-Null

    $stamp = Microsoft.PowerShell.Utility\Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $attemptId = "{0}-{1}-{2}" -f $stamp, $PID, $suffix
    $logPath = Microsoft.PowerShell.Management\Join-Path $LogRoot ("attempt-{0}.log" -f $attemptId)

    "FORMAT=interactive-verification-v1" | Microsoft.PowerShell.Utility\Out-File -LiteralPath $logPath -Encoding utf8

    $context = [pscustomobject]@{
        AttemptId = $attemptId
        ProjectName = $ProjectName
        Purpose = $Purpose
        LogPath = $logPath
    }

    $outcome = "FAIL"

    try {
        Write-VerificationInternalRecord -Context $context -Record ("ATTEMPT_ID={0}" -f $attemptId)
        Write-VerificationInternalRecord -Context $context -Record ("PROJECT={0}" -f $ProjectName)
        Write-VerificationInternalRecord -Context $context -Record ("PURPOSE={0}" -f $Purpose)

        & $Body $context
        $outcome = "PASS"
    }
    catch {
        $originalError = $_
        $marker = $null
        $currentException = $originalError.Exception
        while ($null -ne $currentException -and $null -eq $marker) {
            if ($currentException.Data.Contains("VerificationOutcome")) {
                $marker = [string]$currentException.Data["VerificationOutcome"]
            }
            $currentException = $currentException.InnerException
        }

        if ($marker -eq "BLOCKED") {
            $outcome = "BLOCKED"
        }

        try {
            Write-VerificationField -Context $context -Name "ERROR" -Value $originalError.Exception.Message
        }
        catch {
            Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $_.Exception.Message)
        }

        throw $originalError
    }
    finally {
        try {
            Write-VerificationInternalRecord -Context $context -Record ("RESULT={0}" -f $outcome)
        }
        catch {
            $terminalLogError = $_
            Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $terminalLogError.Exception.Message)
            Microsoft.PowerShell.Utility\Write-Host ("LOG={0}" -f $logPath)
            if ($outcome -eq "PASS") {
                throw $terminalLogError
            }
        }

        Microsoft.PowerShell.Utility\Write-Host ("LOG={0}" -f $logPath)
    }
}

$verificationPlanController = [System.IO.Path]::Combine($PSScriptRoot, "verification_plan.ps1")
. $verificationPlanController
