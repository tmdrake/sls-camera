# CODE-ANALYSIS.md

## Overview

This document captures the current first-pass software analysis of the SLS camera code that was added under `software/source/example/`.

## Current codebase identity

The software currently appears to be a:
- **C# WPF desktop application**
- targeting **.NET Framework 4.0**
- built around the **Microsoft Kinect SDK 1.x** era
- likely derived from or heavily based on an older Microsoft Kinect sample application

## Current location

The example software has been reorganized into:

```text
software/source/example/
```

This is preferred over keeping it at the repo root because it clearly identifies the code as part of the software portion of the project.

## Key files observed

### Solution and project
- `software/source/example/SLS Explorer.sln`
- `software/source/example/SLS Explorer-WPF.csproj`

### Main application UI
- `software/source/example/MainWindow.xaml`
- `software/source/example/MainWindow.xaml.cs`

### Per-device visualization window
- `software/source/example/KinectWindow.xaml`
- `software/source/example/KinectWindow.xaml.cs`

### Sensor model/state classes
- `software/source/example/KinectSensorItem.cs`
- `software/source/example/KinectSensorItemCollection.cs`
- `software/source/example/KinectStatusItem.cs`

### App bootstrap
- `software/source/example/app.xaml`
- `software/source/example/app.xaml.cs`

### Utility
- `software/source/example/VisibilityConverter.cs`

## Functional understanding

At a high level, this software appears to:
- enumerate Kinect sensors
- monitor Kinect connection/status changes
- display status for available sensors
- open a dedicated window for a connected sensor
- support visual display of Kinect data
- allow swapping views in the visual interface

This looks like a Kinect viewer/explorer foundation, not yet a fully unique or modernized SLS application.

## Build environment assumptions

The project file indicates:
- **Target Framework:** .NET Framework 4.0
- **Project style:** old-style Visual Studio / MSBuild project
- **Likely IDE era:** Visual Studio 2010 or nearby

It also references:

```xml
<Reference Include="Microsoft.Kinect">
  <HintPath>$(KINECTSDK10_DIR)\Assemblies\Microsoft.Kinect.dll</HintPath>
</Reference>
```

This means the code expects:
- the old Kinect SDK to be installed
- a Windows build environment
- `KINECTSDK10_DIR` to be available

## Known missing dependency

The solution references an additional project:

```text
..\KinectWpfViewers\Microsoft.Samples.Kinect.WpfViewers.csproj
```

That dependency is currently **missing from the repo**.

### Immediate consequence
The software is not currently self-contained and is likely **not build-ready** without this dependency.

## Cleanup already performed

The following cleanup has already been done:
- moved `example/` into `software/source/example/`
- removed the tracked `.suo` Visual Studio user file
- updated `.gitignore` to ignore:
  - `*.suo`
  - `.vs/`
  - `bin/`
  - `obj/`

## Current assessment

### Strengths
- readable code
- clear WPF project structure
- understandable event-driven logic
- good enough foundation for further analysis

### Weaknesses / blockers
- missing referenced project (`KinectWpfViewers`)
- legacy SDK dependency
- old framework/tooling assumptions
- unclear how much of the current project is original versus inherited sample code

## Archive recovery targets

When searching the archive, the most useful finds would be:

### Highest priority
- `KinectWpfViewers` project or folder
- any original build notes
- any notes about the exact Kinect SDK version used
- any notes describing what was changed from the original Microsoft sample

### Medium priority
- screenshots of the app in use
- old release/build outputs
- notes on how the Xbox 360 camera mod relates to the Windows software
- protocol or processing notes for the SLS-specific behavior

### Hardware/software bridge items
- camera modification notes
- interface assumptions between the hardware and the software
- any custom add-on concept docs

## Recommended next steps

1. Recover or locate the missing `KinectWpfViewers` dependency
2. Add any build notes or original documentation to the repo
3. Clarify the intended software direction:
   - build legacy app as-is
   - understand it for preservation
   - modernize it
   - adapt it to future custom hardware
4. Once dependencies are found, perform a build-feasibility review

## Working conclusion

The current software looks like a legacy Kinect-based WPF viewer/explorer that can likely be revived, but it is not yet complete enough to build or fully analyze in isolation.
