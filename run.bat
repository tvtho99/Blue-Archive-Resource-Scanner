@echo off
rem Blue Archive Resource Scanner: installs what it needs on the first run,
rem then shows a menu. Double-click it, or run "run.bat" from a terminal.
setlocal
cd /d "%~dp0"
title Blue Archive Resource Scanner
set "PY=.venv\Scripts\python.exe"
set "empty=0"

if not exist "%PY%" (
    call :setup || goto :setup_failed
) else (
    rem A venv from an older install may lack packages added since
    "%PY%" -c "import importlib.util as u, sys; sys.exit(any(u.find_spec(m) is None for m in ('pynput', 'rapidocr', 'cv2', 'windows_capture')))" >nul 2>nul
    if errorlevel 1 (
        call :setup || goto :setup_failed
    )
)

:menu
cls
echo ==================================================================
echo   Blue Archive Resource Scanner
echo ==================================================================
echo.
echo   Before a scan, in the game:
echo     - Game text: English
echo     - Screen Ratio 16:9, game area at least 1280x720
echo       (window or fullscreen, any bigger size works)
echo     - Display Shortcut Icons: OFF, no controller connected
echo     - Steam overlay notifications off, start on the lobby
echo.
echo   [1] Scan            automatic, moves your mouse (F2 stops it)
echo   [2] Read-only scan  you go through the game, nothing is clicked
echo   [3] Settings        platform (PC client / emulator), scan targets
echo   [4] Check layout    screenshots with the scan regions drawn on them
echo   [5] Export          Justin163 Planner
echo   [6] Export          Schale DB
echo   [7] Export          Midokuni roster URL
echo   [8] Update data     download the latest community item/student data
echo   [0] Exit
echo.
set "pick="
set /p "pick=Choose 0-8: "
rem Input closed (Ctrl+Z, or a pipe that ended): leave instead of looping
if defined pick (set "empty=0") else (set /a "empty+=1")
if %empty% geq 20 goto :end
if "%pick%"=="1" goto :scan
if "%pick%"=="2" goto :readonly
if "%pick%"=="3" goto :settings
if "%pick%"=="4" goto :layout
if "%pick%"=="5" goto :justin
if "%pick%"=="6" goto :schaledb
if "%pick%"=="7" goto :midokuni
if "%pick%"=="8" goto :sync
if "%pick%"=="0" goto :end
goto :menu

:scan
echo.
echo   Automatic scan
echo   - It moves your real mouse: don't touch the mouse until it is done.
echo   - Stop: press F2. Screens already finished are still saved.
echo     Emergency stop: push the mouse into a screen corner.
echo   - First run: a setup wizard asks how you run the game
echo     (pick "PC client" for the Steam version).
echo   - Warning: the PC client ships an anti-cheat and the game's terms
echo     forbid macros. Use [2] if you don't want automatic clicks.
echo   - If Windows asks "Terminate batch job (Y/N)?", answer N.
echo.
call :confirm "Start the scan" || goto :menu
"%PY%" launch.py
goto :done

:readonly
call :need_settings || goto :back
echo.
echo   Read-only scan: nothing is clicked, you go through the game yourself.
echo   - Lobby: AP, Credits and Pyroxene are read when it shows.
echo   - Equipment / Items: click the items one by one and scroll yourself.
echo     Keep each item on screen about 1 second, this window counts them.
echo   - Students: open a student and press the next arrow, about 1 s each.
echo   - Done: press F2, or Ctrl+C in this window. Everything seen is saved.
echo   Items and students you don't look at keep their earlier values.
echo.
call :confirm "Start watching" || goto :menu
"%PY%" -m tools.manual_scan
goto :done

:settings
echo.
echo   Opening the settings window. Pick "PC client" for the Steam version,
echo   choose what to scan, then Save Settings.
"%PY%" -m gui.run
if errorlevel 1 (
    echo.
    echo   The settings window could not open. Use the text wizard instead:
    echo   "%PY%" launch.py -e   ^(it starts a scan when you finish^)
)
goto :done

:layout
call :need_settings || goto :back
echo.
echo   Check layout: nothing is clicked.
echo   Open a screen in the game, then type its name here:
echo     home, menu, equipment, items, students, student   (q to quit)
echo   The pictures go to output\layout\: the boxes must sit on the text.
echo.
"%PY%" -m tools.capture_layout
goto :done

:justin
if not exist "input" mkdir "input"
echo.
echo   Justin163 Planner export
echo   - To keep your planner data, export it from justin163.com/planner
echo     and save it as input\justin_data.json first.
echo   - Result: output\justin_data_final.json, import it into the planner.
echo   Options: -m  target MAX for new characters, -o  update data first
echo.
set "opts="
set /p "opts=Options (Enter for none): "
"%PY%" -m tools.justin_planner %opts%
goto :done

:schaledb
echo.
echo   Schale DB export
echo   - Importing REPLACES your whole Schale DB collection. To keep the
echo     students the scan missed, use "Export Collection" on schaledb.com,
echo     save the text to a file and give its path below
echo     (you can drag the file into this window).
echo   - Result: output\SchaleDB_import.txt
echo.
set "base="
set /p "base=Your Schale DB export file (Enter to skip): "
set "opts="
set /p "opts=Options: -l lock everyone, -o update data first (Enter for none): "
if defined base (
    "%PY%" -m tools.schaledb --file "%base:"=%" %opts%
) else (
    "%PY%" -m tools.schaledb %opts%
)
goto :done

:midokuni
echo.
echo   Midokuni roster URL export: prints a link that opens your roster.
echo   Options: -s blue  or  -s black  sets every student's state,
echo            -o  update data first
echo.
set "opts="
set /p "opts=Options (Enter for none): "
"%PY%" -m tools.midokuni %opts%
goto :done

:sync
echo.
echo   Downloading the latest item and student data (BA-Scanner-Data)...
"%PY%" -m tools.sync_data
goto :done

:done
echo.
if errorlevel 1 (echo   Ended with exit code %errorlevel%, see the messages above.) else (echo   Done.)
:back
echo.
pause
goto :menu

:confirm
set "yn="
set /p "yn=%~1? [Y/n]: "
if /i "%yn%"=="n" exit /b 1
exit /b 0

:need_settings
if exist "config\settings.json" exit /b 0
echo.
echo   No settings yet: choose [3] Settings first
echo   (or [1] Scan, which asks on its first run).
exit /b 1

:setup
echo Installing the scanner's Python packages, this takes a few minutes...
where uv >nul 2>nul
if not errorlevel 1 (
    uv sync
    exit /b
)
python -c "import sys; sys.exit(sys.version_info < (3, 13))" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python 3.13 or newer is needed. Install it from
    echo https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
    echo or install uv: https://docs.astral.sh/uv/
    exit /b 1
)
if not exist "%PY%" python -m venv .venv || exit /b 1
"%PY%" -m pip install -r requirements.txt
exit /b

:setup_failed
echo.
echo Setup failed, see the messages above.
pause
exit /b 1

:end
endlocal
exit /b 0
