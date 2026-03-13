@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "PYTHON_DIR=%ROOT_DIR%\wipe_engine_service"
set "BACKEND_DIR=%ROOT_DIR%\cipherforge-spring-backend"
set "FRONTEND_DIR=%ROOT_DIR%\cipherforge-dashboard"
if not defined BACKEND_PORT set "BACKEND_PORT=8081"
if not defined FRONTEND_PORT set "FRONTEND_PORT=4300"

echo ================================================
echo CipherForge System Startup
echo Root: %ROOT_DIR%
echo ================================================

call :start_postgres
call :start_python_engine
call :start_backend
call :start_frontend

echo.
echo ================================================
echo Startup sequence completed.
echo Python Engine : http://localhost:8000
echo Spring Backend: http://localhost:%BACKEND_PORT%
echo Angular UI    : http://localhost:%FRONTEND_PORT%
echo ================================================
exit /b 0

:start_postgres
echo.
echo [1/4] Checking PostgreSQL (port 5432)...
call :is_port_open 5432
if /I "!OPEN!"=="true" (
  echo PostgreSQL already running.
  exit /b 0
)

echo PostgreSQL not detected. Trying to start service...
set "PG_STARTED=false"
for %%S in (
  "postgresql-x64-17"
  "postgresql-x64-16"
  "postgresql-x64-15"
  "postgresql-x64-14"
  "postgresql-x64-13"
  "postgresql"
  "PostgreSQL"
) do (
  sc query %%~S >nul 2>&1
  if !errorlevel! EQU 0 (
    echo Trying service %%~S ...
    net start %%~S >nul 2>&1
    if !errorlevel! EQU 0 set "PG_STARTED=true"
  )
)

call :wait_for_port 5432 20
if !errorlevel! EQU 0 (
  echo PostgreSQL is running.
) else (
  echo WARNING: PostgreSQL is still not reachable on port 5432.
  echo          Start PostgreSQL manually if your setup uses a different service.
)
exit /b 0

:start_python_engine
echo.
echo [2/4] Checking Python wipe engine (port 8000)...
call :is_port_open 8000
if /I "!OPEN!"=="true" (
  echo Python wipe engine already running.
  exit /b 0
)

if not exist "%PYTHON_DIR%\main.py" (
  echo ERROR: Python engine script not found at "%PYTHON_DIR%\main.py"
  exit /b 1
)

echo Starting Python wipe engine...
start "CipherForge Python Engine" cmd /k "cd /d ""%ROOT_DIR%"" && python -m wipe_engine_service.main"
call :wait_for_port 8000 25
if !errorlevel! EQU 0 (
  echo Python wipe engine started.
) else (
  echo WARNING: Python wipe engine did not open port 8000 in time.
)
exit /b 0

:start_backend
echo.
echo [3/4] Checking Spring backend (port %BACKEND_PORT%)...
call :is_port_open %BACKEND_PORT%
if /I "!OPEN!"=="true" (
  echo Spring backend already running on port %BACKEND_PORT%.
  exit /b 0
)

if not exist "%BACKEND_DIR%\pom.xml" (
  echo ERROR: Backend pom.xml not found at "%BACKEND_DIR%\pom.xml"
  exit /b 1
)

echo Starting Spring backend...
start "CipherForge Spring Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=%BACKEND_PORT%"
call :wait_for_port %BACKEND_PORT% 60
if !errorlevel! EQU 0 (
  echo Spring backend started on port %BACKEND_PORT%.
) else (
  echo WARNING: Spring backend did not open port %BACKEND_PORT% in time.
)
exit /b 0

:start_frontend
echo.
echo [4/4] Checking Angular frontend (port %FRONTEND_PORT%)...
call :is_port_open %FRONTEND_PORT%
if /I "!OPEN!"=="true" (
  echo Angular frontend already running on port %FRONTEND_PORT%.
  exit /b 0
)

if not exist "%FRONTEND_DIR%\angular.json" (
  echo ERROR: Frontend angular.json not found at "%FRONTEND_DIR%\angular.json"
  exit /b 1
)

echo Starting Angular frontend...
start "CipherForge Angular Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && ng serve --port %FRONTEND_PORT%"
call :wait_for_port %FRONTEND_PORT% 60
if !errorlevel! EQU 0 (
  echo Angular frontend started on port %FRONTEND_PORT%.
) else (
  echo WARNING: Angular frontend did not open port %FRONTEND_PORT% in time.
)
exit /b 0

:is_port_open
set "OPEN=false"
for /f "tokens=1" %%A in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING" 2^>nul') do (
  set "OPEN=true"
  goto :eof
)
exit /b 0

:wait_for_port
set /a WAIT_SECONDS=0
:wait_loop
call :is_port_open %~1
if /I "!OPEN!"=="true" exit /b 0
if !WAIT_SECONDS! GEQ %~2 exit /b 1
set /a WAIT_SECONDS+=1
timeout /t 1 /nobreak >nul
goto :wait_loop
