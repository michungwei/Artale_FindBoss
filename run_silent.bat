@echo off
REM 無視窗啟動自動遊戲監控系統
if not exist "config.json" (
    REM 首次執行需要安裝套件，顯示安裝進度
    start "" /wait cmd /c "title 安裝套件 & echo 正在安裝必要套件，請稍候... & py -m pip install -r requirements.txt & echo 安裝完成！ & timeout /t 2 >nul"
)

REM 背景啟動程式（完全無視窗）
start "" /B py game_monitor.py

REM 立即退出批次檔
exit