# install_windows.ps1
# Instalacion de reel-news-bot en Windows con Docker Desktop.
# Ejecutar desde la carpeta del pendrive donde esta este script.
#
# Clic derecho sobre el archivo -> "Ejecutar con PowerShell"
# (o desde PowerShell: .\install_windows.ps1)

$ErrorActionPreference = "Stop"

# ── Funciones de color ─────────────────────────────────────────────────────────
function OK    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function WARN  { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function ERROR { param($msg) Write-Host "  [X]  $msg" -ForegroundColor Red }
function TITLE { param($msg) Write-Host "`n$msg" -ForegroundColor Cyan }

# ── Cabecera ───────────────────────────────────────────────────────────────────
Clear-Host
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Instalacion reel-news-bot en Windows     " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Docker Desktop ──────────────────────────────────────────────────────────
TITLE "1. Verificando Docker Desktop..."

try { $v = docker --version; OK $v }
catch {
    ERROR "Docker Desktop no encontrado."
    Write-Host ""
    Write-Host "  Descargalo en: https://www.docker.com/products/docker-desktop/" -ForegroundColor White
    Write-Host "  Instalalo, arrancalo y vuelve a ejecutar este script." -ForegroundColor White
    Read-Host "`nPulsa Enter para salir"
    exit 1
}

try { docker info 2>&1 | Out-Null; OK "Docker esta en marcha" }
catch {
    ERROR "Docker Desktop no esta corriendo. Abrelo y espera a que el icono de la barra de tareas sea estable."
    Read-Host "`nPulsa Enter para salir"
    exit 1
}

# ── 2. Carpeta de instalacion ──────────────────────────────────────────────────
TITLE "2. Carpeta de instalacion"

$defaultPath = "C:\Dev\reel-news-bot"
Write-Host "  Donde instalar el proyecto? (Enter = $defaultPath)" -ForegroundColor White
$installPath = Read-Host "  Ruta"
if ([string]::IsNullOrWhiteSpace($installPath)) { $installPath = $defaultPath }
$installPath = $installPath.TrimEnd('\')

# ── 3. Localizar el backup .tar.gz ─────────────────────────────────────────────
TITLE "3. Localizando backup..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backupFile = Get-ChildItem -Path $scriptDir -Filter "reel-news-bot_backup_*.tar.gz" `
              | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $backupFile) {
    ERROR "No se encontro ningun reel-news-bot_backup_*.tar.gz en la misma carpeta que este script."
    Write-Host "  Asegurate de ejecutar install_windows.ps1 desde la carpeta del pendrive." -ForegroundColor Yellow
    Read-Host "`nPulsa Enter para salir"
    exit 1
}
OK "Backup: $($backupFile.Name)"

# ── 4. Extraer el proyecto ─────────────────────────────────────────────────────
TITLE "4. Extrayendo proyecto en $installPath ..."

$parentDir = Split-Path -Parent $installPath
if (-not (Test-Path $parentDir)) {
    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
}

# tar esta disponible en Windows 10 1803+ y Windows 11
Push-Location $parentDir
try {
    tar -xzf "$($backupFile.FullName)"
} catch {
    ERROR "Error al extraer el backup. Asegurate de tener Windows 10 1803+ o Windows 11."
    Pop-Location; Read-Host "`nPulsa Enter para salir"; exit 1
}
Pop-Location

# Si el directorio extraido se llama "reel-news-bot" y el destino tiene otro nombre, renombrar
$extractedDir = Join-Path $parentDir "reel-news-bot"
if ((Test-Path $extractedDir) -and ($extractedDir -ne $installPath)) {
    if (Test-Path $installPath) { Remove-Item -Recurse -Force $installPath }
    Rename-Item -Path $extractedDir -NewName (Split-Path -Leaf $installPath)
}

if (-not (Test-Path $installPath)) {
    ERROR "No se encontro el proyecto en $installPath tras extraer."
    Read-Host "`nPulsa Enter para salir"; exit 1
}
OK "Proyecto extraido en $installPath"

# ── 5. Copiar credenciales y datos desde el pendrive ──────────────────────────
TITLE "5. Copiando credenciales y datos desde el pendrive..."

$copies = @(
    @{ src = ".env";     dst = ".env";     label = ".env (API keys)" }
    @{ src = "_tokens";  dst = "_tokens";  label = "_tokens (YouTube / Telegram / WhatsApp)" }
    @{ src = "_config";  dst = "_config";  label = "_config (configuracion de la app)" }
    @{ src = "_music";   dst = "_music";   label = "_music (canciones del Montaje)" }
    @{ src = "_library"; dst = "_library"; label = "_library (biblioteca de imagenes)" }
)

foreach ($c in $copies) {
    $src = Join-Path $scriptDir $c.src
    $dst = Join-Path $installPath $c.dst
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        OK "$($c.label)"
    } else {
        WARN "$($c.label) — no encontrado en el pendrive, se omite"
    }
}

# ── 6. Crear carpetas que no vienen en el backup ───────────────────────────────
TITLE "6. Creando carpetas de datos..."

foreach ($dir in @("output", "_templates", "_uploads")) {
    $dirPath = Join-Path $installPath $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
        OK "Carpeta $dir creada"
    }
}

# ── 7. Arrancar con Docker Compose ────────────────────────────────────────────
TITLE "7. Construyendo e iniciando contenedores..."
Write-Host "  (La primera vez tarda 5-15 minutos descargando imagenes y compilando)" -ForegroundColor White
Write-Host ""

Set-Location $installPath

# Usar el override de Windows para eliminar el extra_hosts de Linux
$composeArgs = @(
    "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.windows.yml",
    "up", "-d", "--build"
)

& docker @composeArgs

if ($LASTEXITCODE -ne 0) {
    ERROR "Docker Compose devolvio un error (codigo $LASTEXITCODE)."
    Write-Host "  Revisa los logs: docker compose logs backend" -ForegroundColor Yellow
    Read-Host "`nPulsa Enter para salir"; exit 1
}

# ── 8. Resultado final ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   Instalacion completada correctamente!    " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Interfaz web:   http://localhost:3000" -ForegroundColor White
Write-Host "  API backend:    http://localhost:8000" -ForegroundColor White
Write-Host "  WhatsApp QR:    http://localhost:3002" -ForegroundColor White
Write-Host ""
Write-Host "Proximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Abre http://localhost:3000 en el navegador" -ForegroundColor White
Write-Host "  2. Si YouTube/Instagram piden reconectar -> ve a /canales" -ForegroundColor White
Write-Host "  3. Para WhatsApp -> abre http://localhost:3002 y escanea el QR" -ForegroundColor White
Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor Cyan
Write-Host "  Ver logs:    docker compose logs -f backend" -ForegroundColor Gray
Write-Host "  Detener:     docker compose down" -ForegroundColor Gray
Write-Host "  Reiniciar:   docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d" -ForegroundColor Gray
Write-Host ""
Read-Host "Pulsa Enter para cerrar"
