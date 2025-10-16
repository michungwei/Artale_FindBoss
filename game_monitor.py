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
import requests
from PIL import Image, ImageTk
import cv2
import numpy as np
import keyboard
import mss
import os

class GameMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Artale找Boss神器")
        self.root.geometry("800x600")
        
        # 系統狀態
        self.is_running = False
        self.is_paused = False
        self.current_stage = "待機"
        self.monitoring_thread = None
        
        # 階段設定狀態
        self.stage_screenshots = {}
        self.setting_stage = None
        
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
            }
        }
        
        self.load_config()
        self.create_widgets()
        self.setup_hotkeys()
        
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
        
        # BOSS訊息判斷設定
        self.create_collapsible_section(main_frame, "color", "BOSS訊息判斷設定", 5, self.create_color_widgets)
        
        # 點位設定
        self.create_collapsible_section(main_frame, "position", "點位設定", 6, self.create_position_widgets)
        
        # 底部按鈕
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=7, column=0, columnspan=2, pady=10)
        
        ttk.Button(bottom_frame, text="儲存設定", command=self.save_config).grid(row=0, column=0, padx=5)
        ttk.Button(bottom_frame, text="重新設定", command=self.reset_config).grid(row=0, column=1, padx=5)
        ttk.Button(bottom_frame, text="取消點位設定", command=self.cancel_position_recording).grid(row=0, column=2, padx=5)
        
        self.update_position_labels()
        self.update_area_labels()
        self.update_stage_labels()
    
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
            row = i // 2
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
        tk.Label(parent, text="設定顏色:", font=('Arial', 8)).grid(row=5, column=0, sticky=tk.W)
        tk.Label(parent, text="滑鼠顏色:", font=('Arial', 8)).grid(row=5, column=1, sticky=tk.W)
        
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
        
        # 顏色資訊顯示
        ttk.Label(parent, text="RGB值:").grid(row=4, column=0, sticky=tk.W)
        self.rgb_label = ttk.Label(parent, text=f"({self.config['target_color'][0]}, {self.config['target_color'][1]}, {self.config['target_color'][2]})")
        self.rgb_label.grid(row=4, column=1, sticky=tk.W, padx=5)
    
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
        
        messagebox.showinfo("開始測試", "將在10秒內檢測BOSS訊息\n請確保遊戲畫面可見")
        
        # 啟動測試執行緒
        self.boss_test_thread = threading.Thread(target=self.run_boss_test, daemon=True)
        self.boss_test_thread.start()
    
    def run_boss_test(self):
        """執行BOSS檢測測試"""
        test_duration = 10  # 測試10秒
        check_interval = 0.5  # 每0.5秒檢測一次
        start_time = time.time()
        boss_detected = False
        
        try:
            while time.time() - start_time < test_duration and self.boss_test_active:
                # 執行BOSS檢測
                if self.detect_boss():
                    boss_detected = True
                    break
                
                time.sleep(check_interval)
            
            # 更新UI必須在主執行緒中
            if boss_detected:
                self.root.after(0, lambda: self.show_test_result(True))
            else:
                self.root.after(0, lambda: self.show_test_result(False))
                
        except Exception as e:
            print(f"測試過程發生錯誤: {e}")
            self.root.after(0, lambda: self.show_test_result(False, str(e)))
        
        # 重置測試狀態
        self.boss_test_active = False
        self.root.after(0, self.reset_boss_test_button)
    
    def show_test_result(self, detected, error_msg=None):
        """顯示測試結果"""
        if error_msg:
            messagebox.showerror("測試錯誤", f"測試過程發生錯誤:\n{error_msg}")
        elif detected:
            # 取得當前設定值顯示
            timestamp = datetime.now().strftime("%H:%M:%S")
            result_msg = f"✅ 偵測到BOSS！\n\n"
            result_msg += f"時間: {timestamp}\n"
            result_msg += f"目標顏色: RGB{self.config['target_color']}\n"
            result_msg += f"顏色容差: {self.config['color_tolerance']}\n"
            result_msg += f"像素閾值: {self.config['color_threshold']}"
            
            messagebox.showinfo("測試結果", result_msg)
        else:
            result_msg = f"❌ 未偵測到BOSS\n\n"
            result_msg += f"測試時間: 10秒\n"
            result_msg += f"目標顏色: RGB{self.config['target_color']}\n"
            result_msg += f"顏色容差: {self.config['color_tolerance']}\n"
            result_msg += f"像素閾值: {self.config['color_threshold']}\n\n"
            result_msg += "建議:\n"
            result_msg += "• 檢查目標顏色是否正確\n"
            result_msg += "• 調整顏色容差 (增加容差值)\n"
            result_msg += "• 降低像素閾值\n"
            result_msg += "• 確認檢測區域設定正確"
            
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
        self.status_label.config(text=f"目前狀態: {self.current_stage}")
    
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
        
        stage = "C"  # 從階段C開始（登入畫面）
        
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
                
                time.sleep(1)  # 基本延遲
            except Exception as e:
                print(f"監控循環錯誤: {e}")
                time.sleep(1)
    
    def stage_a(self):
        """階段A: 頻道切換成功確認"""
        self.current_stage = "階段A: 頻道切換成功確認"
        self.update_status()
        
        # 檢查是否有階段A的截圖設定
        if "A" in self.stage_screenshots:
            # 檢測當前畫面是否匹配階段A
            if self.detect_stage_match("A"):
                # 匹配成功，進入下一階段
                return "C"
        
        # 沒有設定或不匹配，直接進入登入階段
        time.sleep(1)
        return "C"
    
    def stage_c(self):
        """階段C: 登入畫面"""
        self.current_stage = "階段C: 登入畫面"
        self.update_status()
        
        login_pos = self.config["click_positions"]["login"]
        if login_pos:
            pyautogui.click(login_pos[0], login_pos[1])
            time.sleep(2)
        
        return "D"
    
    def stage_d(self):
        """階段D: 選擇角色畫面"""
        self.current_stage = "階段D: 角色選擇"
        self.update_status()
        
        char_pos = self.config["click_positions"]["character"]
        if char_pos:
            pyautogui.click(char_pos[0], char_pos[1])
            time.sleep(2)
        
        return "E"
    
    def stage_e(self):
        """階段E: 遊戲內王怪檢測"""
        self.current_stage = "階段E: 王怪檢測中"
        self.update_status()
        
        # 檢測王怪
        if self.detect_boss():
            # 發送通知並暫停
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"BOSS出現！\n時間: {timestamp}"
            
            self.send_telegram_message(self.config["telegram_chat_id"], message)
            
            # 自動暫停，等待使用者繼續
            self.is_paused = True
            self.pause_continue_btn.config(text="繼續", style="Accent.TButton")  # 突出樣式
            self.current_stage = "檢測到BOSS - 請打完後點繼續"
            self.update_status()
            
            # 等待使用者點繼續
            while self.is_paused and self.is_running:
                time.sleep(0.1)
            
            self.pause_continue_btn.config(style="TButton")  # 恢復一般樣式
            return "F"
        
        # 超時檢查
        time.sleep(1)
        return "E"  # 繼續檢測
    
    def stage_f(self):
        """階段F: 切換頻道"""
        self.current_stage = "階段F: 切換頻道"
        self.update_status()
        
        # 檢查是否已達到階段F的目標畫面
        if "F" in self.stage_screenshots:
            if self.detect_stage_match("F"):
                # 已達到目標畫面，執行點位3和4
                channel_positions = self.config["click_positions"]["channel"]
                if len(channel_positions) >= 4:
                    # 點擊第3個點位
                    if channel_positions[2] and self.is_running and not self.is_paused:
                        pyautogui.click(channel_positions[2][0], channel_positions[2][1])
                        time.sleep(1)
                    
                    # 點擊第4個點位
                    if channel_positions[3] and self.is_running and not self.is_paused:
                        pyautogui.click(channel_positions[3][0], channel_positions[3][1])
                        time.sleep(1)
                
                return "A"  # 回到階段A確認切換成功
        
        # 還沒達到目標畫面，執行點位1和2
        channel_positions = self.config["click_positions"]["channel"]
        if len(channel_positions) >= 2:
            # 點擊第1個點位
            if channel_positions[0] and self.is_running and not self.is_paused:
                pyautogui.click(channel_positions[0][0], channel_positions[0][1])
                time.sleep(1)
            
            # 點擊第2個點位
            if channel_positions[1] and self.is_running and not self.is_paused:
                pyautogui.click(channel_positions[1][0], channel_positions[1][1])
                time.sleep(1)
        
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
            
            # 相似度閾值，可以調整
            threshold = 0.8  # 80%相似度
            
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
        
        # 儲存階段截圖
        self.save_stage_screenshots()
        
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
    
    def load_config(self):
        """載入設定"""
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
            
            # 載入階段截圖
            self.load_stage_screenshots()
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
                "click_positions": {
                    "login": None,
                    "character": None,
                    "channel": []
                }
            }
            self.chat_id_entry.delete(0, tk.END)
            self.threshold_entry.delete(0, tk.END)
            self.threshold_entry.insert(0, "100")
            self.color_tolerance_entry.delete(0, tk.END)
            self.color_tolerance_entry.insert(0, "50")
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

if __name__ == "__main__":
    app = GameMonitor()
    app.run()