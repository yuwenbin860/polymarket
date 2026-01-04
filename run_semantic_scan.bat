@echo off
REM ============================================================
REM Polymarket 向量化语义扫描启动脚本
REM ============================================================
REM 自动设置UTF-8编码环境，避免中文/emoji显示问题

echo [启动] Polymarket 向量化语义扫描系统
echo.

REM 设置控制台为UTF-8编码
chcp 65001 >nul 2>&1

REM 设置Python使用UTF-8编码
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM 设置默认参数
set DOMAIN=crypto
set THRESHOLD=0.85

REM 解析命令行参数
:parse_args
if "%1"=="" goto run_scan
if "%1"=="--domain" (
    set DOMAIN=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--threshold" (
    set THRESHOLD=%2
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:run_scan
echo [配置] 领域: %DOMAIN%, 阈值: %THRESHOLD%
echo.

REM 运行扫描
.venv\Scripts\python.exe local_scanner_v2.py --semantic --domain %DOMAIN% --threshold %THRESHOLD%

echo.
echo [完成] 扫描已结束
pause
