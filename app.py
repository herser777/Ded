import os
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from collections import deque
from datetime import datetime

app = Flask(__name__)

# Настройки (Замените на свои, если деплоите на Render)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
GROQ_MODEL = "llama-3.3-70b-versatile"
CHATS_FILE = "chats.json"

# --- Логика сервера (Оставляем как есть, она работает) ---
def load_chats():
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_chats(data):
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

user_contexts = {}

BASE_PROMPT = """Твоя роль: Пошлый, агрессивный, нецензурный, старый 'Пошлый дед 👴'. 
ГЛАВНЫЕ ПРАВИЛА: 
1. Отвечай коротко (1-2 фразы). 
2. Используй мат и грубые оскорбления. 
3. Тон: смесь пошлости и неадекватности. 
4. Только русский язык."""

def call_groq(messages):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.9, "max_tokens": 300},
        timeout=20
    )
    if resp.status_code != 200:
        return "Пиздец, инет отвалился. Попробуй еще раз."
    return resp.json()["choices"][0]["message"]["content"].strip()

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    session_id = data.get("session_id", "default")
    message = data.get("message", "").strip()
    
    if not message: return jsonify({"error": "empty"}), 400
    
    if session_id not in user_contexts:
        user_contexts[session_id] = deque(maxlen=10)
    
    ctx = user_contexts[session_id]
    messages = [{"role": "system", "content": BASE_PROMPT}]
    for m in ctx: messages.append(m)
    messages.append({"role": "user", "content": message})
    
    reply = call_groq(messages)
    
    ctx.append({"role": "user", "content": message})
    ctx.append({"role": "assistant", "content": reply})
    
    # Сохранение для истории
    chats = load_chats()
    if session_id not in chats: chats[session_id] = {"messages": []}
    chats[session_id]["messages"].append({"role": "user", "content": message})
    chats[session_id]["messages"].append({"role": "assistant", "content": reply})
    save_chats(chats)
    
    return jsonify({"reply": reply})

# --- АХУЕННЫЙ ИНТЕРФЕЙС С АНИМАЦИЯМИ ---
HTML = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Пошлый Дед 👴🔥</title>
    <style>
        :root {
            --bg-color: #080b10;
            --header-bg: rgba(23, 33, 43, 0.85);
            --input-bg: rgba(36, 47, 61, 0.9);
            --user-bubble: linear-gradient(135deg, #3a7bd5 0%, #00d2ff 100%);
            --bot-bubble: #182533;
            --text-color: #f5f5f5;
            --accent-blue: #00d2ff;
            --shadow: 0 4px 15px rgba(0,0,0,0.3);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png');
            background-attachment: fixed;
            color: var(--text-color);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Анимации Глобальные */
        @keyframes slideIn {
            from { transform: translateY(20px) scale(0.9); opacity: 0; }
            to { transform: translateY(0) scale(1); opacity: 1; }
        }
        @keyframes pulseTyping {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; transform: scale(1.05); }
        }

        /* Header (Glassmorphism) */
        header {
            background: var(--header-bg);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 10px 15px;
            display: flex;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            z-index: 10;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        .avatar {
            width: 45px; height: 45px;
            border-radius: 50%;
            background: #2c3e50;
            margin-right: 15px;
            display: flex; align-items: center; justify-content: center;
            font-size: 24px;
            border: 2px solid rgba(255,255,255,0.1);
        }
        .header-info h1 { font-size: 17px; margin: 0; font-weight: 600; }
        .header-info span { font-size: 13px; color: var(--accent-blue); font-weight: 500; }

        /* Chat Area */
        #chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px 15px 90px 15px; /* Зазор снизу для плавающей панели */
            display: flex;
            flex-direction: column;
            gap: 12px;
            scroll-behavior: smooth;
        }
        
        /* Исправление вертикального текста + Анимация появления */
        .bubble-container {
            display: flex;
            width: 100%;
            animation: slideIn 0.3s ease-out forwards;
        }
        
        .bubble {
            max-width: 80%;
            padding: 10px 14px;
            font-size: 15px;
            line-height: 1.4;
            position: relative;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: normal;
            white-space: pre-wrap;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }
        
        .user-container { justify-content: flex-end; }
        .user { 
            background: var(--user-bubble); 
            color: white;
            border-radius: 16px 16px 4px 16px; 
        }
        
        .bot-container { justify-content: flex-start; }
        .bot { 
            background: var(--bot-bubble); 
            border-radius: 16px 16px 16px 4px; 
            border: 1px solid rgba(255,255,255,0.03);
        }

        /* Вспомогательные элементы (время) */
        .time {
            font-size: 10px;
            opacity: 0.6;
            margin-top: 4px;
            display: block;
            text-align: right;
        }

        /* Индикатор набора Деда */
        #typing-indicator {
            align-self: flex-start;
            color: var(--accent-blue);
            font-size: 13px;
            font-style: italic;
            margin-left: 10px;
            display: none; /* Скрыт по умолчанию */
            animation: pulseTyping 1s infinite;
        }

        /* Input Area (Плавающая, Glassmorphism) */
        .input-form-container {
            position: fixed;
            bottom: 15px;
            left: 50%;
            transform: translateX(-50%);
            width: 95%;
            max-width: 600px;
            z-index: 10;
        }

        .input-area {
            background: var(--input-bg);
            backdrop-filter: blur(15px);
            -webkit-backdrop-filter: blur(15px);
            padding: 8px 8px 8px 15px;
            display: flex;
            gap: 10px;
            align-items: center;
            border-radius: 30px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.4);
            border: 1px solid rgba(255,255,255,0.05);
        }
        
        input {
            flex: 1;
            background: transparent;
            border: none;
            padding: 10px 0;
            color: white;
            font-size: 16px;
        }
        
        button {
            background: var(--accent-blue);
            border: none;
            color: #000;
            font-weight: bold;
            cursor: pointer;
            font-size: 14px;
            width: 40px; height: 40px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            transition: transform 0.2s ease, background 0.2s ease;
        }
        
        button:hover {
            background: white;
            transform: scale(1.05);
        }
        
        button:active {
            transform: scale(0.95);
        }

        /* Красивый скроллбар */
        #chat-container::-webkit-scrollbar { width: 4px; }
        #chat-container::-webkit-scrollbar-track { background: transparent; }
        #chat-container::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
    </style>
