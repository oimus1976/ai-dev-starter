$script:AttemptStates = @{}

function Get-VerificationAttemptState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Context
    )

    if ($null -eq $Context.PSObject.Properties['AttemptToken']) {
        throw 'verification context does not contain an attempt capability'
    }

    $token = [string]$Context.AttemptToken
    if ([string]::IsNullOrWhiteSpace($token) -or -not $script:AttemptStates.ContainsKey($token)) {
        throw 'verification attempt capability is not active'
    }

    return $script:AttemptStates[$token]
}

function Write-VerificationInternalRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$AttemptToken,

        [Parameter(Mandatory = $true)]
        [string]$Record
    )

    if ($Record -match "[`r`n]") {
        throw 'internal verification record must be one physical line'
    }
    if (-not $script:AttemptStates.ContainsKey($AttemptToken)) {
        throw 'verification attempt capability is not active'
    }

    $state = $script:AttemptStates[$AttemptToken]
    $state.Writer.WriteLine($Record)
    $state.Writer.Flush()
    Microsoft.PowerShell.Utility\Write-Host $Record
}

function ConvertTo-VerificationJsonString {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$Value
    )

    $text = if ($null -eq $Value) { '' } else { [string]$Value }
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

    if ($Name -eq 'RESULT') {
        throw 'RESULT is wrapper-owned and cannot be written by guarded body code'
    }

    $state = Get-VerificationAttemptState -Context $Context
    $encoded = ConvertTo-VerificationJsonString -Value $Value
    Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record ("{0}={1}" -f $Name, $encoded)
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
        Write-VerificationField -Context $Context -Name 'DETAIL' -Value $InputObject
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

    $state = Get-VerificationAttemptState -Context $Context
    $actualCommand = (@($Command) + $Arguments) -join ' '
    $argumentsJson = Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject @($Arguments) -Compress

    Write-VerificationField -Context $Context -Name 'COMMAND' -Value $actualCommand
    Write-VerificationField -Context $Context -Name 'COMMAND_EXECUTABLE' -Value $Command
    Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record ("COMMAND_ARGUMENTS_JSON={0}" -f $argumentsJson)

    if (-not [string]::IsNullOrWhiteSpace($DisplayCommand) -and $DisplayCommand -ne $actualCommand) {
        Write-VerificationField -Context $Context -Name 'DISPLAY_COMMAND' -Value $DisplayCommand
    }

    $resolvedCommand = Microsoft.PowerShell.Core\Get-Command `
        -Name $Command `
        -CommandType Application `
        -ErrorAction SilentlyContinue |
        Microsoft.PowerShell.Utility\Select-Object -First 1

    if ($null -eq $resolvedCommand) {
        Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record 'EXIT_CODE=UNAVAILABLE'
        throw ("native executable was not found: {0}" -f $Command)
    }

    if ($resolvedCommand -isnot [System.Management.Automation.ApplicationInfo]) {
        Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record 'EXIT_CODE=UNAVAILABLE'
        throw ("native command did not resolve to an application: {0}" -f $Command)
    }

    $resolvedPath = $resolvedCommand.Source
    if ([string]::IsNullOrWhiteSpace($resolvedPath) -or -not [System.IO.Path]::IsPathRooted($resolvedPath)) {
        Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record 'EXIT_CODE=UNAVAILABLE'
        throw ("native executable resolved without a usable path: {0}" -f $Command)
    }

    Write-VerificationField -Context $Context -Name 'COMMAND_RESOLVED' -Value $resolvedPath

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $global:LASTEXITCODE = $null
        $ErrorActionPreference = 'Continue'
        $output = & $resolvedPath @Arguments 2>&1
        $exitCode = $global:LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($item in $output) {
        Write-VerificationField -Context $Context -Name 'NATIVE_OUTPUT' -Value $item
    }

    if ($null -eq $exitCode) {
        Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record 'EXIT_CODE=UNAVAILABLE'
        throw ("native command did not produce an exit code: {0}" -f $actualCommand)
    }

    Write-VerificationInternalRecord -AttemptToken $state.AttemptToken -Record ("EXIT_CODE={0}" -f $exitCode)

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
    $exception.Data['VerificationOutcome'] = 'BLOCKED'
    throw $exception
}

function Get-VerificationLogOutcome {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    $lines = [System.IO.File]::ReadAllLines($LiteralPath)
    if ($lines.Count -eq 0) {
        throw 'verification log is empty'
    }

    $markers = @($lines | Microsoft.PowerShell.Core\Where-Object { $_ -match '^RESULT=(BLOCKED|FAIL|PASS)$' })
    if ($markers.Count -ne 1) {
        throw ("verification log must contain exactly one terminal RESULT record; found {0}" -f $markers.Count)
    }
    if ($lines[$lines.Count - 1] -ne $markers[0]) {
        throw 'verification terminal RESULT record must be the final log record'
    }

    return ($markers[0] -replace '^RESULT=', '')
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

    $ErrorActionPreference = 'Stop'

    if ([string]::IsNullOrWhiteSpace($LogRoot)) {
        if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
            throw 'TEMP is not available and LogRoot was not provided'
        }
        $LogRoot = Microsoft.PowerShell.Management\Join-Path $env:TEMP ("{0}-logs\{1}" -f $ProjectName, $Purpose)
    }

    Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $LogRoot | Microsoft.PowerShell.Core\Out-Null

    $stamp = Microsoft.PowerShell.Utility\Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $attemptId = "{0}-{1}-{2}" -f $stamp, $PID, $suffix
    $attemptToken = [Guid]::NewGuid().ToString('N')
    $logPath = Microsoft.PowerShell.Management\Join-Path $LogRoot ("attempt-{0}.log" -f $attemptId)

    $stream = [System.IO.FileStream]::new(
        $logPath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::Read
    )
    $encoding = [System.Text.UTF8Encoding]::new($true)
    $writer = [System.IO.StreamWriter]::new($stream, $encoding)
    $writer.AutoFlush = $true

    $script:AttemptStates[$attemptToken] = [pscustomobject]@{
        AttemptToken = $attemptToken
        LogPath = $logPath
        Stream = $stream
        Writer = $writer
    }

    $context = [pscustomobject]@{
        AttemptToken = $attemptToken
        ProjectName = $ProjectName
        Purpose = $Purpose
    }

    $outcome = 'FAIL'
    $bodyError = $null
    try {
        Write-VerificationInternalRecord -AttemptToken $attemptToken -Record 'FORMAT=interactive-verification-v1'
        Write-VerificationInternalRecord -AttemptToken $attemptToken -Record ("ATTEMPT_ID={0}" -f $attemptId)
        Write-VerificationInternalRecord -AttemptToken $attemptToken -Record ("PROJECT={0}" -f $ProjectName)
        Write-VerificationInternalRecord -AttemptToken $attemptToken -Record ("PURPOSE={0}" -f $Purpose)

        & $Body $context
        $outcome = 'PASS'
    }
    catch {
        $bodyError = $_
        $marker = $null
        $currentException = $bodyError.Exception
        while ($null -ne $currentException -and $null -eq $marker) {
            if ($currentException.Data.Contains('VerificationOutcome')) {
                $marker = [string]$currentException.Data['VerificationOutcome']
            }
            $currentException = $currentException.InnerException
        }
        if ($marker -eq 'BLOCKED') {
            $outcome = 'BLOCKED'
        }

        try {
            Write-VerificationField -Context $context -Name 'ERROR' -Value $bodyError.Exception.Message
        }
        catch {
            Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $_.Exception.Message)
        }
    }
    finally {
        $terminalLogError = $null
        try {
            Write-VerificationInternalRecord -AttemptToken $attemptToken -Record ("RESULT={0}" -f $outcome)
        }
        catch {
            $terminalLogError = $_
            Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $terminalLogError.Exception.Message)
        }
        finally {
            try { $writer.Dispose() } catch { }
            try { $stream.Dispose() } catch { }
            [void]$script:AttemptStates.Remove($attemptToken)
        }

        if ($null -eq $terminalLogError) {
            try {
                $verifiedOutcome = Get-VerificationLogOutcome -LiteralPath $logPath
                if ($verifiedOutcome -ne $outcome) {
                    throw ("verification terminal outcome mismatch: expected {0}, got {1}" -f $outcome, $verifiedOutcome)
                }
            }
            catch {
                $terminalLogError = $_
                Microsoft.PowerShell.Utility\Write-Host ("LOG_VERIFY_ERROR={0}" -f $terminalLogError.Exception.Message)
            }
        }

        Microsoft.PowerShell.Utility\Write-Host ("LOG={0}" -f $logPath)

        if ($null -ne $terminalLogError -and $outcome -eq 'PASS') {
            throw $terminalLogError
        }
    }

    if ($null -ne $bodyError) {
        throw $bodyError
    }
}

Export-ModuleMember -Function @(
    'Write-VerificationLog',
    'Write-VerificationField',
    'Invoke-VerificationNative',
    'Stop-VerificationBlocked',
    'Get-VerificationLogOutcome',
    'Invoke-VerificationAttempt'
)
