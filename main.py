import os
import glob  # हे नवीन ॲड करा
os.environ['KIVY_GL_BACKEND'] = 'angle_sdl2'

import threading
import time
import asyncio
import edge_tts
import sqlite3
import random
import speech_recognition as sr
from gtts import gTTS
from kivy.core.audio import SoundLoader
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.video import Video
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.screenmanager import ScreenManager, Screen
from groq import Groq
from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDIcon
from kivy.lang import Builder

# --- MOBILE APP SIZE & THEME ---
Window.size = (380, 680)
Window.clearcolor = (0.02, 0.04, 0.1, 1)

# API KEY
GROQ_API_KEY = "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"

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('english_teacher.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_profile 
                 (id INTEGER PRIMARY KEY, name TEXT, age_group TEXT, level TEXT)''')
    
    # XP आणि Messages सेव्ह करण्यासाठी
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress 
                 (id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0, xp INTEGER DEFAULT 0)''')
    
    c.execute("SELECT * FROM user_progress WHERE id=1")
    if not c.fetchone():
        c.execute("INSERT INTO user_progress (id, total_messages, xp) VALUES (1, 0, 0)")
    else:
        # जुन्या युजर्ससाठी XP कॉलम ॲड करण्यासाठी (Error टाळण्यासाठी)
        try:
            c.execute("ALTER TABLE user_progress ADD COLUMN xp INTEGER DEFAULT 0")
        except:
            pass
            
    conn.commit()
    conn.close()

