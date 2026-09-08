<#
mantener_despierto.ps1
Impide que Windows suspenda el equipo MIENTRAS se está preparando un vídeo
(ComfyUI generando, o un job del Montaje en marcha). Cuando no hay nada
generándose desde hace unos minutos, suelta el bloqueo y el PC puede volver a
suspenderse con normalidad.

No toca la configuración de energía del usuario: usa la API SetThreadExecutionState
(lo mismo que hace un reproductor de vídeo para que no se apague la pantalla).

Uso:
    powershell -ExecutionPolicy Bypass -File scripts\mantener_despierto.ps1

Déjalo abierto en una ventana (o lánzalo junto a ComfyUI). Ctrl+C para salir:
al salir suelta el bloqueo.
#>
param(
    [string]$ComfyUrl   = "http://127.0.0.1:8188",
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [int]$IntervaloSeg  = 30,
    [int]$GraciaSeg     = 300   # sigue despierto este tiempo tras la última actividad
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Power {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$ES_CONTINUOUS       = [uint32]"0x80000000"
$ES_SYSTEM_REQUIRED  = [uint32]"0x00000001"

$bloqueado   = $false
$ultActividad = (Get-Date).AddYears(-1)

function Test-Generando {
    # ¿ComfyUI tiene algo en cola o ejecutándose?
    try {
        $q = Invoke-RestMethod -Uri "$ComfyUrl/queue" -TimeoutSec 8 -ErrorAction Stop
        if ($q.queue_running.Count -gt 0 -or $q.queue_pending.Count -gt 0) { return $true }
    } catch {}
    # ¿algún job del Montaje en marcha? (cubre transcripción/voz/ensamblado)
    try {
        $a = Invoke-RestMethod -Uri "$BackendUrl/api/music-clip/activo" -TimeoutSec 8 -ErrorAction Stop
        if ($a.activo) { return $true }
    } catch {}
    return $false
}

Write-Host "[mantener-despierto] vigilando ComfyUI + Montaje. El PC no se suspenderá mientras se genere. Ctrl+C para salir." -ForegroundColor Cyan

try {
    while ($true) {
        if (Test-Generando) { $ultActividad = Get-Date }
        $activo = ((Get-Date) - $ultActividad).TotalSeconds -lt $GraciaSeg

        if ($activo -and -not $bloqueado) {
            [void][Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
            $bloqueado = $true
            Write-Host ("[{0}] generando -> suspensión BLOQUEADA" -f (Get-Date -Format HH:mm:ss)) -ForegroundColor Yellow
        }
        elseif (-not $activo -and $bloqueado) {
            [void][Power]::SetThreadExecutionState($ES_CONTINUOUS)
            $bloqueado = $false
            Write-Host ("[{0}] inactivo -> suspensión PERMITIDA de nuevo" -f (Get-Date -Format HH:mm:ss)) -ForegroundColor Green
        }
        # refresca el flag periódicamente (algunos equipos lo "olvidan")
        if ($bloqueado) { [void][Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) }

        Start-Sleep -Seconds $IntervaloSeg
    }
}
finally {
    [void][Power]::SetThreadExecutionState($ES_CONTINUOUS)
    Write-Host "[mantener-despierto] bloqueo liberado, saliendo." -ForegroundColor Cyan
}
