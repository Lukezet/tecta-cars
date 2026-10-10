param(
    [string]$HostAddress = "192.168.1.41",
    [Parameter(Mandatory = $true)]
    [string]$CameraUsername,
    [ValidateSet("stream1", "stream2")]
    [string]$Stream = "stream2",
    [int]$FrameStep = 5,
    [int]$VideoOcrInterval = 10,
    [int]$PlateSaveCooldown = 150,
    [double]$MinOcrConfidence = 0.65,
    [int]$VehicleSaveCooldown = 150,
    [double]$MinVehicleConfidence = 0.4,
    [int]$MaxFrames = 0
)

$ErrorActionPreference = "Stop"

$arguments = @(
    "detect_vehicles.py",
    "--tapo-host", $HostAddress,
    "--tapo-port", 554,
    "--tapo-stream", $Stream,
    "--tapo-username", $CameraUsername,
    "--display",
    "--no-save-video",
    "--display-width", 800,
    "--display-height", 450,
    "--frame-step", $FrameStep,
    "--video-ocr-interval", $VideoOcrInterval,
    "--plate-save-cooldown", $PlateSaveCooldown,
    "--min-ocr-confidence", $MinOcrConfidence,
    "--vehicle-save-cooldown", $VehicleSaveCooldown,
    "--min-vehicle-confidence", $MinVehicleConfidence
)

if ($MaxFrames -gt 0) {
    $arguments += @("--max-frames", $MaxFrames)
}

& ".\.venv\Scripts\python.exe" @arguments
