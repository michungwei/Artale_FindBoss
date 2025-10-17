@echo off
title 自動遊戲監控與通知系統
echo ==========================================
echo       自動遊戲監控與通知系統
echo ==========================================
echo.
echo 正在啟動程式...
echo.

REM 檢查 Python 是否安裝
py --version >nul 2>&1
if errorlevel 1 (
    echo 錯誤：未找到 Python！
    echo 請先安裝 Python 3.8 或以上版本
    echo 下載網址：https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 檢查是否為首次執行
if not exist "config.json" (
    echo 檢測到首次執行，正在安裝必要套件...
    py -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 套件安裝失敗！請檢查網路連線
        pause
        exit /b 1
    )
    echo 套件安裝完成！
    echo.
)

REM 執行程式
echo 啟動監控系統...
echo.
echo 程式啟動成功！GUI視窗已開啟
echo 您可以安全地關閉此命令提示字元視窗
echo.
start /B py game_monitor.py

REM 等待程式啟動
timeout /t 3 /nobreak >nul

echo 監控系統已在背景運行
echo 請查看桌面上的程式視窗
echo.
echo 按任意鍵關閉此視窗...
pause >nul