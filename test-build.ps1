Write-Output "=== SLS Cam Test Script ==="
Write-Output "Killing any running slscam.exe..."
Stop-Process -Name slscam -Force -ErrorAction SilentlyContinue
Write-Output "Build started at $(Get-Date)"
cd "C:\Work\sls-camera\software\source\example"
& "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe" "SLS Explorer.sln" /p:Configuration=Debug /verbosity:minimal /p:TargetFrameworkVersion=v4.8
Write-Output "Build completed at $(Get-Date). Waiting 15 seconds..."
Start-Sleep -Seconds 15
Write-Output "Launching slscam.exe for test..."
$p = Start-Process "bin\Debug\slscam.exe" -PassThru -ErrorAction SilentlyContinue
Start-Sleep -Seconds 8
if ($p -and !$p.HasExited) {
  Write-Output "SUCCESS: App started (PID $($p.Id)). Killing test instance."
  Stop-Process -Id $p.Id -Force
} else {
  Write-Output "FAILED: App did not start or exited immediately. Check error.log for details."
}
Get-Content "bin\Debug\error.log" -ErrorAction SilentlyContinue | Select-Object -First 10
Write-Output "Test complete at $(Get-Date). Ready for next build."
