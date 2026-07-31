<#
.SYNOPSIS
  Free a TCP port by killing whatever owns it, including orphaned children.

.DESCRIPTION
  Dot-source this and call `Clear-Port -Port 8000`.

  It exists because of a specific failure that cost time twice in one build. Both
  `uvicorn --reload` and `vite` run a supervisor that spawns the real server as a child.
  Killing the supervisor by remembered PID leaves the child alive and still holding the
  socket, so the next start silently fails to bind while the *old* code keeps answering
  requests. Phase 5 shipped three routes that returned 404 from a stale server while
  pytest stayed green, and separately left three dead Vite listeners across 5173-5180.

  So: resolve owners from the port itself rather than from a PID anyone remembered, kill
  the whole descendant tree, and then *confirm* the port is free instead of assuming it.
#>

function Get-ProcessDescendants {
    param([Parameter(Mandatory)][int[]]$ParentIds)

    # Index children by parent once. Re-scanning the process table per generation is what
    # makes the naive version quadratic on a busy machine.
    $byParent = @{}
    foreach ($p in Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId) {
        $key = [int]$p.ParentProcessId
        if (-not $byParent.ContainsKey($key)) {
            $byParent[$key] = [System.Collections.Generic.List[int]]::new()
        }
        $byParent[$key].Add([int]$p.ProcessId)
    }

    # Breadth-first with an explicit read index. Do NOT re-slice the queue with
    # `$queue[1..($queue.Count-1)]` — when Count is 1 that expression is `$queue[1,0]`,
    # which yields $null plus the element back again, and the loop never terminates.
    $queue = [System.Collections.Generic.List[int]]::new()
    $ParentIds | ForEach-Object { $queue.Add($_) }
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $found = [System.Collections.Generic.List[int]]::new()

    for ($i = 0; $i -lt $queue.Count; $i++) {
        $current = $queue[$i]
        if (-not $seen.Add($current)) { continue }   # PID reuse could otherwise cycle
        if (-not $byParent.ContainsKey($current)) { continue }
        foreach ($child in $byParent[$current]) {
            if ($child -eq $current) { continue }
            $found.Add($child)
            $queue.Add($child)
        }
    }

    $found
}

function Clear-Port {
    param(
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutSeconds = 5
    )

    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)

    if (-not $owners) {
        Write-Host "Port $Port is free."
        return
    }

    $victims = @($owners) + @(Get-ProcessDescendants -ParentIds $owners) | Sort-Object -Unique
    Write-Host "Port $Port held by PID(s) $($owners -join ', '); stopping $($victims.Count) process(es)."
    foreach ($id in $victims) {
        try { Stop-Process -Id $id -Force -Confirm:$false -ErrorAction Stop } catch {}
    }

    # A dead process can hold the socket briefly. Confirm rather than assume — assuming is
    # exactly what produced the stale server in the first place.
    $deadline = $TimeoutSeconds * 10
    while ($deadline-- -gt 0 -and
           (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 100
    }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is still held after ${TimeoutSeconds}s. Check for a process outside this session."
    }
}
