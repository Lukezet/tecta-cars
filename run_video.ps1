param(
    [string]$Video = "C:\Users\NB138\Downloads\20260613_093125.mp4",
    [string]$Stream = "",
    [bool]$Display = $true,
    [int]$DisplayWidth = 800,
    [int]$DisplayHeight = 450,
    [int]$FrameStep = 5,
    [int]$VideoOcrInterval = 10,
    [int]$PlateSaveCooldown = 150,
    [double]$MinOcrConfidence = 0.65,
    [int]$VehicleSaveCooldown = 150,
    [double]$MinVehicleConfidence = 0.4
)

$ErrorActionPreference = "Stop"

$arguments = @(
    "detect_vehicles.py",
    "--display-width", $DisplayWidth,
    "--display-height", $DisplayHeight,
    "--frame-step", $FrameStep,
    "--video-ocr-interval", $VideoOcrInterval,
    "--plate-save-cooldown", $PlateSaveCooldown,
    "--min-ocr-confidence", $MinOcrConfidence,
    "--vehicle-save-cooldown", $VehicleSaveCooldown,
    "--min-vehicle-confidence", $MinVehicleConfidence
)

if ($Stream) {
    $arguments += @("--stream", $Stream)
} else {
    $arguments += @("--video", $Video)
}

if ($Display) {
    $arguments += "--display"
}

& ".\.venv\Scripts\python.exe" @arguments
