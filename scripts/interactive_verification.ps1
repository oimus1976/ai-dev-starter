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
        $text | Out-File -LiteralPath $Context.LogPath -Append -Encoding utf8
        Write-Host $text
    }
}

function ConvertTo-VerificationJsonString {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$Value
    )

    $text = if ($null -eq $Value) { "" } else { [string]$Value }
    return (ConvertTo-Json -InputObject $text -Compress)
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
    Write-VerificationLog -Context $Context -InputObject ("{0}={1}" -f $Name, $encoded)
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
    $argumentsJson = ConvertTo-Json -InputObject @($Arguments) -Compress

    Write-VerificationField -Context $Context -Name "COMMAND" -Value $actualCommand
    Write-VerificationField -Context $Context -Name "COMMAND_EXECUTABLE" -Value $Command
    Write-VerificationLog -Context $Context -InputObject ("COMMAND_ARGUMENTS_JSON={0}" -f $argumentsJson)

    if (-not [string]::IsNullOrWhiteSpace($DisplayCommand) -and $DisplayCommand -ne $actualCommand) {
        Write-VerificationField -Context $Context -Name "DISPLAY_COMMAND" -Value $DisplayCommand
    }

    $resolvedCommand = Get-Command `
        -Name $Command `
        -CommandType Application `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $resolvedCommand) {
        Write-VerificationLog -Context $Context -InputObject "EXIT_CODE=UNAVAILABLE"
        throw ("native executable was not found: {0}" -f $Command)
    }

    $resolvedPath = $resolvedCommand.Source
    if ([string]::IsNullOrWhiteSpace($resolvedPath)) {
        Write-VerificationLog -Context $Context -InputObject "EXIT_CODE=UNAVAILABLE"
        throw ("native executable resolved without a usable path: {0}" -f $Command)
    }

    Write-VerificationField -Context $Context -Name "COMMAND_RESOLVED" -Value $resolvedPath

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Clear the global automatic variable rather than creating a local
        # shadow. A successfully launched native application must establish
        # a fresh exit status for this invocation.
        $global:LASTEXITCODE = $null

        # Windows PowerShell 5.1 can surface redirected native stderr as
        # ErrorRecord objects. Native success remains authoritative by exit code.
        # Invoke the already-resolved application path so functions/aliases
        # cannot shadow the executable between resolution and launch.
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
        Write-VerificationLog -Context $Context -InputObject "EXIT_CODE=UNAVAILABLE"
        throw ("native command did not produce an exit code: {0}" -f $actualCommand)
    }

    Write-VerificationLog -Context $Context -InputObject ("EXIT_CODE={0}" -f $exitCode)

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
            Write-Host ("LOG_WRITE_ERROR={0}" -f $_.Exception.Message)
        }

        throw $originalError
    }
    finally {
        # This is the only terminal-marker write in an initialized attempt.
        try {
            Write-VerificationLog -Context $context -InputObject ("RESULT={0}" -f $outcome)
        }
        catch {
            $terminalLogError = $_
            Write-Host ("LOG_WRITE_ERROR={0}" -f $terminalLogError.Exception.Message)
            Write-Host ("LOG={0}" -f $logPath)

            # A body that otherwise succeeded must not report success when its
            # terminal PASS evidence could not be persisted.
            if ($outcome -eq "PASS") {
                throw $terminalLogError
            }
        }

        Write-Host ("LOG={0}" -f $logPath)
    }
}
