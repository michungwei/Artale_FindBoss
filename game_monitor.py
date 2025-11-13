#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動遊戲監控與通知系統
功能：監控畫面特定區域，檢測王怪並透過Telegram發送通知
"""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog
import json
import time
import threading
from datetime import datetime
import pyautogui
# 設定PyAutoGUI參數避免fail-safe問題
pyautogui.FAILSAFE = False  # 禁用fail-safe（謹慎使用）
pyautogui.PAUSE = 0.5  # 每次操作間隔0.5秒
import requests
from PIL import Image, ImageTk
import cv2
import numpy as np
import keyboard
import mss
import urllib.parse
import os
import json

class TelegramBot:
    """Telegram Bot指令處理器"""
    
    def __init__(self, game_monitor):
        self.game_monitor = game_monitor
        self.bot_token = game_monitor.config.get("telegram_bot_token", "")
        self.chat_id = game_monitor.config.get("telegram_chat_id", "")
        self.update_offset = 0
        self.is_listening = False
        self.listener_thread = None
        
        # 指令處理映射
        self.commands = {
            '/menu': self.handle_menu,
            '/status': self.handle_status,
            '/pause': self.handle_pause,
            '/resume': self.handle_resume,
            '/stop': self.handle_stop,
            '/screenshot': self.handle_screenshot
        }
    
    def start_listener(self):
        """啟動Telegram指令監聽"""
        if not self.bot_token or not self.chat_id:
            print("❌ Telegram Bot Token或Chat ID未設定，跳過Bot功能")
            return False
        
        self.is_listening = True
        self.listener_thread = threading.Thread(target=self.listen_for_commands, daemon=True)
        self.listener_thread.start()
        
        # 設定Bot指令選單（固定在聊天欄）
        self.set_bot_commands()
        
        # 發送歡迎訊息
        if self.game_monitor.config.get("send_welcome_message", True):
            self.send_welcome_message()
        
        print("✅ Telegram Bot監聽已啟動")
        return True
    
    def stop_listener(self):
        """停止Telegram指令監聽"""
        self.is_listening = False
        if self.listener_thread:
            self.listener_thread.join(timeout=1)
    
    def listen_for_commands(self):
        """監聽Telegram指令（輪詢方式）"""
        while self.is_listening:
            try:
                # 每3秒檢查一次新訊息
                self.check_for_updates()
                time.sleep(3)
            except Exception as e:
                print(f"❌ Telegram監聽錯誤: {e}")
                time.sleep(5)  # 錯誤時等待長一點
    
    def check_for_updates(self):
        """檢查Telegram更新"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                "offset": self.update_offset + 1,
                "timeout": 2,
                "allowed_updates": ["message", "callback_query"]
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data["ok"] and data["result"]:
                    for update in data["result"]:
                        self.process_update(update)
                        self.update_offset = update["update_id"]
        except Exception as e:
            print(f"❌ 檢查Telegram更新失敗: {e}")
    
    def process_update(self, update):
        """處理Telegram更新"""
        try:
            if "message" in update:
                message = update["message"]
                chat_id = str(message["chat"]["id"])
                
                # 只處理來自設定聊天室的訊息
                if chat_id == self.chat_id:
                    text = message.get("text", "")
                    if text.startswith("/"):
                        command = text.split()[0].lower()
                        self.process_command(command, message)
            
            elif "callback_query" in update:
                # 處理按鈕點擊事件
                callback_query = update["callback_query"]
                chat_id = str(callback_query["message"]["chat"]["id"])
                
                # 只處理來自設定聊天室的按鈕點擊
                if chat_id == self.chat_id:
                    self.handle_callback_query(callback_query)
                    
        except Exception as e:
            print(f"❌ 處理Telegram訊息失敗: {e}")
    
    def process_command(self, command, message):
        """處理Telegram指令"""
        try:
            if command in self.commands:
                response = self.commands[command](message)
            else:
                response = self.handle_invalid_command()
            
            if response:
                self.send_message(response)
                
        except Exception as e:
            error_msg = f"❌ 指令執行失敗: {str(e)}\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            self.send_message(error_msg)
            print(f"❌ 處理指令 {command} 失敗: {e}")
    
    def get_timestamp(self):
        """取得格式化的時間戳"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def set_bot_commands(self):
        """設定Bot指令清單（固定在聊天欄）"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
            commands = [
                {"command": "menu", "description": "📋 顯示操作選單"},
                {"command": "status", "description": "📊 查看程式狀態"},
                {"command": "pause", "description": "⏸️ 暫停程式"},
                {"command": "resume", "description": "▶️ 恢復運行"},
                {"command": "stop", "description": "⏹️ 停止程式"},
                {"command": "screenshot", "description": "📸 螢幕截圖"}
            ]
            
            data = {
                'commands': json.dumps(commands)
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                print("✅ Bot指令選單設定成功")
                return True
            else:
                print(f"❌ Bot指令選單設定失敗: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 設定Bot指令選單失敗: {e}")
            return False
    
    def create_inline_keyboard(self):
        """創建內聯鍵盤按鈕"""
        keyboard = [
            [
                {"text": "📊 查看狀態", "callback_data": "status"},
                {"text": "📸 螢幕截圖", "callback_data": "screenshot"}
            ],
            [
                {"text": "⏸️ 暫停程式", "callback_data": "pause"},
                {"text": "▶️ 恢復運行", "callback_data": "resume"}
            ],
            [
                {"text": "⏹️ 停止程式", "callback_data": "stop"},
                {"text": "📋 顯示選單", "callback_data": "menu"}
            ]
        ]
        return {"inline_keyboard": keyboard}
    
    def handle_callback_query(self, callback_query):
        """處理按鈕點擊回調"""
        try:
            callback_data = callback_query["data"]
            query_id = callback_query["id"]
            message_id = callback_query["message"]["message_id"]
            
            # 先回應callback_query（避免loading狀態）
            self.answer_callback_query(query_id, "處理中...")
            
            # 根據按鈕數據處理相應功能
            if callback_data == "status":
                response = self.handle_status_callback()
            elif callback_data == "screenshot":
                response = self.handle_screenshot_callback()
            elif callback_data == "pause":
                response = self.handle_pause_callback()
            elif callback_data == "resume":
                response = self.handle_resume_callback()
            elif callback_data == "stop":
                response = self.handle_stop_callback()
            elif callback_data == "menu":
                response = self.handle_menu_callback()
            else:
                response = "❓ 未知的按鈕操作"
            
            # 更新原訊息內容
            if response:
                self.edit_message(message_id, response, self.create_inline_keyboard())
                
        except Exception as e:
            print(f"❌ 處理按鈕點擊失敗: {e}")
            try:
                self.answer_callback_query(query_id, f"操作失敗: {str(e)}")
            except:
                pass
    
    def send_welcome_message(self):
        """發送歡迎訊息"""
        message = f"""🚀 Artale找Boss神器已啟動
時間：{self.get_timestamp()}

💡 兩種操作方式：
🔹 點擊下方按鈕直接操作
🔹 點擊聊天欄 "/" 選擇指令"""
        self.send_message_with_keyboard(message, self.create_inline_keyboard())
    
    def handle_menu(self, message):
        """處理 /menu 指令"""
        menu_text = f"""🤖 Artale找Boss神器 - 指令清單

📊 /status - 查看目前狀態和運行時間
⏸️ /pause - 暫停程式
▶️ /resume - 恢復程式運行  
⏹️ /stop - 停止程式
📸 /screenshot - 發送目前畫面截圖
📋 /menu - 顯示此指令清單

💡 三種操作方式：
🔹 點擊下方按鈕直接操作
🔹 點擊聊天欄 "/" 選擇指令
🔹 直接輸入指令文字

時間：{self.get_timestamp()}"""
        
        # 發送帶按鈕的選單
        self.send_message_with_keyboard(menu_text, self.create_inline_keyboard())
        return None  # 不需要額外回應
    
    def handle_status(self, message):
        """處理 /status 指令"""
        try:
            current_stage = self.game_monitor.current_stage or "未知狀態"
            
            # 計算狀態持續時間
            if hasattr(self.game_monitor, 'current_stage_start_time'):
                elapsed = time.time() - self.game_monitor.current_stage_start_time
                duration = self.format_duration(elapsed)
            else:
                duration = "未知"
            
            # 取得運行狀態
            if self.game_monitor.is_running:
                if self.game_monitor.is_paused:
                    status_icon = "⏸️ 已暫停"
                else:
                    status_icon = "▶️ 運行中"
            else:
                status_icon = "⏹️ 已停止"
            
            status_text = f"""📊 程式狀態報告

{status_icon}
目前階段：{current_stage}
持續時間：{duration}
時間：{self.get_timestamp()}"""
            
            return status_text
            
        except Exception as e:
            return f"❌ 取得狀態失敗: {str(e)}\n時間：{self.get_timestamp()}"
    
    def handle_pause(self, message):
        """處理 /pause 指令"""
        try:
            if not self.game_monitor.is_running:
                return f"⚠️ 程式尚未啟動，無法暫停\n時間：{self.get_timestamp()}"
            
            if self.game_monitor.is_paused:
                return f"⚠️ 程式已經是暫停狀態\n時間：{self.get_timestamp()}"
            
            # 執行暫停
            self.game_monitor.is_paused = True
            self.game_monitor.pause_continue_btn.config(text="繼續")
            
            return f"✅ 程式已暫停\n時間：{self.get_timestamp()}"
            
        except Exception as e:
            return f"❌ 暫停失敗: {str(e)}\n時間：{self.get_timestamp()}"
    
    def handle_resume(self, message):
        """處理 /resume 指令"""
        try:
            if not self.game_monitor.is_running:
                return f"⚠️ 程式尚未啟動，請先啟動程式\n時間：{self.get_timestamp()}"
            
            if not self.game_monitor.is_paused:
                return f"⚠️ 程式已經在運行中\n時間：{self.get_timestamp()}"
            
            # 執行恢復
            self.game_monitor.is_paused = False
            self.game_monitor.pause_continue_btn.config(text="暫停")
            
            return f"✅ 程式已恢復運行\n時間：{self.get_timestamp()}"
            
        except Exception as e:
            return f"❌ 恢復失敗: {str(e)}\n時間：{self.get_timestamp()}"
    
    def handle_stop(self, message):
        """處理 /stop 指令"""
        try:
            if not self.game_monitor.is_running:
                return f"⚠️ 程式已經是停止狀態\n時間：{self.get_timestamp()}"
            
            # 執行停止
            self.game_monitor.is_running = False
            self.game_monitor.is_paused = False
            self.game_monitor.start_stop_btn.config(text="開始")
            self.game_monitor.pause_continue_btn.config(text="暫停", state="disabled")
            
            return f"✅ 程式已停止\n時間：{self.get_timestamp()}"
            
        except Exception as e:
            return f"❌ 停止失敗: {str(e)}\n時間：{self.get_timestamp()}"
    
    def handle_screenshot(self, message):
        """處理 /screenshot 指令"""
        try:
            # 擷取全螢幕截圖
            screenshot = pyautogui.screenshot()
            
            # 儲存為臨時檔案
            temp_file = f"tmp_rovodev_screenshot_{int(time.time())}.png"
            screenshot.save(temp_file)
            
            # 發送截圖
            success = self.send_photo(temp_file, f"📸 螢幕截圖\n時間：{self.get_timestamp()}")
            
            # 刪除臨時檔案
            try:
                os.remove(temp_file)
            except:
                pass
            
            if success:
                return None  # 圖片已發送，不需要額外文字回應
            else:
                return f"❌ 截圖發送失敗\n時間：{self.get_timestamp()}"
                
        except Exception as e:
            return f"❌ 截圖失敗: {str(e)}\n時間：{self.get_timestamp()}"
    
    def handle_invalid_command(self):
        """處理無效指令"""
        return f"❓ 無效指令，請使用 /menu 查看可用指令\n時間：{self.get_timestamp()}"
    
    # 按鈕回調處理方法
    def handle_status_callback(self):
        """處理狀態查詢按鈕"""
        return self.handle_status(None)
    
    def handle_screenshot_callback(self):
        """處理截圖按鈕"""
        self.handle_screenshot(None)
        return f"📸 螢幕截圖已發送\n時間：{self.get_timestamp()}"
    
    def handle_pause_callback(self):
        """處理暫停按鈕"""
        return self.handle_pause(None)
    
    def handle_resume_callback(self):
        """處理恢復按鈕"""
        return self.handle_resume(None)
    
    def handle_stop_callback(self):
        """處理停止按鈕"""
        return self.handle_stop(None)
    
    def handle_menu_callback(self):
        """處理選單按鈕"""
        return f"""🤖 Artale找Boss神器 - 指令清單

📊 查看狀態 - 顯示程式當前運行狀態
📸 螢幕截圖 - 發送目前完整畫面截圖  
⏸️ 暫停程式 - 暫停自動化流程
▶️ 恢復運行 - 恢復暫停的流程
⏹️ 停止程式 - 完全停止程式運行
📋 顯示選單 - 顯示此說明

💡 點擊上方按鈕即可操作
時間：{self.get_timestamp()}"""
    
    def format_duration(self, seconds):
        """格式化持續時間"""
        if seconds <= 60:
            return f"{int(seconds)}秒"
        else:
            minutes = int(seconds // 60)
            remaining_seconds = int(seconds % 60)
            if remaining_seconds > 0:
                return f"{minutes}分{remaining_seconds}秒"
            else:
                return f"{minutes}分鐘"
    
    def send_message(self, text):
        """發送Telegram訊息"""
        return self.game_monitor.send_telegram_message(self.chat_id, text)
    
    def send_message_with_keyboard(self, text, keyboard):
        """發送帶按鈕的Telegram訊息"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'reply_markup': json.dumps(keyboard)
            }
            
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ 發送帶按鈕的Telegram訊息失敗: {e}")
            return False
    
    def edit_message(self, message_id, text, keyboard):
        """編輯Telegram訊息"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            data = {
                'chat_id': self.chat_id,
                'message_id': message_id,
                'text': text,
                'reply_markup': json.dumps(keyboard)
            }
            
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ 編輯Telegram訊息失敗: {e}")
            return False
    
    def answer_callback_query(self, query_id, text=""):
        """回應按鈕點擊"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
            data = {
                'callback_query_id': query_id,
                'text': text,
                'show_alert': False
            }
            
            response = requests.post(url, data=data, timeout=5)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ 回應按鈕點擊失敗: {e}")
            return False
    
    def send_photo(self, photo_path, caption=""):
        """發送Telegram圖片"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption
                }
                
                response = requests.post(url, files=files, data=data, timeout=30)
                return response.status_code == 200
                
        except Exception as e:
            print(f"❌ 發送Telegram圖片失敗: {e}")
            return False

class GameMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Artale找Boss神器")
        
        # 設定視窗永遠在最上層
        self.root.attributes('-topmost', True)
        
        # 系統狀態
        self.is_running = False
        self.is_paused = False
        self.current_stage = "待機"
        self.monitoring_thread = None
        
        # 階段設定狀態
        self.stage_screenshots = {}
        self.setting_stage = None
        
        # 當機檢測設定狀態
        self.crash_screenshots = {}
        self.setting_crash = None
        
        # 狀態追蹤變數
        self.current_stage_start_time = time.time()
        self.last_stage_name = ""
        
        # 超時通知變數
        self.timeout_notified_for_current_stage = False
        self.last_timeout_notification_time = 0
        
        # 滴管取色狀態
        self.eyedropper_active = False
        
        # BOSS檢測測試狀態
        self.boss_test_active = False
        self.boss_test_thread = None
        
        # 設定資料
        self.config = {
            "telegram_chat_id": "",
            "telegram_bot_token": "8232088184:AAG2piqVAVbiBdKENJ8tsUlm8I4Zz2OmTV4",
            "detection_area": None,  # (x1, y1, x2, y2)
            "channel_area": None,    # (x1, y1, x2, y2)
            "target_color": (255, 0, 0),  # RGB
            "color_threshold": 100,
            "detection_timeout": 30,
            "click_positions": {
                "login": None,      # 階段C點位
                "character": None,  # 階段D點位
                "channel": []       # 階段F的4個點位
            },
            "telegram_bot_token": "",
            "send_welcome_message": True,
            "stage_timeout_seconds": 300,
            "stage_timeout_enabled": True
        }
        
        # 先載入設定，再設定視窗位置
        self.load_config()
        self.load_window_geometry()
        self.create_widgets()
        self.setup_hotkeys()
        
        # 初始化Telegram Bot（在config載入後）
        self.telegram_bot = TelegramBot(self)
        self.telegram_bot.start_listener()
        
        # 綁定視窗關閉事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 可收合區塊狀態 - 從設定載入
        self.section_collapsed = self.config.get("section_collapsed", {
            "status": False,
            "control": False,
            "telegram": False,
            "area": False,
            "stage": True,  # 預設收合
            "crash": True,  # 預設收合
            "color": True,  # 預設收合
            "position": True  # 預設收合
        })
        
        # 狀態顯示
        self.create_collapsible_section(main_frame, "status", "系統狀態", 0, self.create_status_widgets)
        
        # 控制按鈕
        self.create_collapsible_section(main_frame, "control", "系統控制", 1, self.create_control_widgets)
        
        # Telegram設定
        self.create_collapsible_section(main_frame, "telegram", "Telegram 設定", 2, self.create_telegram_widgets)
        
        # 區域設定
        self.create_collapsible_section(main_frame, "area", "區域設定", 3, self.create_area_widgets)
        
        # 階段設定
        self.create_collapsible_section(main_frame, "stage", "階段設定(點擊右鍵看大圖)", 4, self.create_stage_widgets)
        
        # 當機檢測設定
        # self.create_collapsible_section(main_frame, "crash", "當機檢測設定(點擊右鍵看大圖)", 5, self.create_crash_widgets)
        
        # BOSS訊息判斷設定
        self.create_collapsible_section(main_frame, "color", "BOSS訊息判斷設定", 6, self.create_color_widgets)
        
        # 點位設定
        self.create_collapsible_section(main_frame, "position", "點擊設定", 7, self.create_position_widgets)
        
        # 底部按鈕
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=8, column=0, columnspan=2, pady=10)
        
        ttk.Button(bottom_frame, text="儲存設定", command=self.save_config).grid(row=0, column=0, padx=5)
        ttk.Button(bottom_frame, text="重新設定", command=self.reset_config).grid(row=0, column=1, padx=5)
        ttk.Button(bottom_frame, text="取消點擊設定", command=self.cancel_position_recording).grid(row=0, column=2, padx=5)
        
        self.update_position_labels()
        self.update_area_labels()
        self.update_stage_labels()
        # self.update_crash_labels()
    
    def create_collapsible_section(self, parent, section_id, title, row, content_creator):
        """創建可收合的區塊"""
        # 主框架
        section_frame = ttk.Frame(parent)
        section_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        
        # 標題框架
        title_frame = ttk.Frame(section_frame)
        title_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        section_frame.grid_columnconfigure(0, weight=1)
        
        # 收合按鈕
        collapsed = self.section_collapsed[section_id]
        button_text = "▶" if collapsed else "▼"
        toggle_btn = tk.Button(title_frame, text=button_text, width=2, 
                              command=lambda: self.toggle_section(section_id))
        toggle_btn.grid(row=0, column=0, padx=5)
        
        # 標題
        title_label = ttk.Label(title_frame, text=title, font=('Arial', 10, 'bold'))
        title_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 內容框架
        content_frame = ttk.LabelFrame(section_frame, text="", padding="5")
        if not collapsed:
            content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=2)
        
        # 儲存引用
        setattr(self, f"{section_id}_toggle_btn", toggle_btn)
        setattr(self, f"{section_id}_content_frame", content_frame)
        
        # 創建內容
        content_creator(content_frame)
    
    def toggle_section(self, section_id):
        """切換區塊收合狀態"""
        self.section_collapsed[section_id] = not self.section_collapsed[section_id]
        collapsed = self.section_collapsed[section_id]
        
        # 更新按鈕文字
        toggle_btn = getattr(self, f"{section_id}_toggle_btn")
        toggle_btn.config(text="▶" if collapsed else "▼")
        
        # 顯示/隱藏內容
        content_frame = getattr(self, f"{section_id}_content_frame")
        if collapsed:
            content_frame.grid_remove()
        else:
            content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=2)
        
        # 自動保存收合狀態
        self.save_ui_state()
    
    def create_status_widgets(self, parent):
        """創建狀態顯示組件"""
        self.status_label = ttk.Label(parent, text=f"目前狀態: {self.current_stage}")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
    
    def create_control_widgets(self, parent):
        """創建控制按鈕組件"""
        
        self.start_stop_btn = ttk.Button(parent, text="開始", command=self.toggle_start_stop)
        self.start_stop_btn.grid(row=0, column=0, padx=5)
        
        self.pause_continue_btn = ttk.Button(parent, text="暫停", command=self.toggle_pause_continue, state="disabled")
        self.pause_continue_btn.grid(row=0, column=1, padx=5)
    
    def create_telegram_widgets(self, parent):
        """創建Telegram設定組件"""
        ttk.Label(parent, text="聊天室 ID:").grid(row=0, column=0, sticky=tk.W)
        self.chat_id_entry = ttk.Entry(parent, width=20)
        self.chat_id_entry.grid(row=0, column=1, padx=5)
        self.chat_id_entry.insert(0, self.config["telegram_chat_id"])
        
        ttk.Button(parent, text="測試通知", command=self.test_telegram).grid(row=0, column=2, padx=5)
    
    def create_area_widgets(self, parent):
        """創建區域設定組件"""
        ttk.Button(parent, text="設定王怪檢測區域", command=self.set_detection_area).grid(row=0, column=0, padx=5, pady=2)
        ttk.Button(parent, text="設定頻道檢測區域", command=self.set_channel_area).grid(row=0, column=1, padx=5, pady=2)
        
        # 區域狀態顯示
        ttk.Label(parent, text="王怪檢測區域:").grid(row=1, column=0, sticky=tk.W)
        self.detection_area_label = ttk.Label(parent, text="未設定", foreground="red")
        self.detection_area_label.grid(row=1, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(parent, text="頻道檢測區域:").grid(row=2, column=0, sticky=tk.W)
        self.channel_area_label = ttk.Label(parent, text="未設定", foreground="red")
        self.channel_area_label.grid(row=2, column=1, sticky=tk.W, padx=5)
    
    def create_stage_widgets(self, parent):
        """創建階段設定組件"""
        # 相似度閾值設定
        similarity_frame = tk.Frame(parent)
        similarity_frame.grid(row=0, column=0, columnspan=6, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(similarity_frame, text="畫面相似度閾值:").grid(row=0, column=0, sticky=tk.W)
        self.stage_similarity_entry = ttk.Entry(similarity_frame, width=10)
        self.stage_similarity_entry.grid(row=0, column=1, padx=5)
        # 如果設定中沒有這個值，使用預設值80%
        similarity_threshold = self.config.get("stage_similarity_threshold", 80)
        self.stage_similarity_entry.insert(0, str(similarity_threshold))
        
        # 說明標籤
        similarity_help = ttk.Label(similarity_frame, text="(0-100%, 值越高越嚴格)", font=('Arial', 8), foreground="gray")
        similarity_help.grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # 階段按鈕區域
        self.stage_labels = {}
        self.stage_buttons = {}
        self.stage_thumbnails = {}
        stages = [
            ("A", "頻道切換成功畫面"),
            ("C", "登入畫面"),
            ("D", "角色選擇畫面"),
            ("E", "遊戲內畫面"),
            ("F", "頻道切換目標畫面")
        ]
        
        for i, (stage_key, stage_name) in enumerate(stages):
            row = (i // 2) + 1  # 從第1行開始，第0行是閾值設定
            col = i % 2
            base_col = col * 3
            
            # 階段標籤
            stage_label = ttk.Label(parent, text=f"階段{stage_key}: {stage_name}")
            stage_label.grid(row=row, column=base_col, sticky=tk.W, padx=5, pady=2)
            
            # 設定按鈕或縮圖
            self.stage_buttons[stage_key] = ttk.Button(parent, text="設定", 
                                                     command=lambda k=stage_key: self.set_stage_screenshot(k))
            self.stage_buttons[stage_key].grid(row=row, column=base_col+1, padx=5, pady=2)
            
            # 狀態標籤
            self.stage_labels[stage_key] = ttk.Label(parent, text="未設定", foreground="red")
            self.stage_labels[stage_key].grid(row=row, column=base_col+2, sticky=tk.W, padx=5, pady=2)
    
    def create_crash_widgets(self, parent):
        """創建當機檢測設定組件"""
        # 相似度閾值設定
        similarity_frame = tk.Frame(parent)
        similarity_frame.grid(row=0, column=0, columnspan=6, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(similarity_frame, text="當機畫面相似度閾值:").grid(row=0, column=0, sticky=tk.W)
        self.crash_similarity_entry = ttk.Entry(similarity_frame, width=10)
        self.crash_similarity_entry.grid(row=0, column=1, padx=5)
        # 如果設定中沒有這個值，使用預設值85%
        crash_similarity_threshold = self.config.get("crash_similarity_threshold", 85)
        self.crash_similarity_entry.insert(0, str(crash_similarity_threshold))
        
        # 說明標籤
        similarity_help = ttk.Label(similarity_frame, text="(0-100%, 值越高越嚴格)", font=('Arial', 8), foreground="gray")
        similarity_help.grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # 當機檢測開關
        check_frame = tk.Frame(similarity_frame)
        check_frame.grid(row=0, column=3, padx=10)
        
        self.crash_detection_var = tk.BooleanVar()
        crash_detection_enabled = self.config.get("crash_detection_enabled", True)
        self.crash_detection_var.set(crash_detection_enabled)
        
        crash_check = ttk.Checkbutton(check_frame, text="啟用當機檢測", 
                                     variable=self.crash_detection_var)
        crash_check.grid(row=0, column=0)
        
        # 當機畫面設定按鈕區域
        self.crash_labels = {}
        self.crash_buttons = {}
        crash_types = [
            ("disconnect", "斷線重連畫面"),
            ("error", "錯誤/異常畫面"),
            ("maintenance", "維護/更新畫面"),
            ("timeout", "連線逾時畫面")
        ]
        
        for i, (crash_key, crash_name) in enumerate(crash_types):
            row = (i // 2) + 1  # 從第1行開始，第0行是閾值設定
            col = i % 2
            base_col = col * 3
            
            # 當機類型標籤
            crash_label = ttk.Label(parent, text=f"{crash_name}:")
            crash_label.grid(row=row, column=base_col, sticky=tk.W, padx=5, pady=2)
            
            # 設定按鈕或縮圖
            self.crash_buttons[crash_key] = ttk.Button(parent, text="設定", 
                                                     command=lambda k=crash_key: self.set_crash_screenshot(k))
            self.crash_buttons[crash_key].grid(row=row, column=base_col+1, padx=5, pady=2)
            
            # 狀態標籤
            self.crash_labels[crash_key] = ttk.Label(parent, text="未設定", foreground="red")
            self.crash_labels[crash_key].grid(row=row, column=base_col+2, sticky=tk.W, padx=5, pady=2)
    
    def create_color_widgets(self, parent):
        """創建BOSS訊息判斷設定組件"""
        ttk.Label(parent, text="目標顏色:").grid(row=0, column=0, sticky=tk.W)
        
        # 顏色按鈕框架
        color_frame = tk.Frame(parent)
        color_frame.grid(row=0, column=1, columnspan=2, padx=5, sticky=tk.W)
        
        self.color_btn = ttk.Button(color_frame, text="選擇顏色", command=self.choose_color)
        self.color_btn.grid(row=0, column=0, padx=2)
        
        self.eyedropper_btn = ttk.Button(color_frame, text="滴管取色", command=self.start_eyedropper)
        self.eyedropper_btn.grid(row=0, column=1, padx=2)
        
        # 顏色預覽
        self.color_preview = tk.Label(color_frame, text="    ", width=4, height=1, relief="solid", borderwidth=1)
        self.color_preview.grid(row=0, column=2, padx=5)
        self.update_color_preview()
        
        # 即時顏色預覽
        self.realtime_color_preview = tk.Label(color_frame, text="    ", width=4, height=1, relief="solid", borderwidth=1, bg="white")
        self.realtime_color_preview.grid(row=0, column=3, padx=5)
        
        # 標籤說明
        tk.Label(parent, text="設定顏色:", font=('Arial', 8)).grid(row=6, column=0, sticky=tk.W)
        tk.Label(parent, text="滑鼠顏色:", font=('Arial', 8)).grid(row=6, column=1, sticky=tk.W)
        
        # 啟動即時顏色更新
        self.start_realtime_preview()
        
        ttk.Label(parent, text="像素閾值:").grid(row=1, column=0, sticky=tk.W)
        self.threshold_entry = ttk.Entry(parent, width=10)
        self.threshold_entry.grid(row=1, column=1, padx=5)
        self.threshold_entry.insert(0, str(self.config["color_threshold"]))
        
        # 顏色相似度閾值
        ttk.Label(parent, text="顏色容差:").grid(row=2, column=0, sticky=tk.W)
        self.color_tolerance_entry = ttk.Entry(parent, width=10)
        self.color_tolerance_entry.grid(row=2, column=1, padx=5)
        # 如果設定中沒有這個值，使用預設值50
        color_tolerance = self.config.get("color_tolerance", 50)
        self.color_tolerance_entry.insert(0, str(color_tolerance))
        
        # 說明標籤
        tolerance_help = ttk.Label(parent, text="(0-255, 值越大越寬鬆)", font=('Arial', 8), foreground="gray")
        tolerance_help.grid(row=2, column=2, sticky=tk.W, padx=5)
        
        # 測試按鈕
        self.boss_test_btn = ttk.Button(parent, text="測試BOSS檢測", command=self.test_boss_detection)
        self.boss_test_btn.grid(row=3, column=0, columnspan=2, pady=5)
        
        # BOSS檢測延遲設定
        ttk.Label(parent, text="無BOSS切換延遲:").grid(row=4, column=0, sticky=tk.W)
        self.boss_wait_entry = ttk.Entry(parent, width=10)
        self.boss_wait_entry.grid(row=4, column=1, padx=5)
        # 如果設定中沒有這個值，使用預設值30秒
        boss_wait_time = self.config.get("boss_wait_time", 30)
        self.boss_wait_entry.insert(0, str(boss_wait_time))
        
        # 延遲說明標籤
        wait_help = ttk.Label(parent, text="(秒，無BOSS時多久後切換頻道)", font=('Arial', 8), foreground="gray")
        wait_help.grid(row=4, column=2, sticky=tk.W, padx=5)
        
        # BOSS後行為設定
        ttk.Label(parent, text="檢測到BOSS後:").grid(row=5, column=0, sticky=tk.W)
        self.boss_behavior_var = tk.BooleanVar()
        auto_switch_after_boss = self.config.get("auto_channel_switch_after_boss", True)
        self.boss_behavior_var.set(auto_switch_after_boss)
        
        behavior_frame = tk.Frame(parent)
        behavior_frame.grid(row=5, column=1, columnspan=2, sticky=tk.W, padx=5)
        
        auto_radio = ttk.Radiobutton(behavior_frame, text="5秒後自動切換頻道", 
                                   variable=self.boss_behavior_var, value=True)
        auto_radio.grid(row=0, column=0, sticky=tk.W)
        
        manual_radio = ttk.Radiobutton(behavior_frame, text="暫停等待手動繼續", 
                                     variable=self.boss_behavior_var, value=False)
        manual_radio.grid(row=1, column=0, sticky=tk.W)
        
        # 階段超時設定
        ttk.Label(parent, text="階段超時時間:").grid(row=6, column=0, sticky=tk.W)
        self.stage_timeout_entry = ttk.Entry(parent, width=10)
        self.stage_timeout_entry.grid(row=6, column=1, sticky=tk.W, padx=5)
        # 載入現有設定（轉換為分鐘顯示）
        timeout_minutes = self.config.get("stage_timeout_seconds", 300) // 60
        self.stage_timeout_entry.insert(0, str(timeout_minutes))
        
        # 階段超時說明標籤
        timeout_help = ttk.Label(parent, text="(分鐘，階段停留過久時發送通知)", font=('Arial', 8), foreground="gray")
        timeout_help.grid(row=6, column=2, sticky=tk.W, padx=5)
        
        # 顏色資訊顯示
        ttk.Label(parent, text="RGB值:").grid(row=7, column=0, sticky=tk.W)
        self.rgb_label = ttk.Label(parent, text=f"({self.config['target_color'][0]}, {self.config['target_color'][1]}, {self.config['target_color'][2]})")
        self.rgb_label.grid(row=7, column=1, sticky=tk.W, padx=5)
    
    def create_position_widgets(self, parent):
        """創建點位設定組件"""
        self.position_labels = {}
        self.position_buttons = {}
        positions = [
            ("login", "登入按鈕"),
            ("character", "角色選擇"),
            ("channel_1", "頻道切換-1"),
            ("channel_2", "頻道切換-2"),
            ("channel_3", "頻道切換-3"),
            ("channel_4", "頻道切換-4")
        ]
        
        for i, (key, label) in enumerate(positions):
            row = i
            # 標籤
            ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            
            # 設定按鈕
            self.position_buttons[key] = ttk.Button(parent, text="設定", 
                                                   command=lambda k=key: self.start_position_recording(k))
            self.position_buttons[key].grid(row=row, column=1, padx=5, pady=2)
            
            # 狀態標籤
            self.position_labels[key] = ttk.Label(parent, text="未設定", foreground="red")
            self.position_labels[key].grid(row=row, column=2, sticky=tk.W, padx=5, pady=2)
    
    def setup_hotkeys(self):
        """設定熱鍵和滑鼠監聽"""
        self.recording_position = None
        self.position_recording_active = False
        # 設定滑鼠監聽器
        try:
            from pynput import mouse
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()
            print("滑鼠監聽器已啟動")
        except ImportError:
            print("pynput not installed, using alternative method")
        except Exception as e:
            print(f"滑鼠監聽器啟動失敗: {e}")
    
    def start_position_recording(self, position_key):
        """開始記錄指定位置"""
        if self.is_running:
            messagebox.showerror("錯誤", "請先停止監控模式")
            return
        
        self.recording_position = position_key
        self.position_recording_active = True
        
        # 更新按鈕狀態
        for key, btn in self.position_buttons.items():
            if key == position_key:
                btn.config(text="點擊目標", style="Accent.TButton")
            else:
                btn.config(state="disabled")
        
        # 顯示提示
        position_names = {
            "login": "登入按鈕",
            "character": "角色選擇",
            "channel_1": "頻道切換-1",
            "channel_2": "頻道切換-2", 
            "channel_3": "頻道切換-3",
            "channel_4": "頻道切換-4"
        }
        
        messagebox.showinfo("設定點位", 
            f"正在設定 {position_names[position_key]} 位置\n\n"
            f"請將滑鼠移動到目標位置，然後點擊滑鼠左鍵記錄位置")
    
    def on_mouse_click(self, x, y, button, pressed):
        """滑鼠點擊事件處理"""
        # 只處理左鍵按下事件
        if not pressed:
            return
            
        # 檢查是否為左鍵
        try:
            if button.name != 'left':
                return
        except:
            # 如果無法取得button.name，檢查button值
            if str(button) != 'Button.left':
                return
        
        # 檢查是否在點位記錄模式
        if not self.position_recording_active or not self.recording_position:
            return
        
        print(f"滑鼠點擊偵測: 位置({x}, {y}), 記錄位置: {self.recording_position}")
            
        # 記錄點擊位置
        if self.recording_position in ["login", "character"]:
            self.config["click_positions"][self.recording_position] = (x, y)
        elif self.recording_position.startswith("channel_"):
            index = int(self.recording_position.split("_")[1]) - 1
            while len(self.config["click_positions"]["channel"]) <= index:
                self.config["click_positions"]["channel"].append(None)
            self.config["click_positions"]["channel"][index] = (x, y)
        
        # 重置狀態
        self.position_recording_active = False
        current_position = self.recording_position
        self.recording_position = None
        
        # 更新UI - 使用 after 方法在主執行緒中執行
        self.root.after(100, self.update_position_labels)
        self.root.after(100, self.reset_position_buttons)
        
        # 顯示結果
        position_names = {
            "login": "登入按鈕",
            "character": "角色選擇",
            "channel_1": "頻道切換-1",
            "channel_2": "頻道切換-2", 
            "channel_3": "頻道切換-3",
            "channel_4": "頻道切換-4"
        }
        
        # 使用 after 方法在主執行緒中顯示對話框
        def show_success():
            try:
                messagebox.showinfo("設定完成", 
                    f"{position_names[current_position]} 位置已設定\n座標: ({x}, {y})")
            except Exception as e:
                print(f"顯示對話框錯誤: {e}")
        
        self.root.after(200, show_success)
    
    def reset_position_buttons(self):
        """重置點位設定按鈕狀態"""
        for key, btn in self.position_buttons.items():
            btn.config(text="設定", style="TButton", state="normal")
    
    def update_position_labels(self):
        """更新位置標籤顯示"""
        login_pos = self.config["click_positions"]["login"]
        if login_pos:
            self.position_labels["login"].config(text=f"({login_pos[0]}, {login_pos[1]})", foreground="green")
        
        char_pos = self.config["click_positions"]["character"]
        if char_pos:
            self.position_labels["character"].config(text=f"({char_pos[0]}, {char_pos[1]})", foreground="green")
        
        for i in range(4):
            key = f"channel_{i+1}"
            if i < len(self.config["click_positions"]["channel"]) and self.config["click_positions"]["channel"][i]:
                pos = self.config["click_positions"]["channel"][i]
                self.position_labels[key].config(text=f"({pos[0]}, {pos[1]})", foreground="green")
    
    def update_area_labels(self):
        """更新區域標籤顯示"""
        if self.config["detection_area"]:
            coords = self.config["detection_area"]
            self.detection_area_label.config(text=f"({coords[0]}, {coords[1]}) -> ({coords[2]}, {coords[3]})", foreground="green")
        else:
            self.detection_area_label.config(text="未設定", foreground="red")
            
        if self.config["channel_area"]:
            coords = self.config["channel_area"]
            self.channel_area_label.config(text=f"({coords[0]}, {coords[1]}) -> ({coords[2]}, {coords[3]})", foreground="green")
        else:
            self.channel_area_label.config(text="未設定", foreground="red")
    
    def update_stage_labels(self):
        """更新階段標籤顯示"""
        for stage_key, label in self.stage_labels.items():
            if stage_key in self.stage_screenshots:
                label.config(text="已設定", foreground="green")
                # 更新按鈕為縮圖
                self.create_stage_thumbnail(stage_key)
            else:
                label.config(text="未設定", foreground="red")
                # 恢復為設定按鈕
                if stage_key in self.stage_buttons:
                    self.stage_buttons[stage_key].config(text="設定", command=lambda k=stage_key: self.set_stage_screenshot(k))
    
    def create_stage_thumbnail(self, stage_key):
        """創建階段縮圖按鈕"""
        if stage_key not in self.stage_screenshots:
            return
        
        try:
            # 取得截圖並縮小
            screenshot = self.stage_screenshots[stage_key]
            
            # 縮放圖片為縮圖大小
            thumbnail_size = (60, 40)
            h, w = screenshot.shape[:2]
            
            # 計算縮放比例
            scale = min(thumbnail_size[0]/w, thumbnail_size[1]/h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            # 縮放圖片
            resized_img = cv2.resize(screenshot, (new_w, new_h))
            
            # 轉換為PhotoImage
            pil_img = Image.fromarray(resized_img)
            photo = ImageTk.PhotoImage(pil_img)
            
            # 更新按鈕顯示縮圖
            button = self.stage_buttons[stage_key]
            button.config(text="", image=photo, command=lambda k=stage_key: self.set_stage_screenshot(k))
            
            # 綁定右鍵點擊事件
            button.bind("<Button-3>", lambda event, k=stage_key: self.show_stage_preview(k))
            
            # 保持引用避免被回收
            if not hasattr(self, 'stage_photos'):
                self.stage_photos = {}
            self.stage_photos[stage_key] = photo
            
        except Exception as e:
            print(f"創建階段 {stage_key} 縮圖失敗: {e}")
            # 失敗時顯示文字
            self.stage_buttons[stage_key].config(text="已設定", command=lambda k=stage_key: self.set_stage_screenshot(k))
    
    def update_crash_labels(self):
        """更新當機檢測標籤顯示"""
        for crash_key, label in self.crash_labels.items():
            if crash_key in self.crash_screenshots:
                label.config(text="已設定", foreground="green")
                # 更新按鈕為縮圖
                self.create_crash_thumbnail(crash_key)
            else:
                label.config(text="未設定", foreground="red")
                # 恢復為設定按鈕
                if crash_key in self.crash_buttons:
                    self.crash_buttons[crash_key].config(text="設定", command=lambda k=crash_key: self.set_crash_screenshot(k))
    
    def create_crash_thumbnail(self, crash_key):
        """創建當機檢測縮圖按鈕"""
        if crash_key not in self.crash_screenshots:
            return
        
        try:
            # 取得截圖並縮小
            screenshot = self.crash_screenshots[crash_key]
            
            # 縮放圖片為縮圖大小
            thumbnail_size = (60, 40)
            h, w = screenshot.shape[:2]
            
            # 計算縮放比例
            scale = min(thumbnail_size[0]/w, thumbnail_size[1]/h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            # 縮放圖片
            resized_img = cv2.resize(screenshot, (new_w, new_h))
            
            # 轉換為PhotoImage
            pil_img = Image.fromarray(resized_img)
            photo = ImageTk.PhotoImage(pil_img)
            
            # 更新按鈕顯示縮圖
            button = self.crash_buttons[crash_key]
            button.config(text="", image=photo, command=lambda k=crash_key: self.set_crash_screenshot(k))
            
            # 綁定右鍵點擊事件
            button.bind("<Button-3>", lambda event, k=crash_key: self.show_crash_preview(k))
            
            # 保持引用避免被回收
            if not hasattr(self, 'crash_photos'):
                self.crash_photos = {}
            self.crash_photos[crash_key] = photo
            
        except Exception as e:
            print(f"創建當機檢測 {crash_key} 縮圖失敗: {e}")
            # 失敗時顯示文字
            self.crash_buttons[crash_key].config(text="已設定", command=lambda k=crash_key: self.set_crash_screenshot(k))
    
    def set_crash_screenshot(self, crash_key):
        """設定當機檢測截圖"""
        if self.is_running:
            messagebox.showerror("錯誤", "請先停止監控模式")
            return
        
        crash_names = {
            "disconnect": "斷線重連畫面",
            "error": "錯誤/異常畫面", 
            "maintenance": "維護/更新畫面",
            "timeout": "連線逾時畫面"
        }
        
        crash_name = crash_names.get(crash_key, f"當機類型 {crash_key}")
        
        result = messagebox.askyesno("設定當機檢測截圖", 
            f"即將設定 {crash_name} 的參考截圖\n\n"
            f"請確保當前畫面顯示的是 {crash_name}\n"
            f"點擊「是」開始截取畫面")
        
        if result:
            self.setting_crash = crash_key
            self.capture_crash_screenshot()
    
    def capture_crash_screenshot(self):
        """擷取當機檢測畫面截圖"""
        try:
            # 隱藏主視窗避免干擾
            self.root.withdraw()
            time.sleep(0.5)  # 等待視窗隱藏
            
            # 截取全螢幕
            screenshot = pyautogui.screenshot()
            
            # 轉換為OpenCV格式
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # 儲存截圖
            self.crash_screenshots[self.setting_crash] = screenshot_cv
            
            # 顯示主視窗
            self.root.deiconify()
            
            crash_names = {
                "disconnect": "斷線重連畫面",
                "error": "錯誤/異常畫面",
                "maintenance": "維護/更新畫面", 
                "timeout": "連線逾時畫面"
            }
            
            crash_name = crash_names.get(self.setting_crash, f"當機類型 {self.setting_crash}")
            
            # 更新UI
            self.update_crash_labels()
            
            messagebox.showinfo("截圖完成", f"{crash_name} 截圖已設定完成！")
            
            # 重置設定狀態
            self.setting_crash = None
            
        except Exception as e:
            # 確保主視窗顯示
            self.root.deiconify()
            messagebox.showerror("錯誤", f"截圖失敗: {str(e)}")
            self.setting_crash = None
    
    def show_crash_preview(self, crash_key):
        """顯示當機檢測截圖預覽"""
        if crash_key not in self.crash_screenshots:
            return
        
        try:
            # 創建預覽視窗
            preview_window = tk.Toplevel(self.root)
            preview_window.title(f"當機檢測預覽 - {crash_key}")
            preview_window.attributes('-topmost', True)
            
            # 取得截圖
            screenshot = self.crash_screenshots[crash_key]
            
            # 計算適當的顯示大小（最大800x600）
            h, w = screenshot.shape[:2]
            max_w, max_h = 800, 600
            
            if w > max_w or h > max_h:
                scale = min(max_w/w, max_h/h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                resized_img = cv2.resize(screenshot, (new_w, new_h))
            else:
                resized_img = screenshot
            
            # 轉換為PhotoImage
            pil_img = Image.fromarray(resized_img)
            photo = ImageTk.PhotoImage(pil_img)
            
            # 顯示圖片
            label = ttk.Label(preview_window, image=photo)
            label.pack(padx=10, pady=10)
            
            # 保持引用
            label.image = photo
            
            # 關閉按鈕
            close_btn = ttk.Button(preview_window, text="關閉", command=preview_window.destroy)
            close_btn.pack(pady=5)
            
        except Exception as e:
            messagebox.showerror("錯誤", f"無法顯示預覽: {str(e)}")
    
    def set_detection_area(self):
        """設定王怪檢測區域"""
        messagebox.showinfo("區域選擇", "請用滑鼠拖曳選擇王怪檢測區域\n按ESC取消選擇")
        self.select_area("detection")
    
    def set_channel_area(self):
        """設定頻道檢測區域"""
        messagebox.showinfo("區域選擇", "請用滑鼠拖曳選擇頻道檢測區域\n按ESC取消選擇")
        self.select_area("channel")
    
    def select_area(self, area_type):
        """選擇螢幕區域"""
        self.root.withdraw()  # 隱藏主視窗
        
        # 創建全螢幕選擇視窗
        selection_window = tk.Toplevel()
        selection_window.attributes('-fullscreen', True)
        selection_window.attributes('-alpha', 0.3)
        selection_window.configure(bg='black')
        selection_window.attributes('-topmost', True)
        
        # 建立畫布
        canvas = tk.Canvas(selection_window, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # 顯示提示訊息
        screen_width = selection_window.winfo_screenwidth()
        screen_height = selection_window.winfo_screenheight()
        
        instruction_text = "請拖曳滑鼠選擇區域 (按ESC取消)"
        canvas.create_text(screen_width//2, 50, text=instruction_text, 
                          fill='white', font=('Arial', 16))
        
        # 選擇狀態變數
        start_x = start_y = end_x = end_y = 0
        selection_rect = None
        is_selecting = False
        
        def on_button_press(event):
            nonlocal start_x, start_y, is_selecting, selection_rect
            start_x, start_y = event.x, event.y
            is_selecting = True
            if selection_rect:
                canvas.delete(selection_rect)
        
        def on_mouse_drag(event):
            nonlocal end_x, end_y, selection_rect
            if is_selecting:
                end_x, end_y = event.x, event.y
                if selection_rect:
                    canvas.delete(selection_rect)
                
                # 繪製選擇框
                selection_rect = canvas.create_rectangle(
                    start_x, start_y, end_x, end_y,
                    outline='red', width=2, fill='red', stipple='gray50'
                )
                
                # 顯示座標資訊
                canvas.delete("coords_info")
                coords_text = f"({start_x}, {start_y}) -> ({end_x}, {end_y})"
                canvas.create_text(screen_width//2, screen_height-50, 
                                 text=coords_text, fill='white', 
                                 font=('Arial', 12), tags="coords_info")
        
        def on_button_release(event):
            nonlocal is_selecting
            if is_selecting:
                is_selecting = False
                # 確保座標順序正確
                x1, y1 = min(start_x, end_x), min(start_y, end_y)
                x2, y2 = max(start_x, end_x), max(start_y, end_y)
                
                if abs(x2 - x1) > 10 and abs(y2 - y1) > 10:  # 確保選擇區域夠大
                    coords = (x1, y1, x2, y2)
                    if area_type == "detection":
                        self.config["detection_area"] = coords
                        area_name = "王怪檢測"
                    else:
                        self.config["channel_area"] = coords
                        area_name = "頻道檢測"
                    
                    selection_window.destroy()
                    self.root.deiconify()  # 顯示主視窗
                    self.update_area_labels()  # 更新區域狀態顯示
                    messagebox.showinfo("設定完成", 
                                      f"{area_name}區域已設定\n座標: {coords}")
                else:
                    canvas.create_text(screen_width//2, screen_height//2, 
                                     text="選擇區域太小，請重新選擇", 
                                     fill='yellow', font=('Arial', 14))
        
        def on_escape(event):
            selection_window.destroy()
            self.root.deiconify()  # 顯示主視窗
        
        # 綁定事件
        canvas.bind("<Button-1>", on_button_press)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_button_release)
        selection_window.bind("<Escape>", on_escape)
        selection_window.focus_set()
        
        # 滑鼠游標樣式
        canvas.configure(cursor="crosshair")
    
    def choose_color(self):
        """選擇目標顏色"""
        color = colorchooser.askcolor(title="選擇BOSS訊息顏色", initialcolor=self.config["target_color"])
        if color[0]:
            self.config["target_color"] = tuple(int(c) for c in color[0])
            self.update_color_display()
    
    def start_eyedropper(self):
        """開始滴管取色"""
        if self.is_running:
            messagebox.showerror("錯誤", "請先停止監控模式")
            return
        
        self.eyedropper_active = True
        self.eyedropper_btn.config(text="點擊位置取色", style="Accent.TButton")
        
        messagebox.showinfo("滴管取色", "請移動滑鼠到要取色的位置，然後點擊滑鼠左鍵")
        
        # 設定滑鼠點擊監聽
        def on_click(x, y, button, pressed):
            if self.eyedropper_active and pressed and button.name == 'left':
                color = self.get_pixel_color(x, y)
                if color:
                    self.config["target_color"] = color
                    self.update_color_display()
                    self.root.after(100, lambda: messagebox.showinfo("取色完成", 
                        f"已取得顏色 RGB{color}\n位置: ({x}, {y})"))
                
                # 停止取色模式
                self.stop_eyedropper_mode()
                return False  # 停止監聽
        
        # 啟動滑鼠監聽
        try:
            from pynput import mouse
            self.eyedropper_mouse_listener = mouse.Listener(on_click=on_click)
            self.eyedropper_mouse_listener.start()
        except Exception as e:
            print(f"滑鼠監聽啟動失敗: {e}")
            self.stop_eyedropper_mode()
    
    def stop_eyedropper_mode(self):
        """停止滴管取色模式"""
        self.eyedropper_active = False
        self.eyedropper_btn.config(text="滴管取色", style="TButton")
        
        if hasattr(self, 'eyedropper_mouse_listener'):
            try:
                self.eyedropper_mouse_listener.stop()
            except:
                pass
    
    def get_pixel_color(self, x, y):
        """取得指定位置的像素顏色"""
        try:
            # 使用pyautogui作為主要方法
            pixel = pyautogui.screenshot().getpixel((x, y))
            print(f"取色成功: 位置({x}, {y}) RGB{pixel}")
            return pixel
        except Exception as e:
            print(f"pyautogui取色失敗: {e}")
            # 使用mss作為備用方法
            try:
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x, "width": 1, "height": 1}
                    screenshot = sct.grab(monitor)
                    pixel = screenshot.pixel(0, 0)
                    r, g, b = pixel[2], pixel[1], pixel[0]  # BGRA to RGB
                    print(f"mss備用取色成功: RGB({r}, {g}, {b})")
                    return (r, g, b)
            except Exception as e2:
                print(f"mss備用取色也失敗: {e2}")
                return (0, 0, 0)
    
    def update_color_display(self):
        """更新顏色顯示"""
        color = self.config["target_color"]
        
        # 更新按鈕文字
        self.color_btn.config(text=f"RGB{color}")
        
        # 更新RGB標籤
        self.rgb_label.config(text=f"({color[0]}, {color[1]}, {color[2]})")
        
        # 更新顏色預覽
        self.update_color_preview()
    
    def update_color_preview(self):
        """更新顏色預覽"""
        color = self.config["target_color"]
        hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        self.color_preview.config(bg=hex_color)
    
    def start_realtime_preview(self):
        """開始即時顏色預覽"""
        def update_realtime():
            try:
                if hasattr(self, 'realtime_color_preview') and self.realtime_color_preview.winfo_exists():
                    x, y = pyautogui.position()
                    color = self.get_pixel_color_simple(x, y)
                    if color:
                        hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
                        self.realtime_color_preview.config(bg=hex_color)
                    
                    # 每300ms更新一次 (平衡性能和流暢度)
                    self.root.after(300, update_realtime)
            except:
                # 發生錯誤時重試
                self.root.after(1000, update_realtime)
        
        # 延遲500ms開始，確保界面完全載入
        self.root.after(500, update_realtime)
    
    def get_pixel_color_simple(self, x, y):
        """簡化的取色方法，專用於即時預覽"""
        try:
            # 使用pyautogui快速取色
            pixel = pyautogui.screenshot().getpixel((x, y))
            return pixel
        except:
            return (255, 255, 255)  # 失敗時返回白色
    
    def test_boss_detection(self):
        """測試BOSS檢測功能"""
        if self.is_running or self.boss_test_active:
            messagebox.showerror("錯誤", "請先停止監控或測試模式")
            return
        
        # 檢查設定完整性
        if not self.config["detection_area"]:
            messagebox.showerror("設定錯誤", "請先設定王怪檢測區域")
            return
        
        # 更新設定值
        try:
            self.config["color_threshold"] = int(self.threshold_entry.get())
            self.config["color_tolerance"] = int(self.color_tolerance_entry.get())
        except ValueError:
            messagebox.showerror("設定錯誤", "請輸入有效的數值")
            return
        
        # 開始測試
        self.boss_test_active = True
        self.boss_test_btn.config(text="測試中...", state="disabled")
        
        messagebox.showinfo("開始測試", "將在5秒內檢測王怪區域是否符合BOSS設定\n請確保遊戲畫面可見")
        
        # 啟動測試執行緒
        self.boss_test_thread = threading.Thread(target=self.run_boss_test, daemon=True)
        self.boss_test_thread.start()
    
    def run_boss_test(self):
        """執行BOSS檢測測試 - 5秒內檢測王怪區域"""
        test_duration = 5  # 測試5秒
        check_interval = 0.2  # 每0.2秒檢測一次
        start_time = time.time()
        boss_detected = False
        detection_time = None
        
        try:
            # 更新狀態顯示
            for i in range(5, 0, -1):
                if not self.boss_test_active:
                    break
                    
                self.root.after(0, lambda seconds=i: self.update_test_status(f"測試中... 剩餘 {seconds} 秒"))
                
                # 在這1秒內檢測5次
                for j in range(5):
                    if not self.boss_test_active:
                        break
                        
                    # 執行BOSS檢測
                    if self.detect_boss():
                        boss_detected = True
                        detection_time = time.time() - start_time
                        break
                    
                    time.sleep(0.2)
                
                if boss_detected:
                    break
            
            # 更新UI必須在主執行緒中
            if boss_detected:
                self.root.after(0, lambda: self.show_test_result(True, detection_time))
            else:
                self.root.after(0, lambda: self.show_test_result(False))
                
        except Exception as e:
            print(f"測試過程發生錯誤: {e}")
            self.root.after(0, lambda: self.show_test_result(False, error_msg=str(e)))
        
        # 重置測試狀態
        self.boss_test_active = False
        self.root.after(0, self.reset_boss_test_button)
    
    def update_test_status(self, status_text):
        """更新測試狀態顯示"""
        self.boss_test_btn.config(text=status_text)
    
    def show_test_result(self, detected, detection_time=None, error_msg=None):
        """顯示測試結果"""
        if error_msg:
            messagebox.showerror("測試錯誤", f"測試過程發生錯誤:\n{error_msg}")
        elif detected:
            # 取得當前設定值顯示
            timestamp = datetime.now().strftime("%H:%M:%S")
            result_msg = f"✅ 偵測到BOSS！\n\n"
            result_msg += f"檢測時間: {timestamp}\n"
            if detection_time:
                result_msg += f"偵測用時: {detection_time:.1f} 秒\n"
            result_msg += f"目標顏色: RGB{self.config['target_color']}\n"
            result_msg += f"顏色容差: {self.config['color_tolerance']}\n"
            result_msg += f"像素閾值: {self.config['color_threshold']}\n\n"
            result_msg += "✓ 當前設定可以成功檢測到BOSS訊息"
            
            messagebox.showinfo("測試結果", result_msg)
        else:
            result_msg = f"❌ 5秒內未偵測到BOSS\n\n"
            result_msg += f"測試時間: 5秒 (完整測試)\n"
            result_msg += f"目標顏色: RGB{self.config['target_color']}\n"
            result_msg += f"顏色容差: {self.config['color_tolerance']}\n"
            result_msg += f"像素閾值: {self.config['color_threshold']}\n"
            result_msg += f"檢測區域: {self.config['detection_area']}\n\n"
            result_msg += "建議調整:\n"
            result_msg += "• 檢查目標顏色是否正確 (使用滴管取色)\n"
            result_msg += "• 增加顏色容差值 (建議50-100)\n"
            result_msg += "• 降低像素閾值 (建議50-200)\n"
            result_msg += "• 確認王怪檢測區域包含BOSS訊息\n"
            result_msg += "• 確保測試時遊戲畫面中有BOSS訊息"
            
            messagebox.showwarning("測試結果", result_msg)
    
    def reset_boss_test_button(self):
        """重置測試按鈕狀態"""
        self.boss_test_btn.config(text="測試BOSS檢測", state="normal")
    
    def test_telegram(self):
        """測試Telegram通知"""
        chat_id = self.chat_id_entry.get().strip()
        if not chat_id:
            messagebox.showerror("錯誤", "請輸入聊天室ID")
            return
        
        success = self.send_telegram_message(chat_id, "測試訊息：系統運作正常！")
        if success:
            messagebox.showinfo("成功", "Telegram通知測試成功！")
        else:
            messagebox.showerror("失敗", "Telegram通知測試失敗，請檢查聊天室ID")
    
    def send_telegram_message(self, chat_id, message):
        """發送Telegram訊息"""
        try:
            url = f"https://api.telegram.org/bot{self.config['telegram_bot_token']}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message
            }
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram發送失敗: {e}")
            return False
    
    def toggle_start_stop(self):
        """開始/停止按鈕"""
        if not self.is_running:
            # 停止測試模式
            if self.boss_test_active:
                self.boss_test_active = False
                self.reset_boss_test_button()
            
            # 檢查設定完整性
            if not self.validate_config():
                return
            
            self.is_running = True
            self.start_stop_btn.config(text="停止")
            self.pause_continue_btn.config(state="normal")
            self.current_stage = "啟動中"
            self.update_status()
            
            # 重置BOSS檢測計時器
            if hasattr(self, 'boss_check_start_time'):
                delattr(self, 'boss_check_start_time')
            
            # 開始監控執行緒
            self.monitoring_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
            self.monitoring_thread.start()
        else:
            self.is_running = False
            self.is_paused = False
            self.start_stop_btn.config(text="開始")
            self.pause_continue_btn.config(text="暫停", state="disabled")
            self.current_stage = "已停止"
            self.update_status()
    
    def toggle_pause_continue(self):
        """暫停/繼續按鈕"""
        if not self.is_paused:
            self.is_paused = True
            self.pause_continue_btn.config(text="繼續")
            self.current_stage = "已暫停"
        else:
            self.is_paused = False
            self.pause_continue_btn.config(text="暫停")
            self.current_stage = "運行中"
        self.update_status()
    
    def update_status(self):
        """更新狀態顯示"""
        # 檢測狀態變化並更新時間記錄
        if self.current_stage != self.last_stage_name:
            self.current_stage_start_time = time.time()
            self.last_stage_name = self.current_stage
            self.timeout_notified_for_current_stage = False  # 重置超時通知狀態
            print(f"狀態變更: {self.current_stage}")
        
        # 檢查階段停留超時
        self.check_stage_timeout()
        
        self.status_label.config(text=f"目前狀態: {self.current_stage}")
    
    def check_stage_timeout(self):
        """檢查階段停留超時"""
        try:
            # 檢查是否啟用超時通知
            if not self.config.get("stage_timeout_enabled", True):
                return
            
            # 如果已經通知過當前階段，跳過
            if self.timeout_notified_for_current_stage:
                return
            
            # 計算當前階段停留時間
            current_time = time.time()
            elapsed_time = current_time - self.current_stage_start_time
            timeout_threshold = self.config.get("stage_timeout_seconds", 300)
            
            # 檢查是否超時
            if elapsed_time > timeout_threshold:
                self.send_stage_timeout_notification(elapsed_time, timeout_threshold)
                self.timeout_notified_for_current_stage = True
                self.last_timeout_notification_time = current_time
                
        except Exception as e:
            print(f"❌ 檢查階段超時失敗: {e}")
    
    def send_stage_timeout_notification(self, elapsed_time, threshold_time):
        """發送階段超時通知"""
        try:
            # 格式化時間顯示
            elapsed_str = self.format_duration_for_timeout(elapsed_time)
            threshold_str = self.format_duration_for_timeout(threshold_time)
            
            # 構建通知訊息
            message = f"""⚠️ 階段停留過久

目前階段：{self.current_stage}
停留時間：{elapsed_str}
設定閾值：{threshold_str}

時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            # 發送Telegram通知
            if hasattr(self, 'telegram_bot') and self.telegram_bot:
                chat_id = self.config.get("telegram_chat_id", "")
                if chat_id:
                    self.telegram_bot.send_message(message)
                    print(f"✅ 已發送階段超時通知: {self.current_stage}")
                else:
                    print("⚠️ 未設定Telegram Chat ID，無法發送超時通知")
            else:
                print("⚠️ Telegram Bot未初始化，無法發送超時通知")
                
        except Exception as e:
            print(f"❌ 發送階段超時通知失敗: {e}")
    
    def format_duration_for_timeout(self, seconds):
        """格式化超時時間顯示"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = int(seconds % 60)
            if remaining_seconds > 0:
                return f"{minutes}分{remaining_seconds}秒"
            else:
                return f"{minutes}分鐘"
        else:
            hours = int(seconds // 3600)
            remaining_minutes = int((seconds % 3600) // 60)
            if remaining_minutes > 0:
                return f"{hours}小時{remaining_minutes}分鐘"
            else:
                return f"{hours}小時"
    
    def validate_config(self):
        """驗證設定完整性"""
        chat_id = self.chat_id_entry.get().strip()
        if not chat_id:
            messagebox.showerror("設定錯誤", "請設定Telegram聊天室ID")
            return False
        
        if not self.config["detection_area"]:
            messagebox.showerror("設定錯誤", "請設定王怪檢測區域")
            return False
        
        if not self.config["click_positions"]["login"]:
            messagebox.showerror("設定錯誤", "請設定登入按鈕位置")
            return False
        
        return True
    
    def monitoring_loop(self):
        """主要監控循環"""
        self.config["telegram_chat_id"] = self.chat_id_entry.get().strip()
        self.config["color_threshold"] = int(self.threshold_entry.get())
        self.config["auto_channel_switch_after_boss"] = self.boss_behavior_var.get()
        
        stage = "A"  # 從階段A開始（頻道切換成功確認）
        
        while self.is_running:
            if self.is_paused:
                time.sleep(0.1)
                continue
            
            try:
                if stage == "A":
                    stage = self.stage_a()
                elif stage == "C":
                    stage = self.stage_c()
                elif stage == "D":
                    stage = self.stage_d()
                elif stage == "E":
                    stage = self.stage_e()
                elif stage == "F":
                    stage = self.stage_f()
                
                time.sleep(0.5)  # 縮短基本延遲，提高響應速度
            except Exception as e:
                print(f"監控循環錯誤: {e}")
                self.current_stage = f"階段{stage}: 發生錯誤 - {str(e)}"
                self.update_status()
                time.sleep(1)
    
    def stage_a(self):
        """階段A: 頻道切換成功確認"""
        self.current_stage = "階段A: 檢查是否為頻道切換成功畫面"
        self.update_status()
        
        # 檢查是否有階段A的截圖設定
        if "A" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段A
            if self.detect_stage_match("A"):
                self.current_stage = "階段A: ✓ 匹配頻道切換成功畫面"
                self.update_status()
                time.sleep(1)
                return "C"
            else:
                self.current_stage = "階段A: ✗ 不匹配頻道切換成功畫面，繼續檢查"
                self.update_status()
        else:
            self.current_stage = "階段A: 未設定參考畫面，跳過檢查"
            self.update_status()
        
        # 沒有匹配，等待一段時間後重新檢查
        time.sleep(2)
        return "A"  # 繼續停留在階段A檢查
    
    def stage_c(self):
        """階段C: 等待登入畫面出現"""
        # 檢查是否有階段C的截圖設定
        if "C" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段C（登入畫面）
            if self.detect_stage_match("C"):
                self.current_stage = "階段C: ✓ 檢測到登入畫面，執行登入點擊"
                self.update_status()
                
                # 確認是登入畫面，執行登入點擊
                login_pos = self.config["click_positions"]["login"]
                if login_pos:
                    pyautogui.click(login_pos[0], login_pos[1])
                    time.sleep(2)
                    return "D"  # 進入階段D等待角色選擇畫面
                else:
                    self.current_stage = "階段C: 未設定登入按鈕位置"
                    self.update_status()
                    time.sleep(2)
                    return "C"
            else:
                self.current_stage = "階段C: 等待登入畫面出現"
                self.update_status()
        else:
            # 沒有設定截圖，假設已經是登入畫面，直接點擊登入
            self.current_stage = "階段C: 未設定參考畫面，執行登入點擊"
            self.update_status()
            
            login_pos = self.config["click_positions"]["login"]
            if login_pos:
                pyautogui.click(login_pos[0], login_pos[1])
                time.sleep(2)
                return "D"
        
        # 等待登入畫面出現
        time.sleep(1)
        return "C"
    
    def stage_d(self):
        """階段D: 等待角色選擇畫面出現"""
        # 檢查是否有階段D的截圖設定
        if "D" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段D（角色選擇畫面）
            if self.detect_stage_match("D"):
                self.current_stage = "階段D: ✓ 檢測到角色選擇畫面，執行角色點擊"
                self.update_status()
                
                # 確認是角色選擇畫面，執行角色點擊
                char_pos = self.config["click_positions"]["character"]
                if char_pos:
                    pyautogui.click(char_pos[0], char_pos[1])
                    time.sleep(2)
                    return "E"  # 進入階段E進行BOSS檢測
                else:
                    self.current_stage = "階段D: 未設定角色選擇按鈕位置"
                    self.update_status()
                    time.sleep(2)
                    return "D"
            else:
                # 檢查是否還在上個階段（階段C）
                if "C" in self.stage_screenshots and self.detect_stage_match("C"):
                    self.current_stage = "階段D: 檢測到仍在登入畫面，執行登入點擊"
                    self.update_status()
                    
                    # 還在登入畫面，執行登入點擊
                    login_pos = self.config["click_positions"]["login"]
                    if login_pos:
                        pyautogui.click(login_pos[0], login_pos[1])
                        time.sleep(2)
                    return "D"  # 繼續等待角色選擇畫面
                else:
                    self.current_stage = "階段D: 等待角色選擇畫面出現"
                    self.update_status()
        else:
            # 沒有設定截圖，假設已經是角色選擇畫面，直接點擊角色
            self.current_stage = "階段D: 未設定參考畫面，執行角色點擊"
            self.update_status()
            
            char_pos = self.config["click_positions"]["character"]
            if char_pos:
                pyautogui.click(char_pos[0], char_pos[1])
                time.sleep(2)
                return "E"
        
        # 等待角色選擇畫面出現
        time.sleep(1)
        return "D"
    
    def stage_e(self):
        """階段E: 專心BOSS檢測，不被中斷"""
        # 直接進行BOSS檢測，不進行任何畫面匹配判斷
        if self.detect_boss():
            # 重置計時器 (檢測到BOSS後重新開始計時)
            if hasattr(self, 'boss_check_start_time'):
                delattr(self, 'boss_check_start_time')
            
            # 發送通知
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"BOSS出現！\n時間: {timestamp}"
            
            self.send_telegram_message(self.config["telegram_chat_id"], message)
            
            # 檢查是否要自動進入頻道切換
            auto_switch = self.config.get("auto_channel_switch_after_boss", True)
            
            if auto_switch:
                # 自動模式：發送通知並暫停等待5秒
                self.is_paused = True
                self.pause_continue_btn.config(text="繼續", style="Accent.TButton")
                self.current_stage = "檢測到BOSS！已暫停，5秒後自動切換頻道..."
                self.update_status()
                
                # 等待5秒倒數
                for i in range(5, 0, -1):
                    if not self.is_running:
                        return "E"
                    if not self.is_paused:  # 如果用戶手動點擊繼續，提前結束等待
                        break
                    self.current_stage = f"檢測到BOSS！已暫停，{i}秒後自動切換頻道..."
                    self.update_status()
                    time.sleep(1)
                
                # 自動恢復並進入頻道切換
                self.is_paused = False
                self.pause_continue_btn.config(text="暫停", style="TButton")
                return "F"  # 進入頻道切換
            else:
                # 手動模式：暫停等待使用者點繼續
                self.is_paused = True
                self.pause_continue_btn.config(text="繼續", style="Accent.TButton")
                self.current_stage = "檢測到BOSS - 請打完後點繼續"
                self.update_status()
                
                # 等待使用者點繼續
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                
                self.pause_continue_btn.config(style="TButton")
                return "F"
        else:
            # 沒有檢測到BOSS，計時邏輯
            if not hasattr(self, 'boss_check_start_time'):
                self.boss_check_start_time = time.time()
                
            elapsed = time.time() - self.boss_check_start_time
            wait_time = self.config.get("boss_wait_time", 30)
            remaining = max(0, wait_time - elapsed)
            
            if remaining > 0:
                self.current_stage = f"階段E: 專心BOSS檢測中... 無BOSS還有 {remaining:.0f} 秒切頻道"
                self.update_status()
                time.sleep(0.1)  # 快速檢測間隔，每0.1秒檢測一次
                return "E"
            else:
                # 超過等待時間，切換頻道
                if hasattr(self, 'boss_check_start_time'):
                    delattr(self, 'boss_check_start_time')
                return "F"
        
        return "E"  # 繼續在階段E檢測BOSS
        # 檢查是否有階段E的截圖設定
        if "E" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段E（遊戲內畫面）
            if self.detect_stage_match("E"):
                self.current_stage = "階段E: ✓ 檢測到遊戲內畫面，開始BOSS檢測"
                self.update_status()
                
                # 確認在遊戲內，進行BOSS檢測
                if self.detect_boss():
                    # 重置計時器 (檢測到BOSS後重新開始計時)
                    if hasattr(self, 'boss_check_start_time'):
                        delattr(self, 'boss_check_start_time')
                    
                    # 發送通知
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    message = f"BOSS出現！\n時間: {timestamp}"
                    
                    self.send_telegram_message(self.config["telegram_chat_id"], message)
                    
                    # 檢查是否要自動進入頻道切換
                    auto_switch = self.config.get("auto_channel_switch_after_boss", True)
                    
                    if auto_switch:
                        # 自動模式：發送通知並暫停等待5秒
                        self.is_paused = True
                        self.pause_continue_btn.config(text="繼續", style="Accent.TButton")
                        self.current_stage = "檢測到BOSS！已暫停，5秒後自動切換頻道..."
                        self.update_status()
                        
                        # 等待5秒倒數
                        for i in range(5, 0, -1):
                            if not self.is_running:
                                return "E"
                            if not self.is_paused:  # 如果用戶手動點擊繼續，提前結束等待
                                break
                            self.current_stage = f"檢測到BOSS！已暫停，{i}秒後自動切換頻道..."
                            self.update_status()
                            time.sleep(1)
                        
                        # 自動恢復並進入頻道切換
                        self.is_paused = False
                        self.pause_continue_btn.config(text="暫停", style="TButton")
                        return "F"  # 進入頻道切換
                    else:
                        # 手動模式：暫停等待使用者點繼續
                        self.is_paused = True
                        self.pause_continue_btn.config(text="繼續", style="Accent.TButton")
                        self.current_stage = "檢測到BOSS - 請打完後點繼續"
                        self.update_status()
                        
                        # 等待使用者點繼續
                        while self.is_paused and self.is_running:
                            time.sleep(0.1)
                        
                        self.pause_continue_btn.config(style="TButton")
                        return "F"
                
                # 沒有檢測到BOSS，檢查是否達到等待時間
                if not hasattr(self, 'boss_check_start_time'):
                    self.boss_check_start_time = time.time()
                
                elapsed_time = time.time() - self.boss_check_start_time
                wait_time = self.config.get("boss_wait_time", 30)
                
                remaining_time = max(0, int(wait_time - elapsed_time))
                self.current_stage = f"階段E: BOSS檢測中 ({remaining_time}秒後切換頻道)"
                self.update_status()
                
                if elapsed_time >= wait_time:
                    # 重置計時器，準備下一輪檢測
                    self.boss_check_start_time = time.time()
                    return "F"  # 進入頻道切換
            else:
                # 檢查是否還在上個階段（階段D）
                if "D" in self.stage_screenshots and self.detect_stage_match("D"):
                    self.current_stage = "階段E: 檢測到仍在角色選擇畫面，執行角色點擊"
                    self.update_status()
                    
                    # 還在角色選擇畫面，執行角色點擊
                    char_pos = self.config["click_positions"]["character"]
                    if char_pos:
                        pyautogui.click(char_pos[0], char_pos[1])
                        time.sleep(2)
                    return "E"  # 繼續等待進入遊戲
                else:
                    self.current_stage = "階段E: 等待進入遊戲內畫面"
                    self.update_status()
        else:
            # 沒有設定截圖，直接進行BOSS檢測
            self.current_stage = "階段E: 未設定參考畫面，直接進行BOSS檢測"
            self.update_status()
            
            # 進行BOSS檢測
            if self.detect_boss():
                # 重置計時器
                if hasattr(self, 'boss_check_start_time'):
                    delattr(self, 'boss_check_start_time')
                
                # 發送通知並暫停
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = f"BOSS出現！\n時間: {timestamp}"
                
                self.send_telegram_message(self.config["telegram_chat_id"], message)
                
                # 自動暫停，等待使用者繼續
                self.is_paused = True
                self.pause_continue_btn.config(text="繼續", style="Accent.TButton")
                self.current_stage = "檢測到BOSS - 請打完後點繼續"
                self.update_status()
                
                # 等待使用者點繼續
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                
                self.pause_continue_btn.config(style="TButton")
                return "F"
            
            # 沒有檢測到BOSS，檢查是否達到等待時間
            if not hasattr(self, 'boss_check_start_time'):
                self.boss_check_start_time = time.time()
            
            elapsed_time = time.time() - self.boss_check_start_time
            wait_time = self.config.get("boss_wait_time", 30)
            
            remaining_time = max(0, int(wait_time - elapsed_time))
            self.current_stage = f"階段E: BOSS檢測中 ({remaining_time}秒後切換頻道)"
            self.update_status()
            
            if elapsed_time >= wait_time:
                self.boss_check_start_time = time.time()
                return "F"
        
        time.sleep(1)
        return "E"  # 繼續檢測
    
    def stage_f(self):
        """階段F: 立即執行頻道切換，不等待任何條件"""
        print("階段F: 開始執行頻道切換")
        self.current_stage = "階段F: 執行頻道切換..."
        self.update_status()
        
        # 直接執行頻道切換，不進行任何畫面檢測
        channel_positions = self.config["click_positions"]["channel"]
        
        # 檢查頻道切換點位是否已設定
        if not channel_positions or len(channel_positions) < 4:
            self.current_stage = "階段F: 未設定頻道切換點位，需要設定4個點位"
            self.update_status()
            time.sleep(2)
            return "F"
        
        # 檢查前4個點位是否都已設定
        if not all(channel_positions[i] for i in range(4)):
            self.current_stage = "階段F: 頻道切換點位不完整，請確認已設定點位1-4"
            self.update_status()
            time.sleep(2)
            return "F"
        
        # 立即執行所有4個點位的點擊
        self.current_stage = "階段F: 立即執行4個點位點擊"
        self.update_status()
        
        try:
            # 依序執行所有點位
            for i in range(4):
                if channel_positions[i] and self.is_running and not self.is_paused:
                    print(f"階段F: 點擊點位{i+1} ({channel_positions[i][0]}, {channel_positions[i][1]})")
                    pyautogui.click(channel_positions[i][0], channel_positions[i][1])
                    time.sleep(1)
            
            # 頻道切換完成，重置BOSS檢測計時器
            if hasattr(self, 'boss_check_start_time'):
                delattr(self, 'boss_check_start_time')
            
            self.current_stage = "階段F: 頻道切換完成"
            self.update_status()
            print("階段F: 所有點位點擊完成，返回階段A")
            time.sleep(2)
            return "A"  # 回到階段A檢查頻道切換結果
            
        except Exception as e:
            print(f"階段F點擊錯誤: {e}")
            self.current_stage = f"階段F: 點擊錯誤 - {str(e)}"
            self.update_status()
            time.sleep(2)
            return "F"
        if "F" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段F（頻道切換目標畫面）
            if self.detect_stage_match("F"):
                self.current_stage = "階段F: ✓ 檢測到頻道切換目標畫面，執行完成點擊"
                self.update_status()
                
                # 已達到目標畫面，執行點位3和4
                channel_positions = self.config["click_positions"]["channel"]
                if len(channel_positions) >= 4:
                    # 點擊第3個點位
                    if channel_positions[2] and self.is_running and not self.is_paused:
                        print(f"階段F: 點擊點位3 ({channel_positions[2][0]}, {channel_positions[2][1]})")
                        pyautogui.click(channel_positions[2][0], channel_positions[2][1])
                        time.sleep(1)
                    
                    # 點擊第4個點位
                    if channel_positions[3] and self.is_running and not self.is_paused:
                        print(f"階段F: 點擊點位4 ({channel_positions[3][0]}, {channel_positions[3][1]})")
                        pyautogui.click(channel_positions[3][0], channel_positions[3][1])
                        time.sleep(1)
                
                # 頻道切換完成，重置BOSS檢測計時器
                if hasattr(self, 'boss_check_start_time'):
                    delattr(self, 'boss_check_start_time')
                
                return "A"  # 回到階段A檢查頻道切換結果
            else:
                # 檢查是否還在上個階段（階段E）
                if "E" in self.stage_screenshots and self.detect_stage_match("E"):
                    self.current_stage = "階段F: 檢測到仍在遊戲內畫面，等待進入頻道切換"
                    self.update_status()
                    # 還在遊戲內，等待進入頻道切換界面
                    time.sleep(1)
                    return "F"
                else:
                    # 還沒達到目標畫面，執行點位1和2
                    self.current_stage = "階段F: 執行頻道切換點位1和2"
                    self.update_status()
                    
                    channel_positions = self.config["click_positions"]["channel"]
                    if len(channel_positions) >= 2:
                        # 點擊第1個點位
                        if channel_positions[0] and self.is_running and not self.is_paused:
                            print(f"階段F: 點擊點位1 ({channel_positions[0][0]}, {channel_positions[0][1]})")
                            pyautogui.click(channel_positions[0][0], channel_positions[0][1])
                            time.sleep(1)
                        
                        # 點擊第2個點位
                        if channel_positions[1] and self.is_running and not self.is_paused:
                            print(f"階段F: 點擊點位2 ({channel_positions[1][0]}, {channel_positions[1][1]})")
                            pyautogui.click(channel_positions[1][0], channel_positions[1][1])
                            time.sleep(1)
        else:
            # 沒有設定截圖，執行完整的頻道切換流程
            self.current_stage = "階段F: 未設定參考畫面，執行完整頻道切換"
            self.update_status()
            
            channel_positions = self.config["click_positions"]["channel"]
            if len(channel_positions) >= 4:
                # 依序點擊所有4個點位
                for i, pos in enumerate(channel_positions):
                    if pos and self.is_running and not self.is_paused:
                        print(f"階段F: 點擊點位{i+1} ({pos[0]}, {pos[1]})")
                        pyautogui.click(pos[0], pos[1])
                        time.sleep(1)
                
                # 頻道切換完成，重置BOSS檢測計時器
                if hasattr(self, 'boss_check_start_time'):
                    delattr(self, 'boss_check_start_time')
                
                return "A"  # 回到階段A檢查頻道切換結果
        
        return "F"  # 繼續在階段F，直到檢測到目標畫面
    
    def detect_boss(self):
        """檢測王怪"""
        if not self.config["detection_area"]:
            return False
        
        try:
            # 截圖檢測區域
            x1, y1, x2, y2 = self.config["detection_area"]
            with mss.mss() as sct:
                monitor = {"top": y1, "left": x1, "width": x2-x1, "height": y2-y1}
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                img_array = np.array(img)
            
            # 檢測目標顏色
            target_color = np.array(self.config["target_color"])
            color_diff = np.abs(img_array - target_color)
            color_distance = np.sum(color_diff, axis=2)
            
            # 使用設定的顏色容差
            color_tolerance = self.config.get("color_tolerance", 50)
            matching_pixels = np.sum(color_distance < color_tolerance)
            
            return matching_pixels > self.config["color_threshold"]
        except Exception as e:
            print(f"王怪檢測錯誤: {e}")
            return False
    
    def detect_stage_match(self, stage_key):
        """檢測當前畫面是否匹配指定階段"""
        if stage_key not in self.stage_screenshots:
            return False
        
        try:
            # 截取當前畫面
            current_screenshot = self.take_area_screenshot(self.config["detection_area"])
            
            # 取得目標階段截圖
            target_screenshot = self.stage_screenshots[stage_key]
            
            # 計算相似度
            similarity = self.calculate_image_similarity(current_screenshot, target_screenshot)
            
            # 從設定中取得相似度閾值
            threshold_percent = self.config.get("stage_similarity_threshold", 80)
            threshold = threshold_percent / 100.0  # 轉換為0-1範圍
            
            # 除錯訊息
            print(f"階段{stage_key}匹配檢測: 相似度{similarity:.3f}, 閾值{threshold:.3f}, 匹配:{similarity > threshold}")
            
            return similarity > threshold
        except Exception as e:
            print(f"階段匹配檢測錯誤: {e}")
            return False
    
    def calculate_image_similarity(self, img1, img2):
        """計算兩張圖片的相似度"""
        try:
            # 調整大小以匹配
            h1, w1 = img1.shape[:2]
            h2, w2 = img2.shape[:2]
            
            if h1 != h2 or w1 != w2:
                img2 = cv2.resize(img2, (w1, h1))
            
            # 轉換為灰階
            gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
            
            # 計算結構相似性
            from skimage.metrics import structural_similarity as ssim
            similarity = ssim(gray1, gray2)
            
            return similarity
        except:
            # 如果沒有skimage，使用簡單的像素比較
            try:
                diff = cv2.absdiff(img1, img2)
                total_pixels = diff.size
                different_pixels = np.count_nonzero(diff > 30)
                similarity = 1 - (different_pixels / total_pixels)
                return similarity
            except:
                return 0
    
    def save_config(self):
        """儲存設定"""
        self.config["telegram_chat_id"] = self.chat_id_entry.get().strip()
        self.config["color_threshold"] = int(self.threshold_entry.get())
        self.config["color_tolerance"] = int(self.color_tolerance_entry.get())
        self.config["boss_wait_time"] = int(self.boss_wait_entry.get())
        self.config["stage_similarity_threshold"] = int(self.stage_similarity_entry.get())
        # 階段超時設定（轉換分鐘為秒）
        timeout_minutes = int(self.stage_timeout_entry.get())
        self.config["stage_timeout_seconds"] = timeout_minutes * 60
        
        # 儲存階段截圖
        self.save_stage_screenshots()
        
        # 儲存當機檢測截圖
        self.save_crash_screenshots()
        
        # 儲存UI狀態
        self.save_ui_state()
        
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        
        messagebox.showinfo("成功", "設定已儲存")
    
    def save_stage_screenshots(self):
        """儲存階段截圖到檔案"""
        import os
        
        # 建立截圖資料夾
        if not os.path.exists("stage_screenshots"):
            os.makedirs("stage_screenshots")
        
        # 儲存每個階段的截圖
        for stage_key, screenshot in self.stage_screenshots.items():
            try:
                # 轉換為PIL圖片並儲存
                pil_img = Image.fromarray(screenshot)
                pil_img.save(f"stage_screenshots/stage_{stage_key}.png")
                print(f"已儲存階段 {stage_key} 截圖")
            except Exception as e:
                print(f"儲存階段 {stage_key} 截圖失敗: {e}")
    
    def save_crash_screenshots(self):
        """儲存當機檢測截圖到檔案"""
        import os
        
        # 建立截圖資料夾
        if not os.path.exists("crash_screenshots"):
            os.makedirs("crash_screenshots")
        
        # 儲存每個當機類型的截圖
        for crash_key, screenshot in self.crash_screenshots.items():
            try:
                # 轉換為PIL圖片並儲存
                pil_img = Image.fromarray(screenshot)
                pil_img.save(f"crash_screenshots/crash_{crash_key}.png")
                print(f"已儲存當機檢測 {crash_key} 截圖")
            except Exception as e:
                print(f"儲存當機檢測 {crash_key} 截圖失敗: {e}")
    
    def load_config(self):
        """載入設定"""
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
            
            # 載入階段截圖
            self.load_stage_screenshots()
            
            # 載入當機檢測截圖
            self.load_crash_screenshots()
        except Exception as e:
            print(f"載入設定失敗: {e}")
    
    def load_stage_screenshots(self):
        """載入階段截圖"""
        import os
        
        if not os.path.exists("stage_screenshots"):
            return
        
        stages = ["A", "C", "D", "E", "F"]
        for stage_key in stages:
            screenshot_path = f"stage_screenshots/stage_{stage_key}.png"
            if os.path.exists(screenshot_path):
                try:
                    # 載入圖片並轉換為numpy陣列
                    pil_img = Image.open(screenshot_path)
                    screenshot = np.array(pil_img)
                    self.stage_screenshots[stage_key] = screenshot
                    print(f"已載入階段 {stage_key} 截圖")
                except Exception as e:
                    print(f"載入階段 {stage_key} 截圖失敗: {e}")
    
    def load_crash_screenshots(self):
        """載入當機檢測截圖"""
        import os
        
        if not os.path.exists("crash_screenshots"):
            return
        
        crash_types = ["disconnect", "error", "maintenance", "timeout"]
        for crash_key in crash_types:
            screenshot_path = f"crash_screenshots/crash_{crash_key}.png"
            if os.path.exists(screenshot_path):
                try:
                    # 載入圖片並轉換為numpy陣列
                    pil_img = Image.open(screenshot_path)
                    screenshot = np.array(pil_img)
                    self.crash_screenshots[crash_key] = screenshot
                    print(f"已載入當機檢測 {crash_key} 截圖")
                except Exception as e:
                    print(f"載入當機檢測 {crash_key} 截圖失敗: {e}")
    
    def save_ui_state(self):
        """儲存UI狀態"""
        self.config["section_collapsed"] = self.section_collapsed
    
    def show_stage_preview(self, stage_key):
        """顯示階段截圖預覽視窗"""
        if stage_key not in self.stage_screenshots:
            return
        
        # 創建預覽視窗
        preview_window = tk.Toplevel(self.root)
        preview_window.title(f"階段 {stage_key} 預覽")
        preview_window.transient(self.root)
        preview_window.grab_set()
        
        # 取得截圖
        screenshot = self.stage_screenshots[stage_key]
        
        # 計算適當的顯示大小（最大800x600）
        max_width, max_height = 800, 600
        h, w = screenshot.shape[:2]
        
        # 計算縮放比例
        scale = min(max_width/w, max_height/h, 1.0)  # 不放大，只縮小
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # 縮放圖片
        if scale < 1.0:
            resized_img = cv2.resize(screenshot, (new_w, new_h))
        else:
            resized_img = screenshot
        
        # 轉換為PhotoImage
        pil_img = Image.fromarray(resized_img)
        photo = ImageTk.PhotoImage(pil_img)
        
        # 設定視窗大小
        preview_window.geometry(f"{new_w + 40}x{new_h + 80}")
        
        # 階段資訊
        stage_names = {
            "A": "頻道切換成功畫面",
            "C": "登入畫面",
            "D": "角色選擇畫面",
            "E": "遊戲內畫面",
            "F": "頻道切換目標畫面"
        }
        
        info_label = tk.Label(preview_window, text=f"階段 {stage_key}: {stage_names.get(stage_key, '未知階段')}", 
                             font=('Arial', 12, 'bold'))
        info_label.pack(pady=10)
        
        # 顯示圖片
        img_label = tk.Label(preview_window, image=photo)
        img_label.image = photo  # 保持引用
        img_label.pack(pady=5)
        
        # 按鈕框架
        btn_frame = tk.Frame(preview_window)
        btn_frame.pack(pady=10)
        
        # 重新設定按鈕
        tk.Button(btn_frame, text="重新設定", 
                 command=lambda: self.reset_and_close(preview_window, stage_key),
                 bg="orange", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        
        # 關閉按鈕
        tk.Button(btn_frame, text="關閉", 
                 command=preview_window.destroy,
                 bg="gray", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        
        # 居中顯示
        preview_window.update_idletasks()
        x = (preview_window.winfo_screenwidth() // 2) - (preview_window.winfo_width() // 2)
        y = (preview_window.winfo_screenheight() // 2) - (preview_window.winfo_height() // 2)
        preview_window.geometry(f"+{x}+{y}")
    
    def reset_and_close(self, window, stage_key):
        """重新設定階段並關閉預覽視窗"""
        window.destroy()
        self.set_stage_screenshot(stage_key)
    
    def reset_config(self):
        """重置設定"""
        if messagebox.askyesno("確認", "確定要重置所有設定嗎？"):
            self.config = {
                "telegram_chat_id": "",
                "telegram_bot_token": "8232088184:AAG2piqVAVbiBdKENJ8tsUlm8I4Zz2OmTV4",
                "detection_area": None,
                "channel_area": None,
                "target_color": (255, 0, 0),
                "color_threshold": 100,
                "detection_timeout": 30,
                "color_tolerance": 50,
                "boss_wait_time": 30,
                "stage_similarity_threshold": 80,
                "click_positions": {
                    "login": None,
                    "character": None,
                    "channel": []
                },
                "send_welcome_message": True,
                "stage_timeout_seconds": 300,
                "stage_timeout_enabled": True
            }
            self.chat_id_entry.delete(0, tk.END)
            self.threshold_entry.delete(0, tk.END)
            self.threshold_entry.insert(0, "100")
            self.color_tolerance_entry.delete(0, tk.END)
            self.color_tolerance_entry.insert(0, "50")
            self.boss_wait_entry.delete(0, tk.END)
            self.boss_wait_entry.insert(0, "30")
            self.stage_similarity_entry.delete(0, tk.END)
            self.stage_similarity_entry.insert(0, "80")
            self.stage_screenshots = {}
            
            # 刪除階段截圖檔案
            import os
            if os.path.exists("stage_screenshots"):
                for stage_key in ["A", "C", "D", "E", "F"]:
                    screenshot_path = f"stage_screenshots/stage_{stage_key}.png"
                    if os.path.exists(screenshot_path):
                        try:
                            os.remove(screenshot_path)
                        except:
                            pass
            
            self.update_position_labels()
            self.update_stage_labels()
            self.reset_position_buttons()
            messagebox.showinfo("完成", "設定已重置")
    
    def cancel_position_recording(self):
        """取消點位設定"""
        if self.position_recording_active:
            self.position_recording_active = False
            self.recording_position = None
            self.reset_position_buttons()
            messagebox.showinfo("已取消", "點位設定已取消")
    
    def __del__(self):
        """程式結束時停止滑鼠監聽"""
        if hasattr(self, 'mouse_listener') and self.mouse_listener:
            self.mouse_listener.stop()
    
    def set_stage_screenshot(self, stage_key):
        """設定階段截圖"""
        if self.is_running:
            messagebox.showerror("錯誤", "請先停止監控模式再設定階段")
            return
        
        self.setting_stage = stage_key
        
        # 所有階段都使用王怪檢測區域
        detection_area = self.config["detection_area"]
        area_name = "王怪檢測區域"
        
        if not detection_area:
            messagebox.showerror("設定錯誤", f"請先設定{area_name}")
            return
        
        # 截取當前畫面
        current_screenshot = self.take_area_screenshot(detection_area)
        
        # 顯示確認對話框
        stage_names = {
            "A": "頻道切換成功畫面",
            "C": "登入畫面",
            "D": "角色選擇畫面",
            "E": "遊戲內畫面",
            "F": "頻道切換目標畫面"
        }
        
        confirmed = self.show_stage_confirmation_dialog(current_screenshot, stage_key, stage_names[stage_key], area_name)
        
        if confirmed:
            # 儲存階段截圖
            self.stage_screenshots[stage_key] = current_screenshot
            self.update_stage_labels()
            messagebox.showinfo("設定完成", f"階段 {stage_key} 截圖已設定")
        
        self.setting_stage = None
    
    def show_stage_confirmation_dialog(self, screenshot, stage_key, stage_name, area_name):
        """顯示階段截圖確認對話框"""
        # 創建對話框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"設定階段 {stage_key} - {stage_name}")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 顯示截圖
        img_height = 400
        img_width = int(screenshot.shape[1] * img_height / screenshot.shape[0])
        
        # 調整圖片大小並顯示
        resized_img = cv2.resize(screenshot, (img_width, img_height))
        pil_img = Image.fromarray(resized_img)
        photo = ImageTk.PhotoImage(pil_img)
        
        img_label = tk.Label(dialog, image=photo)
        img_label.image = photo  # 保持引用
        img_label.pack(pady=10)
        
        # 說明文字
        info_text = f"設定階段 {stage_key}: {stage_name}\n\n"
        info_text += f"檢測區域: {area_name}\n\n"
        info_text += "確認此截圖是否代表這個階段？"
        info_label = tk.Label(dialog, text=info_text, font=('Arial', 12))
        info_label.pack(pady=10)
        
        # 確認結果
        result = {"confirmed": False}
        
        def confirm():
            result["confirmed"] = True
            dialog.destroy()
        
        def cancel():
            result["confirmed"] = False
            dialog.destroy()
        
        # 按鈕
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="確認設定", command=confirm, bg="green", fg="white", width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=cancel, bg="red", fg="white", width=12).pack(side=tk.LEFT, padx=10)
        
        # 等待使用者選擇
        dialog.wait_window()
        
        return result["confirmed"]
    
    def take_area_screenshot(self, area_coords):
        """截取指定區域"""
        if not area_coords:
            # 如果沒有區域設定，截取全螢幕
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # 主螢幕
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return np.array(img)
        
        x1, y1, x2, y2 = area_coords
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2-x1, "height": y2-y1}
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return np.array(img)
    
    def toggle_recording(self):
        """開始/停止錄製"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """開始錄製模式"""
        if self.is_running:
            messagebox.showerror("錯誤", "請先停止監控模式再開始錄製")
            return
        
        # 檢查是否已設定檢測區域
        if not self.config["detection_area"] or not self.config["channel_area"]:
            result = messagebox.askyesno("需要設定檢測區域", 
                "錄製功能需要先設定檢測區域：\n\n"
                "• 王怪檢測區域 (用於階段 A-E)\n"
                "• 頻道檢測區域 (用於階段 F)\n\n"
                "是否現在設定？")
            if result:
                if not self.config["detection_area"]:
                    messagebox.showinfo("設定區域", "請先設定王怪檢測區域")
                    self.set_detection_area()
                if not self.config["channel_area"]:
                    messagebox.showinfo("設定區域", "請設定頻道檢測區域")
                    self.set_channel_area()
                
                # 再次檢查
                if not self.config["detection_area"] or not self.config["channel_area"]:
                    messagebox.showerror("設定不完整", "需要設定兩個檢測區域才能開始錄製")
                    return
            else:
                return
        
        # 確認開始錄製
        result = messagebox.askyesno("開始錄製", 
            "錄製模式將幫助您確認各階段轉換：\n\n"
            "1. 偵測指定區域的畫面變化\n"
            "2. 彈出截圖確認對話框\n"
            "3. 確認各階段轉換時機\n"
            "4. 熟悉系統運作流程\n\n"
            "請確保遊戲在登入畫面載入階段，是否開始錄製？")
        
        if not result:
            return
        
        # 初始化錄製狀態
        self.is_recording = True
        self.recording_stage = "A"
        self.stage_screenshots = {}
        self.recording_start_time = time.time()
        
        # 更新UI
        self.record_btn.config(text="停止錄製", style="Accent.TButton")
        self.start_stop_btn.config(state="disabled")
        self.current_stage = "錄製模式 - 階段A"
        self.update_status()
        
        # 開始錄製執行緒
        self.recording_thread = threading.Thread(target=self.recording_loop, daemon=True)
        self.recording_thread.start()
        
        messagebox.showinfo("錄製開始", "請開始進行遊戲登入流程\n系統將自動偵測畫面變化並詢問階段確認")
    
    def stop_recording(self):
        """停止錄製模式"""
        self.is_recording = False
        
        # 更新UI
        self.record_btn.config(text="開始錄製", style="TButton")
        self.start_stop_btn.config(state="normal")
        self.current_stage = "錄製完成"
        self.update_status()
        
        # 顯示錄製結果
        self.show_recording_summary()
    
    
    def recording_loop(self):
        """錄製主循環 - 偵測指定區域的畫面變化"""
        screenshot_interval = 1.0  # 每秒截圖
        change_threshold = 0.15  # 15%的畫面變化視為階段轉換
        
        while self.is_recording:
            try:
                # 根據當前階段選擇檢測區域
                if self.recording_stage in ["A", "B", "C", "D", "E"]:
                    # 階段A-E使用王怪檢測區域
                    detection_area = self.config["detection_area"]
                    area_name = "王怪檢測區域"
                else:
                    # 階段F使用頻道檢測區域
                    detection_area = self.config["channel_area"]
                    area_name = "頻道檢測區域"
                
                # 截取指定區域
                current_screenshot = self.take_area_screenshot(detection_area)
                
                if self.last_screenshot is not None:
                    # 計算畫面變化程度
                    change_ratio = self.calculate_screen_change(self.last_screenshot, current_screenshot)
                    
                    if change_ratio > change_threshold:
                        # 發現顯著畫面變化，詢問使用者
                        stage_confirmed = self.ask_stage_confirmation(current_screenshot, change_ratio, area_name)
                        
                        if stage_confirmed:
                            # 儲存階段截圖並進入下一階段
                            self.stage_screenshots[self.recording_stage] = current_screenshot
                            self.advance_recording_stage()
                
                self.last_screenshot = current_screenshot
                time.sleep(screenshot_interval)
                
            except Exception as e:
                print(f"錄製循環錯誤: {e}")
                time.sleep(1)
    
    def take_full_screenshot(self):
        """截取全螢幕"""
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # 主螢幕
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return np.array(img)
    
    def take_area_screenshot(self, area_coords):
        """截取指定區域"""
        if not area_coords:
            return self.take_full_screenshot()
        
        x1, y1, x2, y2 = area_coords
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2-x1, "height": y2-y1}
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return np.array(img)
    
    def calculate_screen_change(self, img1, img2):
        """計算兩張圖片的變化程度"""
        try:
            # 調整大小以加速比較
            h1, w1 = img1.shape[:2]
            h2, w2 = img2.shape[:2]
            
            if h1 != h2 or w1 != w2:
                img2 = cv2.resize(img2, (w1, h1))
            
            # 轉換為灰階
            gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
            
            # 計算差異
            diff = cv2.absdiff(gray1, gray2)
            
            # 計算變化像素比例
            total_pixels = diff.size
            changed_pixels = np.count_nonzero(diff > 30)  # 閾值30
            
            return changed_pixels / total_pixels
        except:
            return 0
    
    def ask_stage_confirmation(self, screenshot, change_ratio, area_name="檢測區域"):
        """詢問使用者是否確認階段轉換"""
        # 暫停錄製循環
        temp_recording = self.is_recording
        self.is_recording = False
        
        # 創建確認對話框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"階段確認 - {self.recording_stage}")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 顯示截圖
        img_height = 400
        img_width = int(screenshot.shape[1] * img_height / screenshot.shape[0])
        
        # 調整圖片大小並顯示
        resized_img = cv2.resize(screenshot, (img_width, img_height))
        pil_img = Image.fromarray(resized_img)
        photo = ImageTk.PhotoImage(pil_img)
        
        img_label = tk.Label(dialog, image=photo)
        img_label.image = photo  # 保持引用
        img_label.pack(pady=10)
        
        # 說明文字
        stage_names = {
            "A": "登入畫面載入中",
            "B": "黑畫面Loading", 
            "C": "登入畫面",
            "D": "角色選擇畫面",
            "E": "遊戲內畫面"
        }
        
        info_text = f"偵測到{area_name}畫面變化 ({change_ratio:.1%})\n\n是否確認進入階段 {self.recording_stage}: {stage_names.get(self.recording_stage, '未知階段')}？"
        info_label = tk.Label(dialog, text=info_text, font=('Arial', 12))
        info_label.pack(pady=10)
        
        # 確認結果
        result = {"confirmed": False}
        
        def confirm():
            result["confirmed"] = True
            dialog.destroy()
        
        def reject():
            result["confirmed"] = False
            dialog.destroy()
        
        # 按鈕
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="確認", command=confirm, bg="green", fg="white", width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=reject, bg="red", fg="white", width=10).pack(side=tk.LEFT, padx=10)
        
        # 等待使用者選擇
        dialog.wait_window()
        
        # 恢復錄製
        self.is_recording = temp_recording
        
        return result["confirmed"]
    
    def advance_recording_stage(self):
        """進入下一個錄製階段"""
        stage_order = ["A", "B", "C", "D", "E", "F"]
        current_index = stage_order.index(self.recording_stage)
        
        if current_index < len(stage_order) - 1:
            self.recording_stage = stage_order[current_index + 1]
            self.current_stage = f"錄製模式 - 階段{self.recording_stage}"
            self.update_status()
            
            if self.recording_stage == "F":
                # 到達最後階段，準備結束錄製
                messagebox.showinfo("錄製進度", "已進入最後階段 - 頻道切換階段")
        else:
            # 錄製完成
            self.stop_recording()
    
    def show_recording_summary(self):
        """顯示錄製摘要"""
        result_text = f"錄製完成！\n\n"
        result_text += f"• 完成了 {len(self.stage_screenshots)} 個階段確認\n"
        result_text += f"• 熟悉了系統各階段轉換流程\n\n"
        result_text += "現在您可以：\n"
        result_text += "1. 使用各點位設定按鈕設定點擊位置\n"
        result_text += "2. 設定檢測顏色和閾值\n"
        result_text += "3. 開始使用自動監控功能！"
        
        messagebox.showinfo("錄製完成", result_text)
    
    def run(self):
        """啟動應用程式"""
        self.root.mainloop()

    def load_window_geometry(self):
        """載入視窗位置和大小"""
        try:
            # 從設定中載入視窗幾何
            geometry = self.config.get("window_geometry", "800x600+100+100")
            self.root.geometry(geometry)
            print(f"載入視窗位置: {geometry}")
        except Exception as e:
            print(f"載入視窗位置失敗: {e}")
            # 使用預設值
            self.root.geometry("800x600+100+100")
    
    def save_window_geometry(self):
        """儲存當前視窗位置和大小"""
        try:
            # 取得當前視窗幾何
            geometry = self.root.geometry()
            self.config["window_geometry"] = geometry
            print(f"儲存視窗位置: {geometry}")
        except Exception as e:
            print(f"儲存視窗位置失敗: {e}")
    
    def on_closing(self):
        """視窗關閉事件處理"""
        try:
            # 停止所有運行中的執行緒
            if self.is_running:
                self.is_running = False
                self.is_paused = False
            
            # 儲存視窗位置
            self.save_window_geometry()
            
            # 儲存設定
            self.save_config()
            
            # 停止滑鼠監聽器
            if hasattr(self, 'mouse_listener'):
                try:
                    self.mouse_listener.stop()
                except:
                    pass
            
            # 停止滴管取色監聽器
            if hasattr(self, 'eyedropper_mouse_listener'):
                try:
                    self.eyedropper_mouse_listener.stop()
                except:
                    pass
            
            # 停止Telegram Bot監聽
            if hasattr(self, 'telegram_bot'):
                try:
                    self.telegram_bot.stop_listener()
                except:
                    pass
            
            print("程式正常關閉")
            
        except Exception as e:
            print(f"關閉程式時發生錯誤: {e}")
        finally:
            # 銷毀視窗
            self.root.destroy()

if __name__ == "__main__":
    app = GameMonitor()
    app.run()