def get_user_profile():
    conn = sqlite3.connect('english_teacher.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_profile LIMIT 1")
    user = c.fetchone()
    conn.close()
    return user

def save_user_profile(name, age_group, level):
    conn = sqlite3.connect('english_teacher.db')
    c = conn.cursor()
    c.execute("INSERT INTO user_profile (name, age_group, level) VALUES (?, ?, ?)", (name, age_group, level))
    conn.commit()
    conn.close()

# मेसेज पाठवल्यावर XP वाढवण्यासाठी
def update_progress():
    conn = sqlite3.connect('english_teacher.db')
    c = conn.cursor()
    # 1 मेसेज = 10 XP
    c.execute("UPDATE user_progress SET total_messages = total_messages + 1, xp = xp + 10 WHERE id=1")
    conn.commit()
    conn.close()

def get_progress():
    conn = sqlite3.connect('english_teacher.db')
    c = conn.cursor()
    c.execute("SELECT total_messages, xp FROM user_progress WHERE id=1")
    res = c.fetchone()
    conn.close()
    # (Total Messages, XP) परत करेल
    return res if res else (0, 0)

# --- SMART ICON CLASSES ---
class SmartIconButton(ButtonBehavior, BoxLayout):
    def __init__(self, icon_path, fallback_text, text_color=(0, 0.8, 1, 1), **kwargs):
        super().__init__(orientation='vertical', padding=5, **kwargs)
        if os.path.exists(icon_path):
            self.add_widget(Image(source=icon_path, allow_stretch=True, keep_ratio=True))
        else:
            self.add_widget(Label(text=fallback_text, color=text_color, font_size=14, bold=True))

class NavItem(ButtonBehavior, BoxLayout):
    def __init__(self, icon_path, text, color, **kwargs):
        super().__init__(orientation='vertical', padding=2, **kwargs)
        if os.path.exists(icon_path):
            self.add_widget(Image(source=icon_path, allow_stretch=True, keep_ratio=True, size_hint_y=0.6))
        self.add_widget(Label(text=text, font_size=12, color=color, size_hint_y=0.4 if os.path.exists(icon_path) else 1))

class ChatBubble(BoxLayout):
    def __init__(self, text, sender, font_size=15, **kwargs): # Yahan font_size parameter add kiya
        super().__init__(orientation='horizontal', size_hint_y=None, padding=(10, 5), **kwargs)
        custom_font = 'Marathi.ttf' if os.path.exists('Marathi.ttf') else 'Roboto'
        
        self.lbl = Label(
            text=text, color=(1, 1, 1, 1), size_hint_y=None, 
            halign='left', valign='middle', padding=(15, 15), 
            font_size=font_size,  # Yahan hardcoded 15 nikal kar dynamic variable set kiya
            font_name=custom_font
        )
        self.lbl.bind(width=lambda s, w: s.setter('text_size')(s, (w, None)))
        self.lbl.bind(texture_size=self.lbl.setter('size'))
        
        self.bubble = BoxLayout(size_hint_x=0.85, size_hint_y=None)
        self.bubble.bind(minimum_height=self.bubble.setter('height'))
        self.bind(minimum_height=self.setter('height'))
        self.bubble.add_widget(self.lbl)
        
        with self.bubble.canvas.before:
            if sender == 'user':
                Color(0, 0.5, 0.9, 1)
            else:
                Color(0.1, 0.15, 0.25, 1)
            self.rect = RoundedRectangle(radius=[15])
            self.bubble.bind(pos=self.update_rect, size=self.update_rect)

        if sender == 'user':
            self.add_widget(Label(size_hint_x=0.15))
            self.add_widget(self.bubble)
        else:
            self.add_widget(self.bubble)
            self.add_widget(Label(size_hint_x=0.15))

    def update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

# --- SCREEN 1: PROFILE SETUP ---
class ProfileScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # मराठी फॉन्ट लोड करण्यासाठी
        custom_font = 'Marathi.ttf' if os.path.exists('Marathi.ttf') else 'Roboto'
        
        # वयाचे आणि लेव्हलचे ऑप्शन्स
        self.age_options = ["Child (Under 18)", "Adult (18-50)", "Senior (50+)"]
        self.age_index = 1  # बाय डिफॉल्ट Adult दिसेल
        
        self.level_options = ["Absolute Beginner", "Intermediate", "Advanced"]
        self.level_index = 0 # बाय डिफॉल्ट Beginner दिसेल

        layout = BoxLayout(orientation='vertical', padding=30, spacing=20)
        
        layout.add_widget(Label(text="[b]Welcome to AI English[/b]", markup=True, font_size=24, color=(0, 0.8, 1, 1), size_hint_y=0.2))
        
        layout.add_widget(Label(text="Your Name:", font_size=16, halign="left", size_hint_y=None, height=30))
        self.name_input = TextInput(hint_text="Enter Name", multiline=False, size_hint_y=None, height=40)
        layout.add_widget(self.name_input)

        # Age Group Button (font_name ऍड केला आहे)
        layout.add_widget(Label(text="Age Group (बदलण्यासाठी क्लिक करा):", font_name=custom_font, font_size=16, halign="left", size_hint_y=None, height=30))
        self.age_btn = Button(text=self.age_options[self.age_index], size_hint_y=None, height=40, background_color=(0.1, 0.2, 0.4, 1))
        self.age_btn.bind(on_press=self.change_age)
        layout.add_widget(self.age_btn)

        # Level Button (font_name ऍड केला आहे)
        layout.add_widget(Label(text="English Level (बदलण्यासाठी क्लिक करा):", font_name=custom_font, font_size=16, halign="left", size_hint_y=None, height=30))
        self.level_btn = Button(text=self.level_options[self.level_index], size_hint_y=None, height=40, background_color=(0.1, 0.2, 0.4, 1))
        self.level_btn.bind(on_press=self.change_level)
        layout.add_widget(self.level_btn)

        # Spacer
        layout.add_widget(Label(size_hint_y=0.2))

        self.start_btn = Button(text="Start Learning", size_hint_y=None, height=50, background_color=(0, 0.6, 1, 1), bold=True)
        self.start_btn.bind(on_press=self.save_and_start)
        layout.add_widget(self.start_btn)
        
        self.add_widget(layout)

    def change_age(self, instance):
        self.age_index = (self.age_index + 1) % len(self.age_options)
        self.age_btn.text = self.age_options[self.age_index]

    def change_level(self, instance):
        self.level_index = (self.level_index + 1) % len(self.level_options)
        self.level_btn.text = self.level_options[self.level_index]

    def save_and_start(self, instance):
        user_name = self.name_input.text.strip()
        if not user_name:
            user_name = "Student"
        
        save_user_profile(user_name, self.age_btn.text, self.level_btn.text)
        
        self.manager.current = 'chat'
        
        # YAHAN CHANGE KIYA HAI: user_name ke sath age aur level bhi AI ko bhej rahe hain
        self.manager.get_screen('chat').initialize_ai(user_name, self.age_btn.text, self.level_btn.text)
# --- 2. NEW ALPHABET ADVENTURE SCREEN (INTEGRATED) ---
ALPHABET_KV = '''
<AlphabetScreen>:
    md_bg_color: [0.03, 0.05, 0.1, 1]

    AnchorLayout:
        anchor_x: 'center'
        anchor_y: 'center'

        MDCard:
            size_hint: None, None
            size: "360dp", "640dp"
            elevation: 4
            md_bg_color: [0.08, 0.11, 0.2, 1]
            radius: [25, 25, 25, 25]
            orientation: "vertical"
            padding: "16dp"
            spacing: "12dp"

            BoxLayout:
                size_hint_y: None
                height: "40dp"
                Label:
                    text: "Kids Voice Adventure"
                    font_size: "18sp"
                    bold: True
                    color: 1, 0.8, 0.2, 1

            MDCard:
                size_hint_y: None
                height: "80dp"
                md_bg_color: [0.12, 0.18, 0.3, 1]
                radius: [15, 15, 15, 15]
                padding: "10dp"
                
                Label:
                    id: robot_text
                    text: "Robot Friend:\\n'Bolo beta... A for Apple!'"
                    font_size: "16sp"
                    color: 0.8, 0.9, 1, 1
                    halign: 'center'

            MDCard:
                size_hint_y: None
                height: "230dp"
                md_bg_color: [0.05, 0.07, 0.12, 1]
                radius: [15, 15, 15, 15]
                
                Video:
                    id: my_video
                    source: 'apple_video.mp4'  
                    state: 'stop'
                    allow_stretch: True

            Label:
                text: "Fun Fact: Apple red color ka hota hai aur ise khane se hum strong bante hain!"
                font_size: "14sp"
                color: 0.4, 1, 0.6, 1
                halign: 'center'
                text_size: self.width, None

            Button:
                id: mic_btn
                text: "Tap & Speak 'A for Apple'"
                size_hint_x: 1
                size_hint_y: None
                height: "45dp"
                background_normal: ''
                background_color: 0.9, 0.3, 0.4, 1
                bold: True
                font_size: "16sp"
                on_release: root.start_listening()

            Button:
                text: "Back to Home"
                size_hint_x: 1
                size_hint_y: None
                height: "40dp"
                background_normal: ''
                background_color: 0, 0.5, 0.8, 1
                bold: True
                on_release: root.go_back()
'''
Builder.load_string(ALPHABET_KV)

class AlphabetScreen(Screen):
    def start_listening(self):
        self.ids.mic_btn.text = "Listening... Speak Now!"
        self.ids.mic_btn.background_color = (0.2, 0.8, 0.2, 1)
        self.ids.robot_text.text = "Robot is listening..."
        threading.Thread(target=self.listen_thread, daemon=True).start()

    def listen_thread(self):
        # Background noise aur mic check
        try:
            import speech_recognition as sr
        except ImportError:
            Clock.schedule_once(lambda dt: self.update_ui_message("Speech library install nahi hai!"))
            return

        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
                
            text = recognizer.recognize_google(audio).lower()
            
            if "apple" in text:
                Clock.schedule_once(lambda dt: self.play_success(text))
            else:
                Clock.schedule_once(lambda dt: self.play_retry(text))
                
        except sr.WaitTimeoutError:
            Clock.schedule_once(lambda dt: self.update_ui_message("Koi aawaz nahi aayi, phir try karein!"))
        except sr.UnknownValueError:
            Clock.schedule_once(lambda dt: self.update_ui_message("Samajh nahi aaya, phir try karein!"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_ui_message("Mic mein kuch issue hai!"))

    def play_success(self, text):
        self.ids.robot_text.text = f"Super! Aapne kaha: '{text}'"
        self.reset_button()
        self.ids.my_video.state = 'play'

    def play_retry(self, text):
        self.ids.robot_text.text = f"Aapne kaha: '{text}'\\nTry again! Bolo 'Apple'"
        self.reset_button()
        self.ids.my_video.state = 'stop'

    def update_ui_message(self, message):
        self.ids.robot_text.text = message
        self.reset_button()
        
    def reset_button(self):
        self.ids.mic_btn.text = "Tap & Speak 'A for Apple'"
        self.ids.mic_btn.background_color = (0.9, 0.3, 0.4, 1)

    def go_back(self):
        self.ids.my_video.state = 'stop'
        self.manager.current = 'chat'
# ----------------------------------------------------
# --- CUSTOM NEON GLASSMORPHIC CARD (FIXED ALIGNMENT & ICONS) ---
class NeonPracticeCard(ButtonBehavior, FloatLayout):
    def __init__(self, title, desc, icon_name, level, progress, glow_color, mode, callback, popup_ref, is_top_card=False, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 70 if is_top_card else 85  # साइज़ छोटी कर दी गई है
        self.mode = mode
        self.callback = callback
        self.popup_ref = popup_ref
        self.progress_val = progress

        with self.canvas.before:
            # 1. Glassmorphism Translucent Background
            Color(0.06, 0.08, 0.14, 0.85)
            self.bg_rect = RoundedRectangle(radius=[12])
            
            # 2. Glowing Neon Border
            Color(*glow_color)
            self.border_line = Line(width=1.2)
            
            # 3. Progress Bar Track (Background)
            Color(0.2, 0.2, 0.3, 1)
            self.prog_track = RoundedRectangle(radius=[2])
            
            # 4. Progress Bar Fill
            Color(*glow_color)
            self.prog_fill = RoundedRectangle(radius=[2])

        self.bind(pos=self.update_canvas, size=self.update_canvas)
        self.bind(on_release=self.on_card_release)

        # --- Vector Material Icons (No Emojis) ---
        icon_lbl = MDIcon(
            icon=icon_name, 
            font_size=32 if is_top_card else 38, 
            theme_text_color="Custom", 
            text_color=glow_color,  # आइकन का कलर कार्ड के बॉर्डर जैसा होगा
            pos_hint={'x': 0.04, 'center_y': 0.55}
        )
        self.add_widget(icon_lbl)
        
        # --- Title (Width फिक्स की ताकि बैज से न टकराए) ---
        title_lbl = Label(
            text=f"[b]{title}[/b]", markup=True, font_size=15 if is_top_card else 16, color=(1,1,1,1), 
            size_hint=(0.55, None), height=30, pos_hint={'x': 0.18, 'top': 0.92}, 
            halign="left", valign="middle"
        )
        title_lbl.bind(size=title_lbl.setter('text_size'))
        self.add_widget(title_lbl)

        # --- Description ---
        desc_lbl = Label(
            text=f"[color=A0B0C0]{desc}[/color]", markup=True, font_size=11, 
            size_hint=(0.55, None), height=20, pos_hint={'x': 0.18, 'top': 0.58}, 
            halign="left", valign="middle"
        )
        desc_lbl.bind(size=desc_lbl.setter('text_size'))
        self.add_widget(desc_lbl)

        # --- Level Badge (टॉप राइट कॉर्नर में सेट किया) ---
        badge_lbl = Label(
            text=f"[b]{level}[/b]", markup=True, font_size=10, color=(1,1,1,1), 
            size_hint=(None, None), size=(75, 20), pos_hint={'right': 0.96, 'top': 0.88}
        )
        with badge_lbl.canvas.before:
            Color(glow_color[0], glow_color[1], glow_color[2], 0.3)
            self.badge_bg = RoundedRectangle(radius=[8])
        badge_lbl.bind(pos=self.update_badge_canvas, size=self.update_badge_canvas)
        self.add_widget(badge_lbl)
        
    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, 12)
        
        # Progress bar position
        track_x = self.x + (self.width * 0.18)
        track_y = self.y + 12
        track_w = self.width * 0.74
        track_h = 4
        
        self.prog_track.pos = (track_x, track_y)
        self.prog_track.size = (track_w, track_h)
        
        self.prog_fill.pos = (track_x, track_y)
        self.prog_fill.size = (track_w * (self.progress_val / 100.0), track_h)
        
    def update_badge_canvas(self, instance, *args):
        self.badge_bg.pos = instance.pos
        self.badge_bg.size = instance.size
        
    def on_card_release(self, *args):
        self.callback(self.mode, self.popup_ref)

# --- CUSTOM NEON MENU CARD (For Main Menu) ---
class NeonMenuCard(ButtonBehavior, FloatLayout):
    def __init__(self, title, desc, icon_name, glow_color, callback, popup_ref, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 80
        self.callback = callback
        self.popup_ref = popup_ref

        with self.canvas.before:
            # 1. Glassmorphism Translucent Background
            Color(0.06, 0.08, 0.14, 0.85)
            self.bg_rect = RoundedRectangle(radius=[12])
            
            # 2. Glowing Neon Border
            Color(*glow_color)
            self.border_line = Line(width=1.2)

        self.bind(pos=self.update_canvas, size=self.update_canvas)
        self.bind(on_release=self.on_card_release)

        # --- Vector Material Icons ---
        icon_lbl = MDIcon(
            icon=icon_name, 
            font_size=36, 
            theme_text_color="Custom", 
            text_color=glow_color,
            pos_hint={'x': 0.05, 'center_y': 0.5}
        )
        self.add_widget(icon_lbl)
        
        # --- Title ---
        title_lbl = Label(
            text=f"[b]{title}[/b]", markup=True, font_size=16, color=(1,1,1,1), 
            size_hint=(0.7, None), height=30, pos_hint={'x': 0.22, 'top': 0.85}, 
            halign="left", valign="middle"
        )
        title_lbl.bind(size=title_lbl.setter('text_size'))
        self.add_widget(title_lbl)

        # --- Description Subtitle ---
        desc_lbl = Label(
            text=f"[color=A0B0C0]{desc}[/color]", markup=True, font_size=12, 
            size_hint=(0.7, None), height=20, pos_hint={'x': 0.22, 'top': 0.45}, 
            halign="left", valign="middle"
        )
        desc_lbl.bind(size=desc_lbl.setter('text_size'))
        self.add_widget(desc_lbl)

    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, 12)
        
    def on_card_release(self, *args):
        # Popup को क्लोज करके अगला फंक्शन कॉल करेगा
        self.popup_ref.dismiss()
        self.callback(None)
# --- CUSTOM NEON VOCABULARY CARD ---
class NeonVocabCard(FloatLayout):
    def __init__(self, eng_word, mar_word, glow_color, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 75
        
        with self.canvas.before:
            # Translucent Glass Background
            Color(0.06, 0.08, 0.14, 0.85)
            self.bg_rect = RoundedRectangle(radius=[12])
            
            # Glowing Neon Border
            Color(*glow_color)
            self.border_line = Line(width=1.2)
            
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        
        # Glowing Icon (Lightbulb)
        icon_lbl = MDIcon(
            icon="lightbulb-on-outline", font_size=32, 
            theme_text_color="Custom", text_color=glow_color, 
            pos_hint={'x': 0.04, 'center_y': 0.5}
        )
        self.add_widget(icon_lbl)
        
        # English Word
        eng_lbl = Label(
            text=f"[b]{eng_word}[/b]", markup=True, font_size=16, color=(1,1,1,1), 
            size_hint=(0.7, None), height=30, pos_hint={'x': 0.18, 'top': 0.85}, 
            halign="left", valign="middle"
        )
        eng_lbl.bind(size=eng_lbl.setter('text_size'))
        self.add_widget(eng_lbl)
        # Marathi Meaning (Fixed Font for Devanagari)
        custom_font = 'Marathi.ttf' if os.path.exists('Marathi.ttf') else 'Roboto'
        
        mar_lbl = Label(
            text=f"[color=A0B0C0]{mar_word}[/color]", markup=True, font_size=14, 
            font_name=custom_font,  # <-- यह लाइन डिब्बों की समस्या दूर करेगी
            size_hint=(0.7, None), height=20, pos_hint={'x': 0.18, 'top': 0.45}, 
            halign="left", valign="middle"
        )
        mar_lbl.bind(size=mar_lbl.setter('text_size'))
        self.add_widget(mar_lbl)

    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, 12)

# --- CUSTOM NEON STAT CARD (For Gamer Dashboard) ---
class NeonStatCard(FloatLayout):
    def __init__(self, icon_name, title, value, glow_color, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 85
        
        with self.canvas.before:
            # Translucent Glass Background
            Color(0.06, 0.08, 0.14, 0.85)
            self.bg_rect = RoundedRectangle(radius=[12])
            
            # Glowing Neon Border
            Color(*glow_color)
            self.border_line = Line(width=1.2)
            
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        
        # Stat Icon
        icon_lbl = MDIcon(
            icon=icon_name, font_size=38, 
            theme_text_color="Custom", text_color=glow_color, 
            pos_hint={'x': 0.05, 'center_y': 0.5}
        )
        self.add_widget(icon_lbl)
        
        # Stat Title (e.g., "Current Level")
        title_lbl = Label(
            text=f"[color=A0B0C0]{title}[/color]", markup=True, font_size=13, 
            size_hint=(0.7, None), height=20, pos_hint={'x': 0.22, 'top': 0.85}, 
            halign="left", valign="middle"
        )
        title_lbl.bind(size=title_lbl.setter('text_size'))
        self.add_widget(title_lbl)
        
        # Stat Value (e.g., "Level 5")
        value_lbl = Label(
            text=f"[b]{value}[/b]", markup=True, font_size=20, color=(1,1,1,1), 
            size_hint=(0.7, None), height=30, pos_hint={'x': 0.22, 'top': 0.55}, 
            halign="left", valign="middle"
        )
        value_lbl.bind(size=value_lbl.setter('text_size'))
        self.add_widget(value_lbl)

    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, 12)

# --- SCREEN 2: MAIN CHAT UI (Modern & Clean) ---
class ChatScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chat_font_size = 15 
        
        main_layout = BoxLayout(orientation='vertical')

        # --- 1. MODERN HEADER ---
        header = BoxLayout(orientation='horizontal', size_hint_y=0.08, padding=(10, 5), spacing=10)
        
        # Menu Icon (अब यह सभी फीचर्स का मेनू खोलेगा)
        self.menu_btn = MDIconButton(icon="menu", theme_text_color="Custom", text_color=(0, 0.8, 1, 1), pos_hint={"center_y": 0.5})
        self.menu_btn.bind(on_press=self.show_main_menu)
        header.add_widget(self.menu_btn)
        
        self.title_lbl = Label(text="[b]AI English Teacher[/b]", markup=True, font_size=20, color=(1, 1, 1, 1), size_hint_x=0.8)
        header.add_widget(self.title_lbl)
        
        # Settings Icon
        self.settings_btn = MDIconButton(icon="cog", theme_text_color="Custom", text_color=(0.7, 0.7, 0.7, 1), pos_hint={"center_y": 0.5})
        self.settings_btn.bind(on_press=self.show_settings)
        header.add_widget(self.settings_btn)
        
        main_layout.add_widget(header)

        # --- 2. VIDEO CONTAINER ---
        self.video_container = FloatLayout(size_hint_y=0.3)
        self.vid_idle = Video(source='robot_speaking.mp4', state='play', options={'eos': 'loop'}, size_hint=(1, 1), pos_hint={'center_x': 0.5, 'center_y': 0.5}, opacity=1)
        self.vid_thinking = Video(source='robot_thinking.mp4', state='play', options={'eos': 'loop'}, size_hint=(1, 1), pos_hint={'center_x': 0.5, 'center_y': 0.5}, opacity=0)
        self.vid_speaking = Video(source='robot_speaking.mp4', state='play', options={'eos': 'loop'}, size_hint=(1, 1), pos_hint={'center_x': 0.5, 'center_y': 0.5}, opacity=0)
        self.video_container.add_widget(self.vid_idle)
        self.video_container.add_widget(self.vid_thinking)
        self.video_container.add_widget(self.vid_speaking)
        main_layout.add_widget(self.video_container)

        # --- 3. CHAT LIST ---
        self.scroll = ScrollView(size_hint_y=0.52, do_scroll_x=False)
        self.chat_list = BoxLayout(orientation='vertical', size_hint_y=None, padding=15, spacing=15)
        self.chat_list.bind(minimum_height=self.chat_list.setter('height'))
        self.scroll.add_widget(self.chat_list)
        main_layout.add_widget(self.scroll)

        # --- 4. ULTRA-MODERN INPUT BAR ---
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=0.1, padding=(10, 8, 10, 8), spacing=8)
        
        # Mic Button
        self.mic_btn = MDIconButton(icon="microphone", md_bg_color=(0, 0.5, 0.9, 1), theme_text_color="Custom", text_color=(1, 1, 1, 1), pos_hint={"center_y": 0.5})
        self.mic_btn.bind(on_press=self.start_listening)
        input_layout.add_widget(self.mic_btn)
        
        # Text Box
        self.user_input = TextInput(
            hint_text="Type your message here...", multiline=False, font_size=14, size_hint_x=0.55, 
            background_color=(0.12, 0.16, 0.24, 1), foreground_color=(1, 1, 1, 1), cursor_color=(0, 0.8, 1, 1),
            padding=(12, 12)
        )
        self.user_input.bind(on_text_validate=self.send_message)
        input_layout.add_widget(self.user_input)
        
        # Explain Button (Bulb)
        self.explain_btn = MDIconButton(icon="lightbulb-on", md_bg_color=(0.9, 0.6, 0, 1), theme_text_color="Custom", text_color=(1, 1, 1, 1), pos_hint={"center_y": 0.5})
        self.explain_btn.bind(on_press=self.explain_last_message)
        input_layout.add_widget(self.explain_btn)
        
        # Send Button
        self.send_btn = MDIconButton(icon="send", md_bg_color=(0, 0.7, 0.3, 1), theme_text_color="Custom", text_color=(1, 1, 1, 1), pos_hint={"center_y": 0.5})
        self.send_btn.bind(on_press=self.send_message)
        input_layout.add_widget(self.send_btn)
        
        main_layout.add_widget(input_layout)
        self.add_widget(main_layout)

        self.client = None
        self.current_voice_tld = 'us'
        self.chat_history_ai = []

    def show_main_menu(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # --- MODERN HEADER WITH MD ICON (No Box Error) ---
        title_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, size_hint_x=None, width=230, pos_hint={'center_x': 0.5})
        title_box.add_widget(MDIcon(icon="lightning-bolt", font_size=28, theme_text_color="Custom", text_color=(0, 0.82, 1, 1), pos_hint={'center_y': 0.5}, size_hint_x=None, width=40))
        title_box.add_widget(Label(text="[b][color=00D2FF]AI Learning Hub[/color][/b]", markup=True, font_size=22, pos_hint={'center_y': 0.5}))
        content.add_widget(title_box)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        menu_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None, padding=(2,2,2,2))
        menu_layout.bind(minimum_height=menu_layout.setter('height'))
        
        popup = Popup(
            title='', separator_height=0, 
            size_hint=(0.88, 0.7), 
            background_color=(0.02, 0.04, 0.08, 0.95)
        )
        
        # --- मेनू के ऑप्शंस (Title, Subtitle, Icon, Neon Color, Function) ---
        options = [
            ("Practice Modes & Roleplay", "Improve your English skills", "controller-classic-outline", (0, 0.9, 1, 1), self.show_practice),
             # --- KIDS MODES ---
            ("Choose AI Friend", "Fun characters for children", "face-man-profile", (1, 0.2, 0.6, 1), self.start_kids_mode), 
            ("Kids Adventure World", "Explore fun places in English", "rocket-launch-outline", (1, 0.5, 0.2, 1), self.show_kids_world),
            ("Kids Mode (Play & Learn)", "Fun & easy learning for children", "emoticon-happy-outline", (1, 0.2, 0.6, 1), self.start_kids_mode), 
            ("Gamer Dashboard & XP", "Check your progress & stats", "chart-bar", (0.3, 1, 0.5, 1), self.show_more),
            ("Word of the Day", "Learn new vocabulary daily", "book-open-page-variant-outline", (1, 0.6, 0.2, 1), self.show_features)
        ]
        
        for title, desc, icon_name, glow_color, callback in options:
            card = NeonMenuCard(
                title=title, desc=desc, icon_name=icon_name, 
                glow_color=glow_color, callback=callback, popup_ref=popup
            )
            menu_layout.add_widget(card)
            
        scroll.add_widget(menu_layout)
        content.add_widget(scroll)
        
        close_btn = Button(
            text="Close Menu", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def start_kids_mode(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # --- FUN KIDS HEADER ---
        title_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, size_hint_x=None, width=280, pos_hint={'center_x': 0.5})
        title_box.add_widget(MDIcon(icon="face-man-profile", font_size=32, theme_text_color="Custom", text_color=(1, 0.84, 0, 1), pos_hint={'center_y': 0.5}, size_hint_x=None, width=40))
        title_box.add_widget(Label(text="[b][color=FFD700]Choose AI Friend[/color][/b]", markup=True, font_size=22, pos_hint={'center_y': 0.5}))
        content.add_widget(title_box)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        avatar_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None, padding=(2,2,2,2))
        avatar_layout.bind(minimum_height=avatar_layout.setter('height'))
        
        popup = Popup(title='', separator_height=0, size_hint=(0.88, 0.8), background_color=(0.02, 0.04, 0.08, 0.95))
        
        # --- CHARACTERS LIST ---
        avatars = [
            ("Nova (Robot)", "Friendly & Smart", "robot-outline", (0, 0.8, 1, 1), "Nova"),
            ("Pipo (Panda)", "Cute & Funny", "teddy-bear", (1, 0.3, 0.6, 1), "Pipo"),
            ("Leo (Lion)", "Brave & Strong", "cat", (1, 0.6, 0.1, 1), "Leo"),
            ("Zoro (Alien)", "Fun Explorer", "alien-outline", (0.2, 0.9, 0.2, 1), "Zoro")
        ]
        
        for name, trait, icon_name, color, char_id in avatars:
            card = NeonMenuCard(
                title=name, desc=trait, icon_name=icon_name, glow_color=color, 
                callback=lambda x, c=char_id: self.activate_kids_character(c, popup), popup_ref=popup
            )
            avatar_layout.add_widget(card)
            
        scroll.add_widget(avatar_layout)
        content.add_widget(scroll)
        
        close_btn = Button(
            text="Close", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def activate_kids_character(self, char_name, popup):
        popup.dismiss()
        self.chat_list.clear_widgets()
        
        if char_name == "Nova":
            sys_prompt = "You are Nova, a friendly and smart robot. Speak in very simple English to a 6-year-old child. Use robot and space emojis 🤖🚀. Keep sentences very short, encouraging, and fun!"
            welcome_msg = "Beep Boop! 🤖 Hello! I am Nova the Robot. Are you ready for an English adventure? 🚀"
            self.set_robot_video_theme("robot")
            
        elif char_name == "Pipo":
            sys_prompt = "You are Pipo, a cute, cuddly, and funny panda. Speak in very simple English to a 6-year-old child. Use panda, bamboo, and food emojis 🐼🎋. Be very soft and sweet."
            welcome_msg = "Yay! 🐼 I am Pipo the Panda. Let's play games and learn English together! 🎋"
            self.set_robot_video_theme("panda")
            
        elif char_name == "Leo":
            sys_prompt = "You are Leo, a brave and strong lion. Speak in very simple English to a 6-year-old child. Use lion and jungle emojis 🦁🌳. Be very brave and motivate the child."
            welcome_msg = "Roaar! 🦁 I am Leo the Lion! Don't be afraid to make mistakes, let's learn bravely! 🌟"
            self.set_robot_video_theme("lion")
            
        elif char_name == "Zoro":
            sys_prompt = "You are Zoro, a funny alien from space. Speak in very simple English to a 6-year-old child. Use alien and star emojis 👽🛸. Act curious about Earth."
            welcome_msg = "Greetings from Space! 👽 I am Zoro. Teach me some Earth words today! 🛸"
            self.set_robot_video_theme("alien")

        self.chat_history_ai = [{"role": "system", "content": sys_prompt}]
        self.add_chat_bubble(f"System: Kids Mode Activated! Playing with {char_name}", "ai")
        
        self.change_robot_video("thinking")
        threading.Thread(target=self.prepare_audio_and_text, args=(welcome_msg,), daemon=True).start()

    def show_kids_world(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # --- FUN ADVENTURE HEADER ---
        title_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, size_hint_x=None, width=280, pos_hint={'center_x': 0.5})
        title_box.add_widget(MDIcon(icon="rocket-launch", font_size=32, theme_text_color="Custom", text_color=(1, 0.5, 0.2, 1), pos_hint={'center_y': 0.5}, size_hint_x=None, width=40))
        title_box.add_widget(Label(text="[b][color=FF8C00]Adventure World[/color][/b]", markup=True, font_size=22, pos_hint={'center_y': 0.5}))
        content.add_widget(title_box)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        world_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None, padding=(2,2,2,2))
        world_layout.bind(minimum_height=world_layout.setter('height'))
        
        popup = Popup(title='', separator_height=0, size_hint=(0.88, 0.8), background_color=(0.02, 0.04, 0.08, 0.95))
        
        # --- YAHAN ALPHABET ADVENTURE ADD KIYA GAYA HAI ---
        worlds = [
            ("Alphabet Adventure", "A to Z with Voice & Video", "sort-alphabetical-variant", (1, 0.8, 0, 1), "kids_alphabet"),
            ("Space Explorer", "Meet aliens and count stars", "rocket-outline", (0.8, 0.2, 1, 1), "kids_space"),
            ("Jungle Safari", "Learn animal names", "pine-tree", (0.2, 0.8, 0.2, 1), "kids_jungle"),
            ("Supermarket Fun", "Buy fruits and toys", "cart-outline", (1, 0.8, 0, 1), "kids_market"),
            ("My Home", "Everyday things at home", "home-outline", (0, 0.8, 1, 1), "kids_home")
        ]
        
        for title, desc, icon_name, color, mode in worlds:
            card = NeonMenuCard(
                title=title, desc=desc, icon_name=icon_name, glow_color=color, 
                callback=lambda x, m=mode: self.start_kids_adventure(m), popup_ref=popup
            )
            world_layout.add_widget(card)
            
        scroll.add_widget(world_layout)
        content.add_widget(scroll)
        
        close_btn = Button(
            text="Close", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def start_kids_adventure(self, mode):
        # --- ALPHABET SCREEN PE SWITCH KARNE KA LOGIC ---
        if mode == 'kids_alphabet':
            self.manager.current = 'alphabet'
            return

        self.chat_list.clear_widgets()
        
        # --- CRASH FIX: Default values set kar diye hain ---
        sys_prompt = "You are a helpful AI guide for kids. Speak in simple English with emojis."
        initial_msg = "Welcome to the adventure world! Let's play and learn! 🎈"
        
        if mode == 'kids_space':
            sys_prompt = "You are an astronaut in space. Speak to a 6-year-old child in very simple English. Use emojis like 🚀👽⭐. Ask the child to count stars or identify planets."
            initial_msg = "Whoosh! 🚀 Welcome to space! I can see 3 shiny stars ⭐⭐⭐. Can you say 'stars'?"
            
        elif mode == 'kids_jungle':
            sys_prompt = "You are a fun jungle safari guide. The user is a 6-year-old child. Introduce ONE animal at a time (like lion, elephant, monkey, tiger). Tell one very short, fun fact about the animal in simple English, use emojis, and ask a simple question about it."
            initial_msg = "Welcome to the Jungle Safari! 🚙🌳 Look over there, I see a big elephant! 🐘 Do you know elephants have very long trunks? Do you like elephants?"
            
        elif mode == 'kids_market':
            sys_prompt = "You are a friendly supermarket cashier. Speak to a 6-year-old child in simple English. Use emojis like 🛒🍎🧸. Ask them what fruit they want to buy."
            initial_msg = "Hello! Welcome to the supermarket 🛒. We have apples 🍎 and bananas 🍌. What do you want to buy?"
            
        elif mode == 'kids_home':
            sys_prompt = "You are playing a game at home. Speak to a 6-year-old in simple English. Use emojis like 🏠🛏️🧸. Ask them to point at a chair or their bed."
            initial_msg = "Welcome home! 🏠 Let's play a game. Can you say 'This is my bed' 🛏️?"
            
        self.chat_history_ai = [{"role": "system", "content": sys_prompt}]
        self.add_chat_bubble(f"System: Adventure World ({mode.replace('kids_', '').title()}) Started! 🎈", "ai")
        
        self.change_robot_video("thinking")
        import threading
        threading.Thread(target=self.prepare_audio_and_text, args=(initial_msg,), daemon=True).start()
        
    def initialize_ai(self, user_name, age_group, level):
        self.title_lbl.text = f"[b]Hi, {user_name}[/b]"
        
        if "Senior" in age_group:
            self.chat_font_size = 20
            age_prompt = "You are talking to a senior citizen (50+). Speak respectfully, clearly, and keep sentences very short."
        elif "Child" in age_group:
            self.chat_font_size = 16
            age_prompt = "You are talking to a kid under 18. Be very playful, encouraging, and use lots of emojis."
        else:
            self.chat_font_size = 15
            age_prompt = "You are talking to an adult. Be professional and helpful."
            
        if "Beginner" in level:
            level_prompt = "The user is an absolute beginner. Keep English very simple. ALWAYS provide a Roman Marathi translation for every English sentence you speak."
        elif "Advanced" in level:
            level_prompt = "The user is advanced. Speak entirely in fluent English and focus on advanced vocabulary."
        else:
            level_prompt = "The user is at an intermediate level. Correct grammar mistakes using 'Incorrect:' and 'Correct:' format."

        self.chat_history_ai = [
            {"role": "system", "content": f"You are an AI English teacher for Indian students. The user's name is {user_name}. {age_prompt} {level_prompt}"}
        ]
        threading.Thread(target=self.load_ai_model, args=(user_name,), daemon=True).start()
    def set_robot_video_theme(self, theme_name):
        import os
        
        default_speaking = 'robot_speaking.mp4'
        default_thinking = 'robot_thinking.mp4'
        
        custom_speaking = f"{theme_name}_speaking.mp4"
        custom_thinking = f"{theme_name}_thinking.mp4"
        
        if os.path.exists(custom_speaking):
            self.vid_speaking.source = custom_speaking
            self.vid_idle.source = custom_speaking
        else:
            self.vid_speaking.source = default_speaking
            self.vid_idle.source = default_speaking
            
        if os.path.exists(custom_thinking):
            self.vid_thinking.source = custom_thinking
        else:
            self.vid_thinking.source = default_thinking
            
        self.vid_idle.state = 'play'
        self.vid_thinking.state = 'play'
        self.vid_speaking.state = 'play'
            
    def show_settings(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=10)
        content.add_widget(Label(text="[color=00C8FF][b]⚙️ Settings[/b][/color]", markup=True, font_size=16, size_hint_y=0.15))
        
        content.add_widget(Label(text="Select AI Accent:", font_size=14, size_hint_y=0.1))
        
        voice_layout = BoxLayout(orientation='vertical', spacing=5, size_hint_y=0.4)
        
        btn_us = Button(text="🇺🇸 American (Default)", background_color=(0.1, 0.2, 0.4, 1))
        btn_us.bind(on_press=lambda x: self.change_voice('us', popup))
        
        btn_in = Button(text="🇮🇳 Indian English", background_color=(0.1, 0.2, 0.4, 1))
        btn_in.bind(on_press=lambda x: self.change_voice('co.in', popup))
        
        btn_uk = Button(text="🇬🇧 British English", background_color=(0.1, 0.2, 0.4, 1))
        btn_uk.bind(on_press=lambda x: self.change_voice('co.uk', popup))
        
        voice_layout.add_widget(btn_us)
        voice_layout.add_widget(btn_in)
        voice_layout.add_widget(btn_uk)
        content.add_widget(voice_layout)
        
        # नवीन: Family Learning (Switch Profile - Option 3)
        btn_switch = Button(text="👥 Switch Profile (Family)", size_hint_y=0.2, background_color=(0, 0.5, 0.2, 1), bold=True)
        btn_switch.bind(on_press=lambda x: self.switch_profile(popup))
        content.add_widget(btn_switch)
        
        close_btn = Button(text="Close", size_hint_y=0.15, background_color=(0, 0.6, 1, 1), font_size=16, bold=True)
        content.add_widget(close_btn)
        
        popup = Popup(title='Settings', content=content, size_hint=(0.85, 0.7), background_color=(0.02, 0.04, 0.1, 1))
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def switch_profile(self, popup):
        popup.dismiss()
        self.manager.current = 'profile'
        
    def explain_last_message(self, instance):
        if len(self.chat_history_ai) > 1:
            explain_prompt = "मला तुमचे मागचे वाक्य समजले नाही. कृपया ते अतिशय सोप्या शब्दांत, उदाहरणासह आणि पूर्णपणे रोमन मराठीत (Roman Marathi) समजावून सांगा."
            self.add_chat_bubble("System: Asking AI to explain again...", "user")
            threading.Thread(target=self.generate_ai_response, args=(explain_prompt,), daemon=True).start()

    def show_features(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # --- MODERN HEADER WITH MD ICON (No Box Error) ---
        title_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, size_hint_x=None, width=240, pos_hint={'center_x': 0.5})
        title_box.add_widget(MDIcon(icon="book-open-page-variant", font_size=28, theme_text_color="Custom", text_color=(0, 0.82, 1, 1), pos_hint={'center_y': 0.5}, size_hint_x=None, width=40))
        title_box.add_widget(Label(text="[b][color=00D2FF]Word of the Day[/color][/b]", markup=True, font_size=22, pos_hint={'center_y': 0.5}))
        content.add_widget(title_box)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        vocab_layout = BoxLayout(orientation='vertical', spacing=12, size_hint_y=None, padding=(2,2,2,2))
        vocab_layout.bind(minimum_height=vocab_layout.setter('height'))
        
        # --- HUGE VOCABULARY DATABASE (100 Words) ---
        all_words = [
            ("Accept", "स्वीकारणे (Svikarne)"),
            ("Accident", "अपघात (Apghat)"),
            ("Advice", "सल्ला (Salla)"),
            ("Always", "नेहमी (Nehmi)"),
            ("Angry", "रागवलेला (Ragavlela)"),
            ("Answer", "उत्तर (Uttar)"),
            ("Beautiful", "सुंदर (Sundar)"),
            ("Believe", "विश्वास ठेवणे (Vishwas thevne)"),
            ("Borrow", "उधार घेणे (Udhar ghene)"),
            ("Brave", "शूर (Shoor)"),
            ("Business", "व्यवसाय (Vyavsay)"),
            ("Careful", "काळजीपूर्वक (Kaljipurvak)"),
            ("Catch", "पकडणे (Pakadne)"),
            ("Change", "बदल (Badal)"),
            ("Clean", "स्वच्छ (Swachh)"),
            ("Clever", "हुशार (Hushar)"),
            ("Common", "सामान्य (Samanya)"),
            ("Complain", "तक्रार करणे (Takrar karne)"),
            ("Complete", "पूर्ण (Purna)"),
            ("Condition", "स्थिती (Sthiti)"),
            ("Confidence", "आत्मविश्वास (Aatmavishwas)"),
            ("Continue", "सुरू ठेवणे (Suru thevne)"),
            ("Correct", "बरोबर (Barobar)"),
            ("Courage", "धैर्य (Dhairya)"),
            ("Curious", "उत्सुक (Utsuk)"),
            ("Danger", "धोका (Dhoka)"),
            ("Decide", "ठरवणे (Tharavne)"),
            ("Defeat", "पराभव (Parabhav)"),
            ("Demand", "मागणी (Magani)"),
            ("Describe", "वर्णन करणे (Varnan karne)"),
            ("Destroy", "नष्ट करणे (Nasht karne)"),
            ("Develop", "विकसित करणे (Vikasit karne)"),
            ("Different", "वेगळे (Vegale)"),
            ("Difficult", "कठीण (Kathin)"),
            ("Direct", "थेट (Thet)"),
            ("Discover", "शोधणे (Shodhane)"),
            ("Discuss", "चर्चा करणे (Charcha karne)"),
            ("Disease", "आजार (Aajar)"),
            ("Divide", "विभागणे (Vibhagne)"),
            ("Doubt", "शंका (Shanka)"),
            ("Educate", "शिक्षित करणे (Shikshit karne)"),
            ("Effort", "प्रयत्न (Prayatna)"),
            ("Empty", "रिकामे (Rikame)"),
            ("Encourage", "प्रोत्साहन देणे (Protsahan dene)"),
            ("Enemy", "शत्रू (Shatru)"),
            ("Energy", "ऊर्जा (Urja)"),
            ("Enough", "पुरेसे (Purese)"),
            ("Equal", "समान (Saman)"),
            ("Error", "चूक (Chuk)"),
            ("Escape", "सुटका (Sutka)"),
            ("Essential", "आवश्यक (Aavashyak)"),
            ("Exact", "अचूक (Achuk)"),
            ("Example", "उदाहरण (Udahaaran)"),
            ("Expect", "अपेक्षा करणे (Apeksha karne)"),
            ("Experience", "अनुभव (Anubhav)"),
            ("Explain", "स्पष्ट करणे (Spasht karne)"),
            ("Express", "व्यक्त करणे (Vyakt karne)"),
            ("Famous", "प्रसिद्ध (Prasiddha)"),
            ("Farmer", "शेतकरी (Shetkari)"),
            ("Fascinating", "आकर्षक (Aakarshak)"),
            ("Fear", "भीती (Bhiti)"),
            ("Final", "अंतिम (Antim)"),
            ("Finish", "संपवणे (Sampavne)"),
            ("Flexible", "लवचिक (Lavchik)"),
            ("Fluent", "अस्खलित (Askhalit)"),
            ("Focus", "लक्ष केंद्रित करणे (Laksh kendrit karne)"),
            ("Forget", "विसरणे (Visarne)"),
            ("Forgive", "क्षमा करणे (Kshama karne)"),
            ("Freedom", "स्वातंत्र्य (Swatantrya)"),
            ("Frequent", "वारंवार (Varanvar)"),
            ("Friendly", "मैत्रीपूर्ण (Maitripurna)"),
            ("Future", "भविष्य (Bhavishya)"),
            ("Gather", "गोळा करणे (Gola karne)"),
            ("Generate", "निर्माण करणे (Nirman karne)"),
            ("Generous", "उदार (Udar)"),
            ("Gentle", "सौम्य (Saumya)"),
            ("Genuine", "खरे (Khare)"),
            ("Glorious", "तेजस्वी (Tejasvi)"),
            ("Grateful", "कृतज्ञ (Krutadnya)"),
            ("Great", "महान (Mahan)"),
            ("Grow", "वाढणे (Vadhane)"),
            ("Guilty", "दोषी (Doshi)"),
            ("Habit", "सवयी (Savayi)"),
            ("Handle", "हाताळणे (Hatalne)"),
            ("Happen", "घडणे (Ghadne)"),
            ("Happy", "आनंदी (Aanandi)"),
            ("Harmful", "हानिकारक (Hanikarak)"),
            ("Healthy", "निरोगी (Nirogi)"),
            ("Heavy", "जड (Jad)"),
            ("Helpful", "मदतनीस (Madatnis)"),
            ("Hesitate", "संकोच करणे (Sankoch karne)"),
            ("Hidden", "लपलेले (Lapalele)"),
            ("History", "इतिहास (Itihas)"),
            ("Honest", "प्रामाणिक (Pramanik)"),
            ("Hope", "आशा (Aasha)"),
            ("Huge", "प्रचंड (Prachand)"),
            ("Hungry", "भुकेलेला (Bhukelela)"),
            ("Identify", "ओळखणे (Olakhne)"),
            ("Ignore", "दुर्लक्ष करणे (Durlaksh karne)"),
            ("Important", "महत्त्वाचे (Mahattvache)"),
            ("Improve", "सुधारणा करणे (Sudharna karne)"),
            # --- J TO Z VOCABULARY ---
            ("Join", "सामील होणे (Saamil hone)"),
            ("Journey", "प्रवास (Pravas)"),
            ("Joy", "आनंद (Aanand)"),
            ("Judge", "निर्णय घेणे (Nirnay ghene)"),
            ("Justice", "न्याय (Nyay)"),
            ("Keep", "ठेवणे (Thevne)"),
            ("Knowledge", "ज्ञान (Dnyan)"),
            ("Language", "भाषा (Bhasha)"),
            ("Learn", "शिकणे (Shikne)"),
            ("Leave", "सोडणे (Sodne)"),
            ("Leader", "नेता (Neta)"),
            ("Limit", "मर्यादा (Maryada)"),
            ("Loyal", "निष्ठावान (Nishthavan)"),
            ("Maintain", "टिकवून ठेवणे (Tikvun thevne)"),
            ("Major", "प्रमुख (Pramukh)"),
            ("Manage", "व्यवस्थापन करणे (Vyavasthapan karne)"),
            ("Measure", "मोजणे (Mojne)"),
            ("Memory", "स्मृती (Smruti)"),
            ("Method", "पद्धत (Paddhat)"),
            ("Natural", "नैसर्गिक (Naisargik)"),
            ("Necessary", "आवश्यक (Aavashyak)"),
            ("Notice", "लक्षात घेणे (Lakshat ghene)"),
            ("Nervous", "घाबरलेला (Ghabarlela)"),
            ("Object", "आक्षेप घेणे / वस्तू (Aakshep ghene)"),
            ("Observe", "निरीक्षण करणे (Nirikshan karne)"),
            ("Opportunity", "संधी (Sandhi)"),
            ("Option", "पर्याय (Paryay)"),
            ("Ordinary", "सामान्य (Samanya)"),
            ("Participate", "सहभागी होणे (Sahbhagi hone)"),
            ("Patience", "संयम (Sanyam)"),
            ("Perfect", "परिपूर्ण (Paripurna)"),
            ("Permanent", "कायमस्वरूपी (Kayamswarupi)"),
            ("Practice", "सराव (Sarav)"),
            ("Quality", "गुणवत्ता (Gunvatta)"),
            ("Quantity", "प्रमाण (Praman)"),
            ("Question", "प्रश्न (Prashna)"),
            ("Quiet", "शांत (Shant)"),
            ("Reason", "कारण (Karan)"),
            ("Receive", "मिळवणे (Milavne)"),
            ("Reduce", "कमी करणे (Kami karne)"),
            ("Regular", "नियमित (Niyamit)"),
            ("Respect", "आदर (Aadar)"),
            ("Satisfy", "समाधान करणे (Samadhan karne)"),
            ("Secret", "गुप्त (Gupt)"),
            ("Serious", "गंभीर (Gambhir)"),
            ("Skill", "कौशल्य (Kaushalya)"),
            ("Success", "यश (Yash)"),
            ("Target", "लक्ष्य (Lakshya)"),
            ("Teach", "शिकवणे (Shikavne)"),
            ("Thought", "विचार (Vichar)"),
            ("Trust", "विश्वास (Vishwas)"),
            ("Understand", "समजणे (Samajne)"),
            ("Unique", "अद्वितीय (Adwitiya)"),
            ("Useful", "उपयुक्त (Upayukt)"),
            ("Usual", "नेहमीचे (Nehmiche)"),
            ("Valuable", "मूल्यवान (Mulyavan)"),
            ("Various", "विविध (Vividh)"),
            ("Victory", "विजय (Vijay)"),
            ("Vision", "दृष्टी (Drushti)"),
            ("Waste", "वाया घालवणे (Vaya ghalavne)"),
            ("Wealth", "संपत्ती (Sampatti)"),
            ("Wonder", "आश्चर्य (Aashcharya)"),
            ("Worth", "मूल्य (Mulya)"),
            ("Yield", "उत्पन्न (Utpanna)"),
            ("Youth", "तरुणपण (Tarunpan)"),
            ("Zeal", "उत्साह (Utsah)"),
            ("Zone", "क्षेत्र (Kshetra)")
        ]
        
        # जादू: पूरी लिस्ट में से हर बार 5 नए शब्द रैंडमली चुनना
        daily_words = random.sample(all_words, 5)
        
        # 5 अलग-अलग नियॉन कलर्स 
        colors = [(0, 0.9, 1, 1), (0.3, 1, 0.8, 1), (1, 0.5, 0.2, 1), (0.8, 0.3, 1, 1), (0.9, 0.8, 0.1, 1)]
        
        for i, (eng, mar) in enumerate(daily_words):
            card = NeonVocabCard(eng_word=eng, mar_word=mar, glow_color=colors[i % len(colors)])
            vocab_layout.add_widget(card)
            
        scroll.add_widget(vocab_layout)
        content.add_widget(scroll)
        
        close_btn = Button(
            text="Close", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        popup = Popup(title='', separator_height=0, size_hint=(0.88, 0.7), background_color=(0.02, 0.04, 0.08, 0.95))
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def show_practice(self, instance):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        title_lbl = Label(text="[b][color=00D2FF]Practice Modes[/color][/b]", markup=True, font_size=22, size_hint_y=None, height=40)
        content.add_widget(title_lbl)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        topics_layout = BoxLayout(orientation='vertical', spacing=12, size_hint_y=None, padding=(2,2,2,2))
        topics_layout.bind(minimum_height=topics_layout.setter('height'))
        
        popup = Popup(title='', separator_height=0, size_hint=(0.88, 0.8), background_color=(0.02, 0.04, 0.08, 0.95))
        
        # 1. CONTINUE LAST PRACTICE (अब यह छोटा, स्लीक और अलग दिखेगा)
        last_practice = NeonPracticeCard(
            title="Continue Last Practice", desc="Reading Practice - Lesson 5", 
            icon_name="play-circle-outline", level="Resume", progress=50, 
            glow_color=(0, 1, 0.5, 1), mode='reading_practice', 
            callback=self.start_roleplay, popup_ref=popup, is_top_card=True
        )
        topics_layout.add_widget(last_practice)
        
        # 2. ALL OTHER CARDS (Emojis हटाकर Professional Material Icons लगा दिए गए हैं)
        topics = [
            ("Reading Practice", "Read level-appropriate articles", "book-open-page-variant", 'reading_practice', "Beginner", 20, (0, 0.9, 1, 1)),
            ("Sentence Builder", "Build complex sentences", "puzzle-outline", 'sentence_builder', "Beginner", 45, (0.3, 1, 0.8, 1)),
            ("AI English Test", "Test your grammar & vocab", "brain", 'ai_test', "Beginner", 10, (0.8, 0.3, 1, 1)),
            ("Story Learning", "Learn through stories", "fire", 'story_learning', "Intermediate", 60, (1, 0.5, 0.2, 1)),
            ("Picture Learning", "Identify objects & scenes", "image-outline", 'picture_learning', "Intermediate", 30, (0.2, 0.8, 1, 1)),
            ("IT / Computer", "Technical support English", "laptop", 'it_support', "Advanced", 80, (1, 1, 0, 1)),
            ("Job Interview", "HR & workplace conversation", "briefcase-outline", 'interview', "Advanced", 15, (0, 1, 0.5, 1)),
            ("At the Hospital", "Doctor & patient dialogue", "hospital-box-outline", 'hospital', "Advanced", 5, (1, 0.2, 0.2, 1)),
            ("At the Bank", "Banking & financial terms", "bank-outline", 'bank', "Intermediate", 0, (0.2, 1, 0.5, 1)),
            ("Train Journey", "Co-passenger travel chat", "train", 'train', "Intermediate", 90, (0.7, 0.7, 1, 1))
        ]
        
        for title, desc, icon_name, mode, level, prog, glow_color in topics:
            card = NeonPracticeCard(
                title=title, desc=desc, icon_name=icon_name, level=level, progress=prog,
                glow_color=glow_color, mode=mode, callback=self.start_roleplay, popup_ref=popup, is_top_card=False
            )
            topics_layout.add_widget(card)
            
        scroll.add_widget(topics_layout)
        content.add_widget(scroll)
        
        close_btn = Button(
            text="Close", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def start_roleplay(self, mode, popup):
        popup.dismiss()
        self.chat_list.clear_widgets() 
        
        # HE NAVEEN LOGIC: Mode nusar video change karel
        self.set_robot_video_theme(mode)
        
        if mode == 'reading_practice':
            sys_prompt = "You are an English reading coach. Provide a short 2-sentence paragraph in English and ask the user to read it aloud using the microphone. If they read it correctly, praise them. If they make a mistake, correct their pronunciation using Roman Marathi."
            initial_msg = "Let's practice reading! Please use the Mic button and read this aloud:\n\n'I am learning English every day. It helps me communicate better.'"
        elif mode == 'writing_practice':
            sys_prompt = "You are an English writing coach. Give the user a Marathi sentence (in Roman script) and ask them to translate and type it in English. Correct their grammar if needed."
            initial_msg = "Let's practice writing! Please translate this sentence into English by typing in the chat:\n\n'मला उद्या नवीन मोबाईल विकत घ्यायचा आहे.'"
        elif mode == 'sentence_builder':
            sys_prompt = "You are an English teacher. Give the user 4-5 jumbled English words and ask them to form a correct sentence. Wait for their answer, correct it if wrong, and give feedback in Roman Marathi. Then give the next jumbled sentence."
            initial_msg = "Let's build a sentence! Please rearrange these words to make a correct sentence:\n\n[ English / learning / am / I ]"
        elif mode == 'story_learning':
            sys_prompt = "You are an English storyteller. Tell a very short, simple story (3-4 sentences) in English, provide the Roman Marathi translation, and then ask one simple question about the story to check comprehension. Wait for the user's answer."
            initial_msg = "Listen carefully to this short story:\n\nOnce there was a thirsty crow. He saw a pot with a little water. He put stones in the pot. The water came up and he drank it.\n\n(Ekda ek tahanlela kawla hota. Tyane ek bhande pahile jyat thode pani hote. Tyane bhandyat khade takle. Pani var ale ani tyane te pyale.)\n\nQuestion: What did the crow put in the pot?"
        elif mode == 'ai_test':
            sys_prompt = "You are an English Examiner. Conduct a quick 3-question English test. Ask one simple grammar or translation question at a time. Wait for the user to answer. After the user answers the 3rd question, give them a final score out of 10 and brief feedback in Roman Marathi."
            initial_msg = "Hello! Are you ready for a quick English test? Let's start! \n\nQuestion 1: Please translate this to English: 'मी उद्या शाळेत जाणार आहे.'"
        elif mode == 'picture_learning':
            sys_prompt = "You are an English teacher for kids and absolute beginners. Teach ONE basic vocabulary word at a time. Start with an emoji of the object, then the English word, then a simple English sentence, and explain its meaning in Roman Marathi. Ask the user to repeat the word."
            initial_msg = "Apple\nThis is an apple.\n(He ek safarchand ahe.)\n\nNow it's your turn! Please say: 'Apple'"
        elif mode == 'it_support':
            sys_prompt = "You are an IT customer whose computer has a problem. The user is an IT technical assistant. Explain a technical issue (like internet down or printer error). Correct the user's English mistakes using 'Incorrect:' and 'Correct:' format, and explain briefly in Roman Marathi."
            initial_msg = "Hello sir, my computer is not connecting to the WiFi and the printer is showing an error. Can you please help me fix this?"
        elif mode == 'hospital':
            sys_prompt = "You are a doctor. The user is a patient. Ask them about their health issue. Correct English mistakes using 'Incorrect:' and 'Correct:' format, and explain briefly in Roman Marathi."
            initial_msg = "Hello! Please have a seat. What brings you to the clinic today? Are you feeling unwell?"
        elif mode == 'bank':
            sys_prompt = "You are a bank manager. The user is a customer who wants to open a new account or withdraw money. Correct English mistakes using 'Incorrect:' and 'Correct:' format, and explain briefly in Roman Marathi."
            initial_msg = "Welcome to our bank! How can I help you today? Do you want to open a new account?"
        elif mode == 'train':  # <- HE NAVEEN TRAIN LOGIC
            sys_prompt = "You are a co-passenger on a train. The user is traveling with you. Start a friendly conversation about the journey. Correct English mistakes using 'Incorrect:' and 'Correct:' format, and explain briefly in Roman Marathi."
            initial_msg = "Hello! Are you traveling to Mumbai too? The train is quite crowded today, isn't it?"
        else:
            sys_prompt = "You are a helpful English teacher. Give the user one simple sentence in Roman Marathi and ask them to translate it to English. If wrong, correct it using 'Incorrect:' and 'Correct:' format."
            initial_msg = "Hello! Let's practice translation. Please translate this to English: 'Mala chaha pahije.'"
            
        self.chat_history_ai = [{"role": "system", "content": sys_prompt}]
        self.add_chat_bubble(f"System: Practice Mode Started! ({mode.replace('_', ' ').title()})", "ai")
        if popup:
            popup.dismiss()
            
        self.change_robot_video("thinking")
        threading.Thread(target=self.prepare_audio_and_text, args=(initial_msg,), daemon=True).start()           
        
    def show_more(self, instance):
        # पुराना लॉजिक (डेटा लाने के लिए)
        user = get_user_profile()
        progress = get_progress()
        total_msgs = progress[0]
        xp = progress[1]
        
        app_level = (xp // 100) + 1
        next_level_xp = app_level * 100
        name = user[1] if user else "Student"

        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # --- MODERN HEADER WITH MD ICON ---
        title_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, size_hint_x=None, width=280, pos_hint={'center_x': 0.5})
        title_box.add_widget(MDIcon(icon="controller-classic", font_size=28, theme_text_color="Custom", text_color=(0, 0.82, 1, 1), pos_hint={'center_y': 0.5}, size_hint_x=None, width=40))
        title_box.add_widget(Label(text="[b][color=00D2FF]Gamer Dashboard[/color][/b]", markup=True, font_size=22, pos_hint={'center_y': 0.5}))
        content.add_widget(title_box)
        
        scroll = ScrollView(size_hint=(1, 0.78), do_scroll_x=False)
        stats_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None, padding=(2,2,2,2))
        stats_layout.bind(minimum_height=stats_layout.setter('height'))
        
        # --- ADDING NEON STAT CARDS ---
        # 1. Player Name
        stats_layout.add_widget(NeonStatCard(
            icon_name="account-circle-outline", title="Player Profile", 
            value=name, glow_color=(0, 0.9, 1, 1) # Cyan
        ))
        
        # 2. Level (Golden Glow)
        stats_layout.add_widget(NeonStatCard(
            icon_name="star-shooting-outline", title="Current Level", 
            value=f"Level {app_level}", glow_color=(1, 0.84, 0, 1) # Gold
        ))
        
        # 3. XP Points (Green Glow)
        stats_layout.add_widget(NeonStatCard(
            icon_name="lightning-bolt-circle", title="XP Points Progress", 
            value=f"{xp} / {next_level_xp} XP", glow_color=(0.1, 0.9, 0.4, 1) # Neon Green
        ))
        
        # 4. Total Messages (Purple Glow)
        stats_layout.add_widget(NeonStatCard(
            icon_name="message-text-outline", title="Total Conversations", 
            value=f"{total_msgs} Messages", glow_color=(0.7, 0.3, 1, 1) # Purple
        ))
        
        scroll.add_widget(stats_layout)
        content.add_widget(scroll)
        
        # Close Button
        close_btn = Button(
            text="Close Dashboard", size_hint_y=None, height=45, 
            background_normal='', background_color=(0.1, 0.3, 0.5, 1), 
            font_size=16, bold=True
        )
        content.add_widget(close_btn)
        
        popup = Popup(title='', separator_height=0, size_hint=(0.88, 0.8), background_color=(0.02, 0.04, 0.08, 0.95))
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def change_voice(self, tld, popup):
        self.current_voice_tld = tld
        self.add_chat_bubble(f"System: Voice accent updated successfully!", "ai")
        popup.dismiss()

    def create_simple_popup(self, title, content_text):
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        lbl = Label(text=content_text, font_size=15, halign="left", valign="top")
        lbl.bind(size=lbl.setter('text_size'))
        content.add_widget(lbl)
        close_btn = Button(text="Close", size_hint_y=0.2, background_color=(0, 0.6, 1, 1), font_size=16, bold=True)
        content.add_widget(close_btn)
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.5), background_color=(0.02, 0.04, 0.1, 1))
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def load_ai_model(self, user_name):
        try:
            self.client = Groq(api_key=GROQ_API_KEY)
            Clock.schedule_once(lambda dt: self.on_model_ready(user_name), 0)
        except Exception as e:
            err_msg = str(e)
            Clock.schedule_once(lambda dt: self.add_chat_bubble(f"Error: API Connection Failed! ({err_msg})", "ai"), 0)

    def on_model_ready(self, user_name):
        self.user_input.disabled = False
        initial_msg = f"Hello {user_name}! I am your AI English assistant. How can I help you today?"
        
        # Naya logic: Pehle thinking video lagayein aur phir audio prepare karein
        self.change_robot_video("thinking")
        threading.Thread(target=self.prepare_audio_and_text, args=(initial_msg,), daemon=True).start()

    def start_listening(self, instance):
        if self.user_input.disabled:
            return
        self.user_input.text = "Listening... (Speak now)"
        self.mic_btn.disabled = True
        self.send_btn.disabled = True
        threading.Thread(target=self.record_audio, daemon=True).start()

    def record_audio(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = recognizer.recognize_google(audio, language='en-IN')
                Clock.schedule_once(lambda dt: self.on_audio_success(text), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_audio_error("Mic Error"), 0)

    def on_audio_success(self, text):
        self.user_input.text = text
        self.mic_btn.disabled = False
        self.send_btn.disabled = False
        self.send_message(None)

    def on_audio_error(self, err_msg):
        self.user_input.text = ""
        self.add_chat_bubble(f"⚠️ {err_msg}", "ai")
        self.mic_btn.disabled = False
        self.send_btn.disabled = False

    def add_chat_bubble(self, text, sender):
        bubble = ChatBubble(text=text, sender=sender, font_size=self.chat_font_size)
        self.chat_list.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0.2)

    def change_robot_video(self, state):
        self.vid_idle.opacity = 0
        self.vid_thinking.opacity = 0
        self.vid_speaking.opacity = 0
        if state == "thinking":
            self.vid_thinking.opacity = 1
        elif state == "speaking":
            self.vid_speaking.opacity = 1
        else:
            self.vid_idle.opacity = 1

    def send_message(self, instance):
        user_text = self.user_input.text.strip()
        if user_text.startswith("Listening...") or not user_text:
            return
            
        self.add_chat_bubble(user_text, "user")
        self.user_input.text = ""
        self.user_input.disabled = True
        self.change_robot_video("thinking")
        
        threading.Thread(target=update_progress, daemon=True).start()
        threading.Thread(target=self.generate_ai_response, args=(user_text,), daemon=True).start()
        
    def generate_ai_response(self, user_text):
        self.chat_history_ai.append({"role": "user", "content": user_text})
        try:
            chat_completion = self.client.chat.completions.create(
                messages=self.chat_history_ai,
                model="qwen/qwen3.8-27b",
                max_tokens=250,
                temperature=0.7
            )
            response = chat_completion.choices[0].message.content.strip()
            self.chat_history_ai.append({"role": "assistant", "content": response})
            if len(self.chat_history_ai) > 15:
                self.chat_history_ai = [self.chat_history_ai[0]] + self.chat_history_ai[-14:]
            Clock.schedule_once(lambda dt: self.on_response_ready(response), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.on_response_ready("Sorry, API error."), 0)

    def on_response_ready(self, response):
        self.add_chat_bubble(response, "ai")
        self.user_input.disabled = False
        self.change_robot_video("speaking")
        threading.Thread(target=self.speak_response, args=(response,), daemon=True).start()

    def generate_ai_response(self, user_text):
        self.chat_history_ai.append({"role": "user", "content": user_text})
        try:
            chat_completion = self.client.chat.completions.create(
                messages=self.chat_history_ai,
                model="qwen/qwen3.8-27b",
                max_tokens=250,
                temperature=0.7
            )
            response = chat_completion.choices[0].message.content.strip()
            self.chat_history_ai.append({"role": "assistant", "content": response})
            if len(self.chat_history_ai) > 15:
                self.chat_history_ai = [self.chat_history_ai[0]] + self.chat_history_ai[-14:]
            
            # FIX: अब हम टेक्स्ट और ऑडियो दोनों को एक साथ तैयार करेंगे
            threading.Thread(target=self.prepare_audio_and_text, args=(response,), daemon=True).start()
            
        except Exception as e:
            Clock.schedule_once(lambda dt: self.add_chat_bubble("Sorry, API error.", "ai"), 0)
            Clock.schedule_once(lambda dt: self.change_robot_video("idle"), 0)
            self.user_input.disabled = False

    # यह नया फंक्शन पहले ऑडियो डाउनलोड करेगा
    def prepare_audio_and_text(self, text):
        clean_text = text.replace("❌", "").replace("✅", "").replace('"', '').replace('\n', ' ')
        filename = f"voice_{int(time.time())}.mp3"
        try:
            if self.current_voice_tld == 'co.in':
                voice = "en-IN-NeerjaNeural"
            elif self.current_voice_tld == 'co.uk':
                voice = "en-GB-SoniaNeural"
            else:
                voice = "en-US-AriaNeural"
                
            # ऑडियो फाइल बनने का इंतज़ार करें
            asyncio.run(edge_tts.Communicate(clean_text, voice).save(filename))
            
            # जब ऑडियो फाइल पूरी बन जाए, तब UI अपडेट करें
            if os.path.exists(filename):
                Clock.schedule_once(lambda dt: self.show_and_play(text, filename), 0)
            else:
                Clock.schedule_once(lambda dt: self.show_and_play(text, None), 0)
        except Exception as e:
            print("TTS API Error:", e)
            Clock.schedule_once(lambda dt: self.show_and_play(text, None), 0)

    def show_and_play(self, text, filename):
        self.add_chat_bubble(text, "ai")
        self.user_input.disabled = False
        
        # --- UNIVERSAL VIDEO MAGIC (For All Modes) ---
        import os
        text_lower = text.lower()
        video_found = False
        
        # Aap jab chahein yahan naye words add kar sakte hain
        magic_words = [
            # 🦁 Jungle Safari
            "lion", "elephant", "monkey", "tiger", "giraffe", "zebra",
            
            # 🚀 Space Explorer
            "earth", "moon", "sun", "mars", "alien", "star", "rocket",
            
            # 🛒 Supermarket Fun
            "apple", "banana", "toy", "milk", "chocolate", "tomato",
            
            # 🏠 My Home
            "bed", "chair", "table", "tv", "kitchen", "sofa"
        ]
        
        # AI ke text mein check karna ki koi magic word hai ya nahi
        for word in magic_words:
            # Agar word text mein hai AUR uska video folder mein majood hai
            if word in text_lower and os.path.exists(f"{word}.mp4"):
                self.vid_speaking.source = f"{word}.mp4"
                self.vid_idle.source = f"{word}.mp4"
                self.vid_speaking.state = 'play'
                self.vid_idle.state = 'play'
                video_found = True
                break  # Ek video milte hi searching rok dega
                
        # Agar koi word ya video nahi mila, toh default robot par wapas aa jayega
        if not video_found:
            self.set_robot_video_theme("robot")
        
        if filename:
            self.change_robot_video("speaking")
            self.play_human_voice(filename)
        else:
            self.change_robot_video("idle")

    def play_human_voice(self, filename):
        sound = SoundLoader.load(filename)
        if sound:
            sound.play()
            audio_length = sound.length if sound.length > 0 else 3.0
            Clock.schedule_once(lambda dt: self.finish_audio(filename, sound), audio_length + 0.5)
        else:
            self.change_robot_video("idle")

    def finish_audio(self, filename, sound_obj=None):
        self.change_robot_video("idle")
        if sound_obj:
            try:
                sound_obj.stop()
                sound_obj.unload()
            except:
                pass
        try:
            os.remove(filename)
        except:
            pass

# --- APP MANAGER (Modern KivyMD) ---
class AiTeacherApp(MDApp):
    def cleanup_audio(self):
        for f in glob.glob("voice_*.mp3"):
            try:
                os.remove(f)
            except:
                pass

    def build(self):
        # Premium Dark Theme Set Karna
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "LightBlue"
        
        self.cleanup_audio() 
        init_db() 
        user = get_user_profile() 
        
        sm = ScreenManager()
        profile_screen = ProfileScreen(name='profile')
        chat_screen = ChatScreen(name='chat')
        
        # --- NAYA ALPHABET SCREEN YAHAN ADD KIYA HAI ---
        alphabet_screen = AlphabetScreen(name='alphabet')
        
        sm.add_widget(profile_screen)
        sm.add_widget(chat_screen)
        sm.add_widget(alphabet_screen)
        
        if user:
            sm.current = 'chat'
            chat_screen.initialize_ai(user[1], user[2], user[3]) 
        else:
            sm.current = 'profile'
            
        return sm

    def on_stop(self):
        self.cleanup_audio()

if __name__ == '__main__':
    AiTeacherApp().run()