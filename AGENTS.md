# SLS Camera App (Ghost Hunting SLS Explorer)

## Overview
Modernized legacy Kinect Xbox 360 SLS camera application with Ovilus-style word generator for paranormal investigation use.

## Build and Run
1. Ensure Microsoft Kinect SDK v1.8 is installed (hardware must be connected).
2. Open `software\source\example\SLS Explorer.sln` in Visual Studio or run from command line:
   ```
   cd software\source\example
   "%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe" "SLS Explorer.sln" /p:Configuration=Debug
   ```
3. Run `software\source\example\bin\Debug\KinectExplorer-WPF.exe`

## Features
- Real-time Color, Depth, and Skeleton viewing from modified Xbox 360 Kinect.
- **Ovilus Word Generator**: Auto-generates ghost-hunting words every 8 seconds or on button press. Displays large text + history log. Integrated into right sidebar.
- Dark paranormal UI theme.
- Sensor management, tilt control, stream swapping.

## Next Steps
- Tie Ovilus triggers to depth/skeleton changes for context-aware "spirit communication".
- Add session recording and anomaly highlighting on depth view.
- Modernize to .NET 8 WPF (optional).

## Hardware
Requires attached Xbox 360 Kinect (SLS structured light camera).

Report issues at https://github.com/anomalyco/opencode/issues
