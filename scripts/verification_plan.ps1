function Get-VerificationLogOutcome {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    if (-not [System.IO.File]::Exists($LiteralPath)) {
        throw ("verification log does not exist: {0}" -f $LiteralPath)
    }

    $lines = [System.IO.File]::ReadAllLines($LiteralPath)
    if ($lines.Count -eq 0) {
        throw "verification log is empty"
    }

    $markers = @()
    foreach ($line in $lines) {
        if ($line -cmatch '^RESULT=(PASS|FAIL|BLOCKED)$') {
            $markers += $line
        }
    }

    if ($markers.Count -ne 1) {
        throw ("verification log must contain exactly one terminal RESULT record; found {0}" -f $markers.Count)
    }
    if ($lines[$lines.Count - 1] -cne $markers[0]) {
        throw "verification terminal RESULT record must be the final log record"
    }

    return ($markers[0] -creplace '^RESULT=', '')
}

function Invoke-VerificationPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlanPath,

        [string]$LogRoot
    )

    $ErrorActionPreference = "Stop"

    $fullPlanPath = [System.IO.Path]::GetFullPath($PlanPath)
    if (-not [System.IO.File]::Exists($fullPlanPath)) {
        throw ("verification plan does not exist: {0}" -f $fullPlanPath)
    }

    if ([string]::IsNullOrWhiteSpace($LogRoot)) {
        if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
            throw "TEMP is not available and LogRoot was not provided"
        }
        $LogRoot = [System.IO.Path]::Combine(
            $env:TEMP,
            "ai-dev-starter-logs",
            "verification-plan"
        )
    }

    $fullLogRoot = [System.IO.Path]::GetFullPath($LogRoot)
    [void][System.IO.Directory]::CreateDirectory($fullLogRoot)

    $stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff')
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $attemptId = "{0}-{1}-{2}" -f $stamp, $PID, $suffix
    $logPath = [System.IO.Path]::Combine($fullLogRoot, ("attempt-{0}.log" -f $attemptId))
    $utf8 = [System.Text.UTF8Encoding]::new($true)
    [System.IO.File]::WriteAllText($logPath, "", $utf8)

    $appendRaw = {
        param([string]$Record)

        if ($Record -match "[`r`n]") {
            throw "verification controller record must be one physical line"
        }

        [System.IO.File]::AppendAllText(
            $logPath,
            $Record + [Environment]::NewLine,
            $utf8
        )
        Microsoft.PowerShell.Utility\Write-Host $Record
    }

    $toJsonString = {
        param([AllowNull()][object]$Value)

        $text = if ($null -eq $Value) { "" } else { [string]$Value }
        return (Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $text -Compress)
    }

    $writeField = {
        param(
            [string]$Name,
            [AllowNull()][object]$Value
        )

        if ($Name -cnotmatch '^[A-Z0-9_]+$') {
            throw ("invalid verification field name: {0}" -f $Name)
        }
        if ($Name -ceq "RESULT") {
            throw "RESULT is controller-owned"
        }

        $encoded = & $toJsonString $Value
        & $appendRaw ("{0}={1}" -f $Name, $encoded)
    }

    $validateFields = {
        param(
            [object]$Object,
            [string[]]$Allowed,
            [string[]]$Required,
            [string]$Where
        )

        if ($null -eq $Object) {
            throw ("{0} must be an object" -f $Where)
        }

        $names = @($Object.PSObject.Properties.Name)
        foreach ($name in $names) {
            if ($Allowed -cnotcontains [string]$name) {
                throw ("unknown field '{0}' in {1}" -f $name, $Where)
            }
        }
        foreach ($requiredName in $Required) {
            if ($names -cnotcontains $requiredName) {
                throw ("missing required field '{0}' in {1}" -f $requiredName, $Where)
            }
        }
    }

    $newOutcomeException = {
        param(
            [string]$Message,
            [string]$Outcome
        )

        $exception = [System.InvalidOperationException]::new($Message)
        $exception.Data["VerificationOutcome"] = $Outcome
        return $exception
    }

    # The authoritative controller validates its own terminal evidence through a
    # local parser rather than through the public consumer command, which a caller
    # could deliberately replace in the surrounding session.
    $parseLogOutcome = {
        param([string]$LiteralPath)

        $lines = [System.IO.File]::ReadAllLines($LiteralPath)
        if ($lines.Count -eq 0) {
            throw "verification log is empty"
        }

        $markers = @()
        foreach ($line in $lines) {
            if ($line -cmatch '^RESULT=(PASS|FAIL|BLOCKED)$') {
                $markers += $line
            }
        }

        if ($markers.Count -ne 1) {
            throw ("verification log must contain exactly one terminal RESULT record; found {0}" -f $markers.Count)
        }
        if ($lines[$lines.Count - 1] -cne $markers[0]) {
            throw "verification terminal RESULT record must be the final log record"
        }

        return ($markers[0] -creplace '^RESULT=', '')
    }

    $reservedRecordNames = @(
        "FORMAT",
        "ATTEMPT_ID",
        "PLAN_PATH",
        "SCHEMA",
        "PROJECT",
        "PURPOSE",
        "STEP_ID",
        "STEP_TYPE",
        "COMMAND",
        "COMMAND_EXECUTABLE",
        "COMMAND_ARGUMENTS_JSON",
        "COMMAND_RESOLVED",
        "DISPLAY_COMMAND",
        "NATIVE_OUTPUT",
        "EXIT_CODE",
        "ERROR",
        "RESULT"
    )

    $outcome = "FAIL"
    $caughtError = $null
    $terminalError = $null

    try {
        & $appendRaw "FORMAT=interactive-verification-plan-v1"
        & $appendRaw ("ATTEMPT_ID={0}" -f $attemptId)
        & $writeField "PLAN_PATH" $fullPlanPath

        $json = [System.IO.File]::ReadAllText($fullPlanPath)
        $plan = Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject $json

        & $validateFields `
            $plan `
            @("schema", "project", "purpose", "steps") `
            @("schema", "project", "purpose", "steps") `
            "plan"

        if ($plan.schema -isnot [string] -or $plan.schema -cne "verification-plan-v1") {
            throw "plan schema must be exactly 'verification-plan-v1'"
        }
        if ($plan.project -isnot [string] -or $plan.project -notmatch '^[A-Za-z0-9._-]+$') {
            throw "plan project is missing or invalid"
        }
        if ($plan.purpose -isnot [string] -or $plan.purpose -notmatch '^[A-Za-z0-9._-]+$') {
            throw "plan purpose is missing or invalid"
        }
        if ($plan.steps -isnot [System.Array]) {
            throw "plan steps must be a JSON array"
        }

        $steps = @($plan.steps)
        if ($steps.Count -eq 0) {
            throw "verification plan must contain at least one step"
        }

        & $writeField "SCHEMA" $plan.schema
        & $writeField "PROJECT" $plan.project
        & $writeField "PURPOSE" $plan.purpose

        # Validate the complete plan before running the first executable step.
        # This includes semantic checks that would otherwise fail only during a
        # later cast or launch, after an earlier Native step had already mutated state.
        $stepKinds = @{}
        for ($index = 0; $index -lt $steps.Count; $index++) {
            $step = $steps[$index]
            $where = "step[{0}]" -f $index

            if ($null -eq $step) {
                throw ("{0} must be an object" -f $where)
            }

            $baseNames = @($step.PSObject.Properties.Name)
            if ($baseNames -cnotcontains "id" -or $baseNames -cnotcontains "type") {
                throw ("{0} must contain id and type" -f $where)
            }
            if ($step.id -isnot [string] -or $step.id -notmatch '^[A-Za-z0-9._-]+$') {
                throw ("invalid step id in {0}" -f $where)
            }
            if ($stepKinds.ContainsKey($step.id)) {
                throw ("duplicate step id: {0}" -f $step.id)
            }
            if ($step.type -isnot [string]) {
                throw ("step type must be a string in {0}" -f $where)
            }

            switch -CaseSensitive ($step.type) {
                "Native" {
                    & $validateFields `
                        $step `
                        @("id", "type", "command", "arguments", "accepted_exit_codes", "failure_outcome") `
                        @("id", "type", "command", "arguments", "accepted_exit_codes", "failure_outcome") `
                        $where

                    if ($step.command -isnot [string] -or $step.command -notmatch '^[A-Za-z0-9._-]+$') {
                        throw ("Native command must be a simple application name in {0}" -f $where)
                    }
                    if ($step.arguments -isnot [System.Array]) {
                        throw ("Native arguments must be a JSON array in {0}" -f $where)
                    }
                    foreach ($argument in $step.arguments) {
                        if ($argument -isnot [string]) {
                            throw ("Native arguments must all be strings in {0}" -f $where)
                        }
                    }
                    if ($step.accepted_exit_codes -isnot [System.Array]) {
                        throw ("Native accepted_exit_codes must be a JSON array in {0}" -f $where)
                    }
                    $acceptedCodes = @($step.accepted_exit_codes)
                    if ($acceptedCodes.Count -eq 0) {
                        throw ("Native accepted_exit_codes must not be empty in {0}" -f $where)
                    }
                    foreach ($code in $acceptedCodes) {
                        if ($code -isnot [int] -and $code -isnot [long]) {
                            throw ("Native accepted_exit_codes must contain integers in {0}" -f $where)
                        }
                        $code64 = [long]$code
                        if ($code64 -lt [int]::MinValue -or $code64 -gt [int]::MaxValue) {
                            throw ("Native accepted_exit_codes must fit Int32 in {0}" -f $where)
                        }
                    }
                    if ($step.failure_outcome -cnotin @("FAIL", "BLOCKED")) {
                        throw ("Native failure_outcome must be FAIL or BLOCKED in {0}" -f $where)
                    }
                }
                "AssertOutputEmpty" {
                    & $validateFields `
                        $step `
                        @("id", "type", "step", "failure_outcome") `
                        @("id", "type", "step", "failure_outcome") `
                        $where

                    if ($step.step -isnot [string] -or [string]::IsNullOrWhiteSpace($step.step)) {
                        throw ("AssertOutputEmpty step reference must be a string in {0}" -f $where)
                    }
                    if ($step.failure_outcome -cnotin @("FAIL", "BLOCKED")) {
                        throw ("AssertOutputEmpty failure_outcome must be FAIL or BLOCKED in {0}" -f $where)
                    }
                    if (-not $stepKinds.ContainsKey($step.step)) {
                        throw ("AssertOutputEmpty must reference an earlier step: {0}" -f $step.step)
                    }
                    if ($stepKinds[$step.step] -cne "Native") {
                        throw ("AssertOutputEmpty may reference only a Native step: {0}" -f $step.step)
                    }
                }
                "Record" {
                    & $validateFields `
                        $step `
                        @("id", "type", "name", "value") `
                        @("id", "type", "name", "value") `
                        $where

                    if ($step.name -isnot [string] -or $step.name -cnotmatch '^[A-Z0-9_]+$') {
                        throw ("Record name is missing or invalid in {0}" -f $where)
                    }
                    if ($reservedRecordNames -ccontains $step.name) {
                        throw ("Record name is reserved: {0}" -f $step.name)
                    }
                    if ($step.value -isnot [string]) {
                        throw ("Record value must be a string in {0}" -f $where)
                    }
                }
                default {
                    throw ("unknown verification step type: {0}" -f $step.type)
                }
            }

            $stepKinds[$step.id] = $step.type
        }

        $results = @{}

        foreach ($step in $steps) {
            & $writeField "STEP_ID" $step.id
            & $writeField "STEP_TYPE" $step.type

            switch -CaseSensitive ($step.type) {
                "Native" {
                    $arguments = [string[]]@($step.arguments)
                    $acceptedExitCodes = [int[]]@($step.accepted_exit_codes)
                    $actualCommand = (@($step.command) + $arguments) -join " "
                    $argumentsJson = Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject @($arguments) -Compress

                    & $writeField "COMMAND" $actualCommand
                    & $writeField "COMMAND_EXECUTABLE" $step.command
                    & $appendRaw ("COMMAND_ARGUMENTS_JSON={0}" -f $argumentsJson)

                    $resolvedCommands = @(
                        Microsoft.PowerShell.Core\Get-Command `
                            -Name $step.command `
                            -CommandType Application `
                            -ErrorAction SilentlyContinue
                    )
                    $resolvedCommand = if ($resolvedCommands.Count -gt 0) { $resolvedCommands[0] } else { $null }

                    if ($null -eq $resolvedCommand -or $resolvedCommand -isnot [System.Management.Automation.ApplicationInfo]) {
                        & $appendRaw "EXIT_CODE=UNAVAILABLE"
                        $exception = & $newOutcomeException `
                            ("native executable was not found: {0}" -f $step.command) `
                            $step.failure_outcome
                        throw $exception
                    }

                    $resolvedPath = $resolvedCommand.Source
                    if ([string]::IsNullOrWhiteSpace($resolvedPath) -or -not [System.IO.Path]::IsPathRooted($resolvedPath)) {
                        & $appendRaw "EXIT_CODE=UNAVAILABLE"
                        $exception = & $newOutcomeException `
                            ("native executable resolved without a usable path: {0}" -f $step.command) `
                            $step.failure_outcome
                        throw $exception
                    }

                    & $writeField "COMMAND_RESOLVED" $resolvedPath

                    $previousErrorActionPreference = $ErrorActionPreference
                    try {
                        $global:LASTEXITCODE = $null
                        $ErrorActionPreference = "Continue"
                        $output = & $resolvedPath @arguments 2>&1
                        $exitCode = $global:LASTEXITCODE
                    }
                    finally {
                        $ErrorActionPreference = $previousErrorActionPreference
                    }

                    foreach ($item in @($output)) {
                        & $writeField "NATIVE_OUTPUT" $item
                    }

                    if ($null -eq $exitCode) {
                        & $appendRaw "EXIT_CODE=UNAVAILABLE"
                        $exception = & $newOutcomeException `
                            ("native command did not produce an exit code: {0}" -f $actualCommand) `
                            $step.failure_outcome
                        throw $exception
                    }

                    & $appendRaw ("EXIT_CODE={0}" -f $exitCode)

                    if ($acceptedExitCodes -notcontains [int]$exitCode) {
                        $exception = & $newOutcomeException `
                            ("native command failed with exit code {0}: {1}" -f $exitCode, $actualCommand) `
                            $step.failure_outcome
                        throw $exception
                    }

                    $results[$step.id] = [pscustomobject]@{
                        ExitCode = [int]$exitCode
                        Output = @($output)
                    }
                }
                "AssertOutputEmpty" {
                    $referenced = $results[$step.step]
                    if ($null -eq $referenced) {
                        throw ("missing runtime result for referenced step: {0}" -f $step.step)
                    }
                    if (@($referenced.Output).Count -ne 0) {
                        $exception = & $newOutcomeException `
                            ("expected no output from step '{0}'" -f $step.step) `
                            $step.failure_outcome
                        throw $exception
                    }
                }
                "Record" {
                    & $writeField $step.name $step.value
                }
            }
        }

        $outcome = "PASS"
    }
    catch {
        $caughtError = $_
        $marker = $null
        $currentException = $caughtError.Exception
        while ($null -ne $currentException -and $null -eq $marker) {
            if ($currentException.Data.Contains("VerificationOutcome")) {
                $marker = [string]$currentException.Data["VerificationOutcome"]
            }
            $currentException = $currentException.InnerException
        }

        if ($marker -ceq "BLOCKED") {
            $outcome = "BLOCKED"
        }

        try {
            & $writeField "ERROR" $caughtError.Exception.Message
        }
        catch {
            Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $_.Exception.Message)
        }
    }

    try {
        & $appendRaw ("RESULT={0}" -f $outcome)
    }
    catch {
        $terminalError = $_
        Microsoft.PowerShell.Utility\Write-Host ("LOG_WRITE_ERROR={0}" -f $terminalError.Exception.Message)
    }

    if ($null -eq $terminalError) {
        try {
            $verifiedOutcome = & $parseLogOutcome $logPath
            if ($verifiedOutcome -cne $outcome) {
                throw ("verification terminal outcome mismatch: expected {0}, got {1}" -f $outcome, $verifiedOutcome)
            }
        }
        catch {
            $terminalError = $_
            Microsoft.PowerShell.Utility\Write-Host ("LOG_VERIFY_ERROR={0}" -f $terminalError.Exception.Message)
        }
    }

    Microsoft.PowerShell.Utility\Write-Host ("LOG={0}" -f $logPath)

    if ($null -ne $caughtError) {
        throw $caughtError
    }
    if ($null -ne $terminalError) {
        throw $terminalError
    }
}
