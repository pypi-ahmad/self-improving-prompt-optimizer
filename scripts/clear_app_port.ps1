param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$Port
)

$ErrorActionPreference = 'Stop'

try {
    $listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq $Port)
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($ownerId in $owners) {
        if ($ownerId -le 4 -or $ownerId -eq $PID) {
            throw "Port $Port belongs to a protected process ($ownerId)."
        }
        # Recheck ownership before stopping a process that might already have exited.
        $stillListening = @(Get-NetTCPConnection -State Listen |
            Where-Object { $_.LocalPort -eq $Port -and $_.OwningProcess -eq $ownerId })
        if ($stillListening.Count -gt 0) {
            Write-Host "Stopping process $ownerId on port $Port..."
            Stop-Process -Id $ownerId -Force
        }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $remaining = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq $Port)
        if ($remaining.Count -eq 0) {
            exit 0
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port $Port is still occupied."
} catch {
    Write-Error "Could not clear port ${Port}: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
