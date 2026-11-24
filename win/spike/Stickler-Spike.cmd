@echo off
rem Stickler spike launcher (SPEC.md, module win-spike). Drop a song on this file, or give
rem its path; the log is %LOCALAPPDATA%\Stickler\spike-log.txt. Nothing is sent anywhere.
setlocal EnableExtensions
set "HERE=%~dp0"
set "STICKLER_PACKAGED=windows"
set "PYTHONUTF8=1"
set "PATH=%HERE%bin;%PATH%"
if not defined STICKLER_SPIKE_LOG set "STICKLER_SPIKE_LOG=%LOCALAPPDATA%\Stickler\spike-log.txt"
if not defined STICKLER_SPIKE_OUT set "STICKLER_SPIKE_OUT=%LOCALAPPDATA%\Stickler\spike-out"
set "SONG=%~1"
if not defined SONG set /p "SONG=Path of the song (or drop it on this window and press Enter): "
if not defined SONG (
  echo No song given.
  set "RC=2"
  goto :done
)
set "SONG=%SONG:"=%"
echo Stickler spike: analysing "%SONG%"
echo Log: %STICKLER_SPIKE_LOG%
"%HERE%python\python.exe" "%HERE%spike_driver.py" --song "%SONG%" --out "%STICKLER_SPIKE_OUT%" --log "%STICKLER_SPIKE_LOG%"
set "RC=%ERRORLEVEL%"
:done
echo.
if "%RC%"=="0" (echo Finished: see the MusicXML in %STICKLER_SPIKE_OUT%) else (echo FAILED with exit code %RC%: send %STICKLER_SPIKE_LOG% back.)
if not defined STICKLER_SPIKE_NO_PAUSE pause
exit /b %RC%
