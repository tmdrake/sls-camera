# SLS Camera App (Ghost Hunting SLS Explorer)

## Overview
Modern SDK-style .NET 8 WPF application for modified Xbox 360 Kinect SLS camera. Features depth-first view with skeleton overlay, spectrum analyser below main screen, Ovilus random word generator (15-30min), un-mirrored camera, and optimized MVVM code.

## Dev-Phase Install Instructions
**Prerequisites**:
- Windows 10/11 (64-bit recommended).
- Microsoft Kinect SDK v1.8 installed (required for hardware).
- .NET 8 SDK and Visual Studio 2022+ (with .NET desktop workload) or `dotnet` CLI.

**Build**:
```cmd
cd software\source\example
dotnet restore
dotnet build -c Release
```

**Run**:
```cmd
cd software\source\example\bin\Release\net8.0-windows
slscam.exe
```

Defaults to Depth feed with skeleton on top. Spectrum analyser below main viewer. Ovilus triggers randomly (15-30 min). Future installer (Inno Setup or MSIX) will be added.

## Features
- Real-time Depth-first view with skeleton overlay (Color on side, swap supported).
- Spectrum analyser below main screen (real-time audio visualization).
- **Ovilus Word Generator**: Auto random 15-30min triggers (no button). Note: external triggers (depth/skeleton/audio anomalies) to be added later.
- Camera un-mirrored for standing behind hardware.
- Dark paranormal UI theme, optimized MVVM code, no audio panel.
- Sensor management, tilt control.

## Next Steps
- Full spectrum analyser implementation with FFT.
- External Ovilus triggers.
- Installer (Inno Setup/MSIX).
- Further optimizations and testing with real hardware.

## Next Steps
- Tie Ovilus triggers to depth/skeleton changes for context-aware "spirit communication".
- Add session recording and anomaly highlighting on depth view.
- Modernize to .NET 8 WPF (optional).

## Hardware
Requires attached Xbox 360 Kinect (SLS structured light camera).

Report issues at https://github.com/anomalyco/opencode/issues
