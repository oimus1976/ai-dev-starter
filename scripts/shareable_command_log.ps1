function Invoke-ShareableCommandLog {
    [CmdletBinding(DefaultParameterSetName = 'ScriptBlock')]
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9._-]+$')]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9._-]+$')]
        [string]$WorkItem,

        [Parameter(Mandatory = $true, ParameterSetName = 'ScriptBlock')]
        [scriptblock]$ScriptBlock,

        [Parameter(Mandatory = $true, ParameterSetName = 'Native')]
        [string]$Command,

        [Parameter(ParameterSetName = 'Native')]
        [string[]]$Arguments = @()
    )

    if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
        throw 'TEMP is not available'
    }

    $logRoot = [System.IO.Path]::Combine(
        $env:TEMP,
        'ai-dev-starter',
        $WorkItem
    )
    [void][System.IO.Directory]::CreateDirectory($logRoot)

    $stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff')
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $logPath = [System.IO.Path]::Combine(
        $logRoot,
        ('{0}-{1}-{2}-{3}.log' -f $Name, $stamp, $PID, $suffix)
    )

    $utf8 = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($logPath, '', $utf8)

    $writeLine = {
        param([AllowNull()][object]$Value)

        $text = if ($null -eq $Value) { '' } else { [string]$Value }
        Microsoft.PowerShell.Utility\Write-Host $text
        [System.IO.File]::AppendAllText(
            $logPath,
            $text + [Environment]::NewLine,
            $utf8
        )
    }

    $exitCode = $null
    $previousConsoleEncoding = [Console]::OutputEncoding

    try {
        # Keep redirected terminal output readable to callers such as Python test
        # harnesses and browser-assisted workflows on Windows PowerShell 5.1.
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

        if ($PSCmdlet.ParameterSetName -eq 'ScriptBlock') {
            $output = & $ScriptBlock 2>&1
            foreach ($item in $output) {
                & $writeLine $item
            }
        }
        else {
            $resolvedCommand = Microsoft.PowerShell.Core\Get-Command `
                -Name $Command `
                -CommandType Application `
                -ErrorAction SilentlyContinue |
                Microsoft.PowerShell.Utility\Select-Object -First 1

            if ($null -eq $resolvedCommand) {
                throw ("native executable was not found: {0}" -f $Command)
            }

            $resolvedPath = $resolvedCommand.Source
            if (
                [string]::IsNullOrWhiteSpace($resolvedPath) -or
                -not [System.IO.Path]::IsPathRooted($resolvedPath)
            ) {
                throw ("native executable resolved without a usable path: {0}" -f $Command)
            }

            $previousErrorActionPreference = $ErrorActionPreference
            try {
                # Windows PowerShell 5.1 may surface redirected native stderr as
                # ErrorRecord objects. The native process exit code remains the
                # command result; stderr is still useful shareable output.
                $global:LASTEXITCODE = $null
                $ErrorActionPreference = 'Continue'
                $output = & $resolvedPath @Arguments 2>&1
                $exitCode = $global:LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }

            foreach ($item in $output) {
                & $writeLine $item
            }

            if ($null -eq $exitCode) {
                throw ("native command did not produce an exit code: {0}" -f $Command)
            }

            & $writeLine ("EXIT_CODE={0}" -f $exitCode)
        }
    }
    finally {
        [Console]::OutputEncoding = $previousConsoleEncoding
        Microsoft.PowerShell.Utility\Write-Host ("LOG={0}" -f $logPath)
    }

    [pscustomobject]@{
        LogPath = $logPath
        ExitCode = $exitCode
    }
}
