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
        $text = if ($null -eq $InputObject) { "" } else { [string]$InputObject }
        Write-Host $text
        $text | Out-File -LiteralPath $Context.LogPath -Append -Encoding utf8
    }
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

    if ([string]::IsNullOrWhiteSpace($DisplayCommand)) {
        $DisplayCommand = (@($Command) + $Arguments) -join " "
    }

    Write-VerificationLog -Context $Context -InputObject ("COMMAND={0}" -f $DisplayCommand)

    $output = @(
        & $Command @Arguments 2>&1 | ForEach-Object {
            Write-VerificationLog -Context $Context -InputObject $_
            $_
        }
    )
    $exitCode = $LASTEXITCODE

    Write-VerificationLog -Context $Context -InputObject ("EXIT_CODE={0}" -f $exitCode)

    if ($AcceptedExitCodes -notcontains $exitCode) {
        throw ("native command failed with exit code {0}: {1}" -f $exitCode, $DisplayCommand)
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
        $LogRoot = Join-Path $env:TEMP ("{0}-logs\{1}" -f $ProjectName, $Purpose)
    }

    New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $attemptId = "{0}-{1}-{2}" -f $stamp, $PID, $suffix
    $logPath = Join-Path $LogRoot ("attempt-{0}.log" -f $attemptId)

    # Explicit UTF-8 creation. Windows PowerShell 5.1 may include a BOM; both
    # Windows PowerShell and PowerShell 7 treat the resulting file as UTF-8.
    "FORMAT=interactive-verification-v1" | Out-File -LiteralPath $logPath -Encoding utf8

    $context = [pscustomobject]@{
        AttemptId = $attemptId
        ProjectName = $ProjectName
        Purpose = $Purpose
        LogPath = $logPath
    }

    $outcome = "FAIL"

    try {
        Write-VerificationLog -Context $context -InputObject ("ATTEMPT_ID={0}" -f $attemptId)
        Write-VerificationLog -Context $context -InputObject ("PROJECT={0}" -f $ProjectName)
        Write-VerificationLog -Context $context -InputObject ("PURPOSE={0}" -f $Purpose)

        & $Body $context

        # PASS is assigned only after the entire guarded body completes.
        $outcome = "PASS"
    }
    catch {
        $marker = $null
        $currentException = $_.Exception
        while ($null -ne $currentException -and $null -eq $marker) {
            if ($currentException.Data.Contains("VerificationOutcome")) {
                $marker = [string]$currentException.Data["VerificationOutcome"]
            }
            $currentException = $currentException.InnerException
        }

        if ($marker -eq "BLOCKED") {
            $outcome = "BLOCKED"
        }

        Write-VerificationLog -Context $context -InputObject ("ERROR={0}" -f $_.Exception.Message)
        throw
    }
    finally {
        # This is the only terminal-marker write in an initialized attempt.
        Write-VerificationLog -Context $context -InputObject ("RESULT={0}" -f $outcome)
        Write-Host ("LOG={0}" -f $logPath)
    }
}
