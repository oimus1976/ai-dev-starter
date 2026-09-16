$modulePath = Microsoft.PowerShell.Management\Join-Path $PSScriptRoot 'interactive_verification.psm1'

# Keep the existing dot-source entrypoint for callers, but load the implementation
# as a module so only the explicitly exported caller surface enters the session.
Microsoft.PowerShell.Core\Import-Module $modulePath -Force -Global
