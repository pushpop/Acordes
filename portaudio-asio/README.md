# ASIO-Enabled PortAudio DLL

Place `libportaudio64bit.dll` (ASIO build) in this folder to enable ASIO backend
support in Acordes. The launcher (`run.ps1`) will copy it automatically into the
virtual environment after every `uv sync`, so it survives venv recreations.

## Why this is needed

The standard `sounddevice` pip package ships with a PortAudio DLL compiled
**without** ASIO support. ASIO drivers (Steinberg, ASIO4ALL, etc.) register at
`HKEY_LOCAL_MACHINE\SOFTWARE\ASIO` on Windows, but PortAudio only discovers them
when its ASIO host API is compiled in. This DLL replaces the bundled one.

## How to get the DLL

1. Go to: https://github.com/spatialaudio/portaudio-binaries
2. Download `libportaudio64bit-asio.dll`
3. Rename it to `libportaudio64bit.dll`
4. Place it in this folder (`portaudio-asio/libportaudio64bit.dll`)
5. Run `run.ps1` — it will install it automatically

## What the launcher does

After `uv sync`, `run.ps1` checks for `portaudio-asio\libportaudio64bit.dll`.
If found, it copies it to:

    .venv\Lib\site-packages\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll

The original DLL is backed up as `libportaudio64bit.dll.bak` on first replacement
so you can restore it if needed.

## After installation

Open Acordes, press `C` for config, and `ASIO` will appear in the Audio Backend
list alongside WASAPI and DirectSound. Select it, then pick your ASIO device.

## Platform note

ASIO is Windows-only. This folder is ignored on Linux and macOS.
