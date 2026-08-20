# CloudCompare + plugins on WSL2 / Ubuntu 24.04 - local setup

How CloudCompare, the CSF filter, the Python runtime and TreeAIBox were built
and wired on this machine, 2026-08-19. **Nothing here needed root** - there is
no passwordless sudo on this box, so everything installs user-local.

TreeAIBox upstream ships a Windows `.exe` installer only; this is the Linux
equivalent.

## What was installed

| Piece | Location |
| --- | --- |
| TreeAIBox clone | `/home/sites/organizations/slu/courses/TreeAIBox` |
| Python env | `./.venv` (system CPython 3.12.3, `--system-site-packages`) |
| PythonRuntime plugin source | `/home/sites/CloudCompare/plugins/private/CloudCompare-PythonRuntime` |
| Built plugins (`.so`) | `~/.local/share/CCCorp/CloudCompare/plugins/` |
| Qt6 WebEngine (extracted debs) | `~/.local/opt/qt6we/root` |
| Launcher | `~/.local/bin/cloudcompare` |
| Runtime settings | `~/.config/CCCorp/CloudCompare:PythonRuntime.Settings.conf` |

CloudCompare scans `~/.local/share/CCCorp/CloudCompare/plugins` at startup, so
plugins go there instead of `/opt` - no sudo, and they survive a `/opt` reinstall.

## Two patches / workarounds worth remembering

1. **`ccColorScale` API drift.** PythonRuntime master calls
   `ccColorScale::isReadOnly()` / `setReadOnly()`; CloudCompare v2.13.1-372
   (this tree) still names them `isLocked()` / `setLocked()`. Patched in
   `wrapper/pycc/src/qcc_db/ccColorScale.cpp` - Python-facing names unchanged.
   Re-apply if PythonRuntime is ever re-cloned.

2. **PyQt6 must come from Ubuntu's Qt, not from pip.** CloudCompare loads the
   system Qt 6.4.2. Pip's PyQt6 bundles its own Qt (6.11), and the two cannot
   coexist in one process. Going the other way - putting the wheel's Qt first -
   breaks CloudCompare itself, which needs Ubuntu's `qt_resourceFeatureZstd`.
   So the Ubuntu `python3-pyqt6*` debs are extracted (not installed) under
   `~/.local/opt/qt6we` and symlinked into the venv's `site-packages`.
   Do not `pip install PyQt6` into this venv.

## Rebuilding the plugins

    cd /home/sites/CloudCompare/build-qt6-qpcl
    cmake -DPLUGIN_STANDARD_QCSF=ON -DPLUGIN_PYTHON=ON \
      -DPython_EXECUTABLE=/home/sites/organizations/slu/courses/TreeAIBox/.venv/bin/python \
      -Dpybind11_DIR=/home/sites/organizations/slu/courses/TreeAIBox/.venv/lib/python3.12/site-packages/pybind11/share/cmake/pybind11 .
    ninja -j6
    cp plugins/private/CloudCompare-PythonRuntime/libPythonRuntime.so \
       plugins/core/Standard/qCSF/libQCSF_PLUGIN.so \
       ~/.local/share/CCCorp/CloudCompare/plugins/

## Running

    cloudcompare        # ~/.local/bin wrapper sets every path needed

TreeAIBox is pre-registered as a script: **Plugins > Python > (script list) > TreeAIBox**.

## Known limitation: no GPU

`nvidia-smi` is absent, so torch is `2.5.1+cpu`. Every bundled model config is
labelled `(GPU3GB)`..`(GPU12GB)`. Inference runs on CPU but will be slow, and
the larger models may be impractical.

## Pinned versions

| Component | Version / commit |
| --- | --- |
| CloudCompare | `v2.13.1-372-g0d385434` |
| CloudCompare-PythonRuntime | `3532659` (+ the patch above) |
| TreeAIBox | `5380dde` |
| Qt (system, what CloudCompare loads) | 6.4.2 |
| PyQt6 / PyQt6-WebEngine | 6.6.1 / 6.6.0, from extracted Ubuntu debs |
| torch | 2.5.1+cpu |
| PCL | 1.15 at `/opt/pcl-qt6` |

## Restoring this setup

The launcher, the runtime settings and the PythonRuntime patch are all kept in
this repo:

    setup/bin/cloudcompare      -> ~/.local/bin/cloudcompare
    setup/bin/ccviewer          -> ~/.local/bin/ccviewer
    setup/config/CloudCompare_PythonRuntime.Settings.conf
                                -> ~/.config/CCCorp/'CloudCompare:PythonRuntime.Settings.conf'
    setup/patches/ccColorScale-isLocked.patch
                                -> git apply, in the PythonRuntime clone

Note the settings file's real name contains a colon (`CloudCompare:PythonRuntime.Settings.conf`)
because Qt derives it from the application name; it is stored here without the
colon for portability.