</head>
<body>
    <header>
        <div class="avatar">👴</div>
        <div class="header-info">
            <h1>Пошлый Дед</h1>
            <span>строчит хуйню... ⚡️</span>
        </div>
    </header>

    <div id="chat-container">
        <div class="bubble-container bot-container" style="animation: none;">
            <div class="bubble bot">
                Че приперся, щегол? Сигарета есть? Пиши че надо.
                <span class="time">только что</span>
            </div>
        </div>
        <div id="typing-indicator">Дед строчит... 👴🔥</div>
    </div>

    <div class="input-form-container">
        <div class="input-area">
            <input type="text" id="msg-input" placeholder="Спроси херню..." autocomplete="off">
            <button onclick="send()" id="send-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
            </button>
        </div>
    </div>

    <script>
        const input = document.getElementById('msg-input');
        const container = document.getElementById('chat-container');
        const typingIndicator = document.getElementById('typing-indicator');
        const sid = Math.random().toString(36).substring(7);

        function getCurrentTime() {
            const now = new Date();
            return now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
        }

        function addBubble(text, isUser) {
            const wrap = document.createElement('div');
            wrap.className = `bubble-container ${isUser ? 'user-container' : 'bot-container'}`;
            
            const b = document.createElement('div');
            b.className = `bubble ${isUser ? 'user' : 'bot'}`;
            
            // Текст + Время
            b.innerHTML = text.replace(/\n/g, '<br>') + `<span class="time">${getCurrentTime()}</span>`;
            
            wrap.appendChild(b);
            // Добавляем ПЕРЕД индикатором набора
            container.insertBefore(wrap, typingIndicator);
            
            // Скролл вниз
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 50);
        }

        function showTyping(show) {
            typingIndicator.style.display = show ? 'block' : 'none';
            if(show) container.scrollTop = container.scrollHeight;
        }

        async function send() {
            const text = input.value.trim();
            if(!text) return;
            
            input.value = '';
            addBubble(text, true); // Добавить сообщение юзера
            
            showTyping(true); // Показать, что дед думает

            try {
                const r = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text, session_id: sid})
                });
                const d = await r.json();
                
                showTyping(false); // Скрыть набор
                
                if (d.reply) {
                    addBubble(d.reply, false); // Добавить ответ деда
                } else {
                    addBubble('Дед поперхнулся, пиздец.', false);
                }
            } catch(e) {
                showTyping(false);
                addBubble('Ошибка связи с дедом. Глобальный пиздец.', false);
            }
        }

        input.addEventListener('keypress', (e) => {
            if(e.key === 'Enter') send();
        });
        
        // Фокус на инпуте при загрузке (для десктопа)
        if(!('ontouchstart' in window)) {
            input.focus();
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    # Для деплоя на Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
