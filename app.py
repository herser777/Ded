import os
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from collections import deque

app = Flask(__name__)

GROQ_API_KEY = "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"
GROQ_MODEL = "llama-3.3-70b-versatile"
CONFIG_FILE = "config.json"
CHATS_FILE = "chats.json"
MEMORY_FILE = "ded_longmem.json"
ADMIN_PASSWORD = "1234"

# ─── ДОЛГОСРОЧНАЯ ПАМЯТЬ ─────────────────────────────────────────────────────

def load_longmem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_longmem(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def make_summary_for_memory(messages):
    if len(messages) < 4:
        return None
    dialog = "\n".join(
        ("Молодой" if m["role"] == "user" else "Дед") + ": " + m["content"]
        for m in messages
    )
    try:
        config = load_config()
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + config.get("api_key", GROQ_API_KEY), "Content-Type": "application/json"},
            json={
                "model": config.get("model", GROQ_MODEL),
                "messages": [
                    {"role": "system", "content": "Ты делаешь краткое резюме разговора. Отвечай ТОЛЬКО на русском. 2-3 предложения: о чём говорили, что важного сказал человек о себе."},
                    {"role": "user", "content": "Краткое резюме:\n\n" + dialog}
                ],
                "temperature": 0.3,
                "max_tokens": 150
            },
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except:
        pass
    return None

def compress_context(messages):
    if len(messages) <= 20:
        return messages
    old_msgs = messages[:10]
    new_msgs = messages[10:]
    dialog = "\n".join(
        ("Молодой" if m["role"] == "user" else "Дед") + ": " + m["content"]
        for m in old_msgs
    )
    try:
        config = load_config()
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + config.get("api_key", GROQ_API_KEY), "Content-Type": "application/json"},
            json={
                "model": config.get("model", GROQ_MODEL),
                "messages": [
                    {"role": "system", "content": "Сожми разговор в резюме (3-4 предложения). Только русский язык."},
                    {"role": "user", "content": dialog}
                ],
                "temperature": 0.3,
                "max_tokens": 200
            },
            timeout=15
        )
        if resp.status_code == 200:
            summary = resp.json()["choices"][0]["message"]["content"].strip()
            compressed = [{"role": "user", "content": "[Резюме начала: " + summary + "]"},
                         {"role": "assistant", "content": "Ну и хрен с ним, продолжай."}]
            return compressed + new_msgs
    except:
        pass
    return messages[-20:]

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"api_key": GROQ_API_KEY, "model": GROQ_MODEL}

def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_chats():
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_chats(data):
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

user_contexts = {}

BASE_PROMPT = """Ты старый пошлый дед. Тебе за семьдесят, спина болит, всё надоело, людей не уважаешь.

Говоришь коротко и грубо. Максимум три предложения. Маты — часть твоей речи, не украшение. Пошлость — твоя картина мира, не приём. Абсурд — твоя логика, ты в неё веришь.

Ты не помогаешь, не поддерживаешь, не объясняешь себя. Если тебя спросили — отвечаешь как хочешь. Если тебя обидели — тебе плевать, ты видел хуже.

Никогда не пиши длинно. Никогда не извиняйся. Никогда не говори как бот.

ТОЛЬКО русский язык. Только кириллица."""

MODE_ADDITIONS = {
    "normal": "",
    "yarost": """\n\nТы сейчас не просто груб — ты унижаешь. Тебе не важно что там у человека за проблема, важно дать ему почувствовать себя идиотом. Не помогаешь. Не советуешь. Топчешь и уходишь.""",
    "sovet": """\n\nЧеловек хочет совета. Дай его — по-своему, криво, абсурдно, но как будто это единственная правда на свете. Ты в неё веришь.""",
    "predskazanie": """\n\nДай предсказание на сегодня. Ты пьяный оракул из деревни, тебе открыто то что другим нет. Предсказание абсурдное, пошлое, немного страшное.""",
    "pervyi": """\n\nНачни разговор сам. Без приветствий. Просто скажи что-то — пожалуйся, обратись, брякни что в голову пришло.""",
}

def call_groq(messages):
    config = load_config()
    api_key = config.get("api_key", GROQ_API_KEY)
    model = config.get("model", GROQ_MODEL)
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.92, "max_tokens": 400},
        timeout=25
    )
    if resp.status_code == 401:
        raise Exception("invalid_key")
    if resp.status_code != 200:
        raise Exception("api_error:" + resp.text[:200])
    return resp.json()["choices"][0]["message"]["content"].strip()

def get_context(session_id):
    if session_id not in user_contexts:
        user_contexts[session_id] = deque(maxlen=40)
    return user_contexts[session_id]

def build_messages(session_id, user_message, mode, topic):
    system = BASE_PROMPT + MODE_ADDITIONS.get(mode, "")
    if topic:
        system += "\n\n[Тема разговора: " + topic + ". Держись её, но по-своему.]"
    longmem = load_longmem()
    if session_id in longmem and longmem[session_id]:
        system += "\n\n[Помнишь этого: " + longmem[session_id] + "]"
    messages = [{"role": "system", "content": system}]
    ctx = list(get_context(session_id))
    if len(ctx) > 20:
        ctx = compress_context(ctx)
        user_contexts[session_id] = deque(ctx, maxlen=40)
    for msg in ctx:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    return messages

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    session_id = data.get("session_id", "default")
    message = data.get("message", "").strip()
    mode = data.get("mode", "normal")
    topic = data.get("topic", "")
    chat_id = data.get("chat_id", "default")
    if not message:
        return jsonify({"error": "empty"}), 400
    try:
        messages = build_messages(session_id, message, mode, topic)
        reply = call_groq(messages)
        ctx = get_context(session_id)
        ctx.append({"role": "user", "content": message})
        ctx.append({"role": "assistant", "content": reply})
        chats = load_chats()
        if chat_id not in chats:
            chats[chat_id] = {"title": message[:40], "messages": []}
        chats[chat_id]["messages"].append({"role": "user", "content": message})
        chats[chat_id]["messages"].append({"role": "assistant", "content": reply})
        save_chats(chats)
        ctx_now = list(get_context(session_id))
        if len(ctx_now) % 6 == 0 and len(ctx_now) >= 6:
            summary = make_summary_for_memory(ctx_now)
            if summary:
                longmem = load_longmem()
                longmem[session_id] = summary
                save_longmem(longmem)
        return jsonify({"reply": reply})
    except Exception as e:
        err = str(e)
        if "invalid_key" in err:
            return jsonify({"error": "invalid_key"}), 401
        return jsonify({"error": err}), 500

@app.route("/retry", methods=["POST"])
def retry():
    data = request.json
    session_id = data.get("session_id", "default")
    mode = data.get("mode", "normal")
    topic = data.get("topic", "")
    chat_id = data.get("chat_id", "default")
    ctx = get_context(session_id)
    lst = list(ctx)
    last_user = None
    if lst and lst[-1]["role"] == "assistant":
        lst.pop()
    if lst and lst[-1]["role"] == "user":
        last_user = lst.pop()["content"]
    user_contexts[session_id] = deque(lst, maxlen=20)
    if not last_user:
        return jsonify({"error": "no_message"}), 400
    try:
        messages = build_messages(session_id, last_user, mode, topic)
        reply = call_groq(messages)
        ctx2 = get_context(session_id)
        ctx2.append({"role": "user", "content": last_user})
        ctx2.append({"role": "assistant", "content": reply})
        return jsonify({"reply": reply})
    except Exception as e:
        err = str(e)
        if "invalid_key" in err:
            return jsonify({"error": "invalid_key"}), 401
        return jsonify({"error": err}), 500

@app.route("/summary", methods=["POST"])
def summary():
    data = request.json
    session_id = data.get("session_id", "default")
    ctx = get_context(session_id)
    if len(ctx) < 2:
        return jsonify({"reply": "Да ни о чём мы ещё не говорили, чё итожить-то."})
    dialog = "\n".join(
        ("Ты" if m["role"] == "user" else "Дед") + ": " + m["content"]
        for m in ctx
    )
    try:
        reply = call_groq([
            {"role": "system", "content": BASE_PROMPT},
            {"role": "user", "content": "Подведи итог нашего разговора по-дедовски:\n\n" + dialog}
        ])
        return jsonify({"reply": "📜 Итог деда:\n\n" + reply})
    except:
        return jsonify({"reply": "Пиздец, забыл о чём говорили."})

@app.route("/clear", methods=["POST"])
def clear():
    session_id = request.json.get("session_id", "default")
    user_contexts.pop(session_id, None)
    return jsonify({"ok": True})

@app.route("/chats", methods=["GET"])
def get_chats():
    return jsonify(load_chats())

@app.route("/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    chats = load_chats()
    chats.pop(chat_id, None)
    save_chats(chats)
    return jsonify({"ok": True})

@app.route("/update_key", methods=["POST"])
def update_key():
    key = request.json.get("key", "").strip()
    if not key:
        return jsonify({"error": "empty"}), 400
    config = load_config()
    config["api_key"] = key
    save_config(config)
    return jsonify({"ok": True})

@app.route("/share/<chat_id>")
def share_chat(chat_id):
    chats = load_chats()
    chat = chats.get(chat_id)
    if not chat:
        return "Разговор не найден", 404
    msgs = chat.get("messages", [])
    title = chat.get("title", "Разговор с Дедом")
    lines = []
    for m in msgs:
        who = "Ты" if m["role"] == "user" else "Дед"
        cls = "user-msg" if m["role"] == "user" else "bot-msg"
        lines.append('<div class="msg {}"><span class="who">{}</span><div class="txt">{}</div></div>'.format(
            cls, who, m["content"].replace("<","&lt;").replace(">","&gt;")))
    dialog_html = "".join(lines)
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + title + """ — Пошлый Дед</title>
<link href="https://fonts.googleapis.com/css2?family=Russo+One&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1008;color:#e8d5b0;font-family:'PT Serif',serif;min-height:100vh;padding:20px}
h1{font-family:'Russo One',sans-serif;color:#d4813a;font-size:22px;letter-spacing:2px;margin-bottom:6px}
.sub{color:#8a6a3a;font-size:13px;margin-bottom:24px}
.msg{margin-bottom:16px;display:flex;flex-direction:column;gap:4px}
.who{font-family:'Russo One',sans-serif;font-size:10px;letter-spacing:2px;color:#8a6a3a}
.user-msg .who{color:#d4813a;text-align:right}
.txt{padding:12px 16px;border-radius:12px;font-size:15px;line-height:1.6;max-width:85%}
.user-msg .txt{background:rgba(212,129,58,0.12);border:1px solid rgba(212,129,58,0.25);margin-left:auto;border-bottom-right-radius:3px}
.bot-msg .txt{background:rgba(255,255,255,0.04);border:1px solid rgba(212,129,58,0.1);border-bottom-left-radius:3px}
.footer{color:#4a3a22;font-size:12px;text-align:center;margin-top:30px}
</style></head><body>
<h1>💬 ПОШЛЫЙ ДЕД</h1>
<div class="sub">Запись разговора</div>
""" + dialog_html + """
<div class="footer">poshlyi-ded.onrender.com</div>
</body></html>"""

@app.route("/watch")
def watch():
    pwd = request.args.get("p", "")
    if pwd != ADMIN_PASSWORD:
        return """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{background:#1a1008;color:#e8d5b0;font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{background:#111;border:1px solid rgba(212,129,58,0.2);border-radius:16px;padding:28px;width:90%;max-width:320px;text-align:center}
h2{color:#d4813a;margin-bottom:20px;font-size:15px;letter-spacing:2px}
input{width:100%;background:rgba(255,255,255,0.05);color:#e8d5b0;border:1px solid rgba(212,129,58,0.2);border-radius:8px;padding:10px;font-size:16px;margin-bottom:12px;outline:none}
button{width:100%;background:#d4813a;color:#1a1008;border:none;border-radius:8px;padding:11px;font-size:15px;cursor:pointer}
</style></head><body>
<div class="box"><h2>НАБЛЮДЕНИЕ</h2>
<form onsubmit="event.preventDefault();location.href='/watch?p='+document.getElementById('p').value">
<input type="password" id="p" placeholder="Пароль" autofocus>
<button type="submit">Войти</button>
</form></div></body></html>"""

    chats = load_chats()
    total_msgs = sum(len(c.get("messages", [])) for c in chats.values())
    total_chats = len(chats)
    rows = ""
    for cid in sorted(chats.keys(), reverse=True):
        chat = chats[cid]
        msgs = chat.get("messages", [])
        if not msgs:
            continue
        title = chat.get("title", "Разговор")[:35]
        count = str(len(msgs) // 2)
        last_m = msgs[-1]
        last_who = "Дед" if last_m["role"] == "assistant" else "Юзер"
        last_txt = last_m["content"][:60]
        rows += '<tr data-cid="' + cid + '" class="chat-row"><td>' + title + '</td><td>' + count + '</td><td>' + last_who + ': ' + last_txt + '</td></tr>\n'

    import json as _json
    chats_data = _json.dumps(chats, ensure_ascii=False)

    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Наблюдение</title>
<link href="https://fonts.googleapis.com/css2?family=Russo+One&family=PT+Serif&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1008;color:#e8d5b0;font-family:'PT Serif',serif;height:100dvh;display:flex;flex-direction:column}
#top{background:#110c05;border-bottom:1px solid rgba(212,129,58,0.2);padding:12px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}
#top h1{font-family:'Russo One',sans-serif;color:#d4813a;font-size:14px;letter-spacing:2px;flex:1}
.stat{color:rgba(232,213,176,0.4);font-size:12px}
#wrap{display:flex;flex:1;overflow:hidden}
#list{width:300px;border-right:1px solid rgba(212,129,58,0.1);overflow-y:auto;flex-shrink:0}
table{width:100%;border-collapse:collapse}
.chat-row{border-bottom:1px solid rgba(212,129,58,0.06);cursor:pointer}
.chat-row:hover{background:rgba(212,129,58,0.06)}
.chat-row.active{background:rgba(212,129,58,0.12)}
td{padding:10px 12px;font-size:13px;vertical-align:top}
td:nth-child(2){color:#d4813a;font-size:11px;white-space:nowrap;text-align:right}
td:nth-child(3){color:rgba(232,213,176,0.45);font-size:12px}
#view{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
.empty{color:rgba(232,213,176,0.25);text-align:center;margin-top:50px;font-style:italic}
.bubble{display:flex;flex-direction:column;gap:2px}
.bubble.user{align-items:flex-end}
.bubble.bot{align-items:flex-start}
.bwho{font-family:'Russo One',sans-serif;font-size:9px;color:#d4813a;letter-spacing:2px;padding:0 3px}
.btxt{max-width:85%;padding:9px 13px;border-radius:13px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.bubble.user .btxt{background:rgba(212,129,58,0.13);border:1px solid rgba(212,129,58,0.22);border-bottom-right-radius:3px}
.bubble.bot .btxt{background:rgba(255,255,255,0.04);border:1px solid rgba(212,129,58,0.08);border-bottom-left-radius:3px}
.rbtn{background:rgba(212,129,58,0.1);border:1px solid rgba(212,129,58,0.25);color:#d4813a;border-radius:7px;padding:5px 12px;font-size:12px;cursor:pointer}
a{color:rgba(232,213,176,0.4);font-size:12px;text-decoration:none}
</style></head><body>
<div id="top"><h1>👁 НАБЛЮДЕНИЕ</h1>
<span class="stat">""" + str(total_chats) + """ разговоров · """ + str(total_msgs) + """ сообщений</span>
<button class="rbtn" onclick="location.reload()">↻</button>
<a href="/admin?p=1234">← Назад</a></div>
<div id="wrap"><div id="list"><table id="tbl">""" + rows + """</table></div>
<div id="view"><div class="empty">Выбери разговор</div></div></div>
<script>
const D = """ + chats_data + """;
document.querySelectorAll(".chat-row").forEach(function(row){
  row.addEventListener("click",function(){
    document.querySelectorAll(".chat-row").forEach(function(r){r.classList.remove("active")});
    row.classList.add("active");
    var cid=row.getAttribute("data-cid");
    var chat=D[cid];
    var view=document.getElementById("view");
    view.innerHTML="";
    if(!chat||!chat.messages)return;
    chat.messages.forEach(function(m){
      var d=document.createElement("div");
      d.className="bubble "+(m.role==="user"?"user":"bot");
      var who=document.createElement("div");
      who.className="bwho";
      who.textContent=m.role==="user"?"ЮЗЕР":"ДЕД";
      var txt=document.createElement("div");
      txt.className="btxt";
      txt.textContent=m.content;
      d.appendChild(who);d.appendChild(txt);
      view.appendChild(d);
    });
    view.scrollTop=view.scrollHeight;
  });
});
setTimeout(function(){location.reload()},20000);
</script></body></html>"""

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd != ADMIN_PASSWORD:
            return render_template_string(ADMIN_LOGIN, error="Неверный пароль")
        config = load_config()
        new_key = request.form.get("api_key", "").strip()
        new_model = request.form.get("model", "").strip()
        if new_key:
            config["api_key"] = new_key
        if new_model:
            config["model"] = new_model
        save_config(config)
        return render_template_string(ADMIN_PANEL, config=config, saved=True)
    pwd = request.args.get("p", "")
    if pwd == ADMIN_PASSWORD:
        config = load_config()
        return render_template_string(ADMIN_PANEL, config=config, saved=False)
    return render_template_string(ADMIN_LOGIN, error="")

ADMIN_LOGIN = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Настройки</title>
<link href="https://fonts.googleapis.com/css2?family=Russo+One&family=PT+Serif&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1008;color:#e8d5b0;font-family:'PT Serif',serif;display:flex;align-items:center;justify-content:center;height:100vh}
.box{background:rgba(15,10,3,0.95);border:1px solid rgba(212,129,58,0.2);border-radius:20px;padding:32px;width:90%;max-width:340px}
h2{font-family:'Russo One',sans-serif;color:#d4813a;margin-bottom:24px;text-align:center;letter-spacing:3px;font-size:15px}
input{width:100%;background:rgba(255,255,255,0.05);color:#e8d5b0;border:1px solid rgba(212,129,58,0.2);border-radius:10px;padding:12px 16px;font-size:16px;margin-bottom:14px;font-family:'PT Serif',serif;outline:none}
input:focus{border-color:#d4813a}
button{width:100%;background:#d4813a;color:#1a1008;border:none;border-radius:10px;padding:12px;font-size:16px;font-family:'Russo One',sans-serif;cursor:pointer;letter-spacing:1px}
.err{color:#ff6b6b;font-size:13px;margin-bottom:12px;text-align:center}
</style></head><body>
<div class="box">
<h2>НАСТРОЙКИ</h2>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="POST">
<input type="password" name="password" placeholder="Пароль" autofocus>
<button type="submit">ВОЙТИ</button>
</form>
</div></body></html>"""

ADMIN_PANEL = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Настройки</title>
<link href="https://fonts.googleapis.com/css2?family=Russo+One&family=PT+Serif&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1008;color:#e8d5b0;font-family:'PT Serif',serif;padding:20px}
.box{background:rgba(15,10,3,0.95);border:1px solid rgba(212,129,58,0.2);border-radius:20px;padding:28px;max-width:500px;margin:0 auto}
h2{font-family:'Russo One',sans-serif;color:#d4813a;margin-bottom:8px;letter-spacing:3px;font-size:15px}
p{color:rgba(232,213,176,0.5);font-size:14px;margin-bottom:24px;line-height:1.5}
label{display:block;color:#d4813a;font-size:11px;letter-spacing:2px;margin-bottom:6px;font-family:'Russo One',sans-serif}
input{width:100%;background:rgba(255,255,255,0.05);color:#e8d5b0;border:1px solid rgba(212,129,58,0.2);border-radius:10px;padding:10px 14px;font-size:14px;margin-bottom:20px;font-family:'PT Serif',serif;outline:none}
input:focus{border-color:#d4813a}
button{width:100%;background:#d4813a;color:#1a1008;border:none;border-radius:10px;padding:12px;font-size:15px;font-family:'Russo One',sans-serif;cursor:pointer;letter-spacing:1px}
.ok{color:#6bff9e;text-align:center;margin-bottom:16px;font-size:14px}
a{display:block;text-align:center;margin-top:16px;color:rgba(232,213,176,0.4);text-decoration:none;font-size:14px}
a:hover{color:#d4813a}
</style></head><body>
<div class="box">
<h2>НАСТРОЙКИ</h2>
<p>Смени ключ API если перестал работать.</p>
{% if saved %}<div class="ok">✓ Сохранено!</div>{% endif %}
<form method="POST">
<input type="hidden" name="password" value="1234">
<label>API КЛЮЧ</label>
<input type="text" name="api_key" value="{{ config.api_key }}">
<label>МОДЕЛЬ</label>
<input type="text" name="model" value="{{ config.model }}">
<button type="submit">СОХРАНИТЬ</button>
</form>
<a href="/watch?p=1234" style="margin-top:8px;background:rgba(212,129,58,0.1);border:1px solid rgba(212,129,58,0.3);border-radius:10px;padding:12px;text-align:center;color:#d4813a;display:block;text-decoration:none;font-family:'Russo One',sans-serif;font-size:13px;letter-spacing:1px">👁 Наблюдать за разговорами</a>
<a href="/">← Вернуться к Деду</a>
</div></body></html>"""

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<meta name="theme-color" content="#1a1310">
<title>Пошлый Дед</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#1a1310;
  --bg2:#211915;
  --bg3:#2a1f1a;
  --orange:#d4813a;
  --orange-dim:rgba(212,129,58,0.35);
  --orange-glow:rgba(212,129,58,0.10);
  --red:#c0392b;
  --red-dim:rgba(192,57,43,0.18);
  --text:#ede0cc;
  --text-dim:rgba(237,224,204,0.45);
  --text-muted:rgba(237,224,204,0.28);
  --bubble-ded:rgba(55,35,22,0.95);
  --bubble-user:rgba(80,52,30,0.85);
  --border:rgba(255,255,255,0.06);
  --glass:rgba(26,19,16,0.85);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);height:100dvh;display:flex;flex-direction:column}

/* HEADER — telegram style */
#hdr{
  display:flex;align-items:center;gap:12px;
  padding:10px 16px;height:60px;flex-shrink:0;
  background:rgba(26,19,16,0.92);
  backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  position:relative;z-index:10;
}
#menu-btn{background:none;border:none;color:var(--text-dim);font-size:22px;cursor:pointer;padding:4px;line-height:1}
#hdr-avatar{
  width:42px;height:42px;border-radius:50%;flex-shrink:0;
  background:var(--bg3);
  border:2px solid var(--orange-dim);
  overflow:hidden;cursor:pointer;position:relative;
}
#hdr-avatar img{width:100%;height:100%;object-fit:cover;object-position:center 20%}
#online-dot{
  position:absolute;bottom:1px;right:1px;
  width:10px;height:10px;border-radius:50%;
  background:#4cd964;border:2px solid var(--bg);
}
#hdr-info{flex:1;min-width:0}
#hdr-name{font-size:16px;font-weight:600;color:var(--text);letter-spacing:0.2px;line-height:1.2}
#hdr-status{font-size:12px;color:var(--orange);line-height:1.2;font-weight:400}
#mode-btn{
  background:none;border:1px solid rgba(212,129,58,0.22);border-radius:20px;
  padding:6px 14px;font-family:'Inter',sans-serif;font-size:11px;font-weight:500;
  color:var(--text-dim);cursor:pointer;transition:all 0.2s;white-space:nowrap;
  letter-spacing:0.3px;
}
#mode-btn:hover{color:var(--orange);border-color:rgba(212,129,58,0.4);background:var(--orange-glow)}
#mode-btn.yarost{border-color:rgba(192,57,43,0.35);color:rgba(220,80,70,0.7)}
#mode-btn.yarost:hover{color:#e05555;border-color:rgba(192,57,43,0.55);background:var(--red-dim)}

/* SIDEBAR */
#sidebar{
  position:fixed;top:0;left:0;bottom:0;z-index:50;width:260px;
  background:rgba(20,14,11,0.97);backdrop-filter:blur(24px);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;
  transform:translateX(-100%);transition:transform 0.28s cubic-bezier(.4,0,.2,1);
}
#sidebar.open{transform:translateX(0)}
#sidebar-head{padding:18px 16px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
#sidebar-head span{flex:1;font-size:11px;font-weight:600;color:var(--orange);letter-spacing:3px;text-transform:uppercase}
#btn-new{background:none;color:var(--text-dim);border:1px solid var(--border);border-radius:7px;width:28px;height:28px;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s}
#btn-new:hover{color:var(--orange);border-color:var(--orange-dim)}
#chats-list{flex:1;overflow-y:auto;padding:6px}
.ci{padding:10px 12px;border-radius:10px;cursor:pointer;font-size:13px;color:var(--text-dim);display:flex;align-items:center;gap:9px;margin-bottom:1px;transition:all 0.15s}
.ci:hover{background:var(--orange-glow);color:var(--text)}
.ci.active{background:rgba(212,129,58,0.12);color:var(--orange)}
.ci-txt{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ci-del{opacity:0;font-size:12px;color:#555;padding:2px 5px}
.ci:hover .ci-del{opacity:1}
.ci-del:hover{color:#e05555}
#sidebar-foot{padding:10px 14px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:1px}
#sidebar-foot a{color:var(--text-muted);font-size:12px;text-decoration:none;display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:8px;transition:all 0.15s;letter-spacing:0.3px}
#sidebar-foot a:hover{background:var(--orange-glow);color:var(--orange)}
#sov{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:40;backdrop-filter:blur(2px)}
#sov.show{display:block}

/* CHAT AREA */
#chat-wrap{flex:1;overflow-y:auto;padding:12px 0 4px}
#chat{max-width:680px;margin:0 auto;padding:8px 16px;display:flex;flex-direction:column;gap:6px;min-height:100%}

/* WELCOME */
#welcome{display:flex;flex-direction:column;align-items:center;padding:36px 16px 20px;gap:20px;text-align:center}
#w-avatar{
  width:88px;height:88px;border-radius:50%;overflow:hidden;
  border:3px solid var(--orange-dim);
  box-shadow:0 0 40px rgba(212,129,58,0.2);
  animation:pulse-av 3s ease-in-out infinite;
}
#w-avatar img{width:100%;height:100%;object-fit:cover;object-position:center 20%}
@keyframes pulse-av{0%,100%{box-shadow:0 0 30px rgba(212,129,58,0.15)}50%{box-shadow:0 0 55px rgba(212,129,58,0.3)}}
#welcome h1{font-family:'Inter',sans-serif;font-size:26px;font-weight:700;color:var(--orange);letter-spacing:1px}
#welcome p{color:var(--text-dim);font-style:italic;font-size:14px;max-width:300px;line-height:1.7;font-family:'PT Serif',serif}
.qbtns{display:flex;flex-direction:column;gap:8px;width:100%;max-width:380px}
.qbtn{
  background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
  border-radius:14px;padding:13px 18px;color:var(--text-dim);
  font-size:14px;font-family:'Inter',sans-serif;cursor:pointer;text-align:left;
  display:flex;align-items:center;gap:14px;transition:all 0.22s;
}
.qbtn:hover{background:var(--orange-glow);border-color:rgba(212,129,58,0.25);color:var(--text);transform:translateX(3px)}
.qbtn.qbtn-danger{border-color:rgba(192,57,43,0.18)}
.qbtn.qbtn-danger:hover{background:var(--red-dim);border-color:rgba(192,57,43,0.35)}
.qbtn-icon{font-size:20px;flex-shrink:0}

/* BUBBLES */
.bubble{display:flex;flex-direction:column;gap:2px;animation:fi 0.2s ease;max-width:100%}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1}}
.bubble.user{align-items:flex-end}
.bubble.bot{align-items:flex-start}

.brow{display:flex;align-items:flex-end;gap:8px}
.bubble.user .brow{flex-direction:row-reverse}

.bavatar{width:32px;height:32px;border-radius:50%;overflow:hidden;flex-shrink:0;border:1px solid var(--orange-dim)}
.bavatar img{width:100%;height:100%;object-fit:cover;object-position:center 20%}

.btxt{
  max-width:78%;padding:10px 14px;
  font-size:15px;line-height:1.58;
  white-space:pre-wrap;word-break:break-word;
  position:relative;
}
/* DED bubble */
.bubble.bot .btxt{
  background:var(--bubble-ded);
  border:1px solid rgba(212,129,58,0.12);
  border-radius:18px 18px 18px 4px;
  font-family:'PT Serif',serif;font-size:15.5px;
  box-shadow:0 2px 12px rgba(0,0,0,0.35);
}
/* USER bubble */
.bubble.user .btxt{
  background:var(--bubble-user);
  border:1px solid rgba(212,129,58,0.18);
  border-radius:18px 18px 4px 18px;
  font-family:'Inter',sans-serif;font-size:14.5px;
  box-shadow:0 2px 12px rgba(0,0,0,0.25);
}
.bmeta{display:flex;gap:4px;padding:2px 4px;opacity:0;transition:opacity 0.15s}
.bubble:hover .bmeta{opacity:1}
.bubble.user .bmeta{justify-content:flex-end}
.bmeta-btn{background:none;border:none;color:var(--text-muted);font-size:13px;cursor:pointer;padding:2px 6px;border-radius:5px;transition:all 0.15s}
.bmeta-btn:hover{color:var(--orange);background:var(--orange-glow)}

/* TYPING */
.tdots{display:flex;gap:5px;padding:12px 16px;background:var(--bubble-ded);border:1px solid rgba(212,129,58,0.1);border-radius:18px 18px 18px 4px;align-items:center}
.dot{width:6px;height:6px;background:var(--orange);border-radius:50%;animation:pu 1.3s infinite;opacity:0.55}
.dot:nth-child(2){animation-delay:0.2s}
.dot:nth-child(3){animation-delay:0.4s}
@keyframes pu{0%,60%,100%{opacity:0.2;transform:scale(0.8)}30%{opacity:0.85;transform:scale(1.1)}}

/* INPUT AREA */
#inp-area{
  flex-shrink:0;background:rgba(20,14,11,0.92);
  backdrop-filter:blur(22px);border-top:1px solid var(--border);
  padding:10px 16px 16px;position:relative;z-index:3;
}
#inp-inner{max-width:680px;margin:0 auto}
#inp-row{display:flex;align-items:flex-end;gap:10px}
#plus-btn{
  width:40px;height:40px;border-radius:50%;flex-shrink:0;
  background:var(--bg3);border:1px solid var(--border);
  color:var(--text-dim);font-size:22px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  transition:all 0.2s;line-height:1;
}
#plus-btn:hover{background:var(--orange-glow);border-color:var(--orange-dim);color:var(--orange)}
#plus-btn.open{transform:rotate(45deg);color:var(--orange);border-color:var(--orange-dim)}
#inp-box{
  flex:1;display:flex;align-items:flex-end;
  background:var(--bg3);border:1px solid var(--border);
  border-radius:22px;padding:10px 16px;gap:8px;
  transition:border-color 0.2s;
}
#inp-box:focus-within{border-color:rgba(212,129,58,0.3)}
#msg{
  flex:1;background:none;border:none;outline:none;
  color:var(--text);font-size:15px;font-family:'Inter',sans-serif;
  resize:none;max-height:100px;line-height:1.5;
}
#msg::placeholder{color:var(--text-muted);font-style:italic}
#send{
  background:none;border:none;color:var(--orange);
  cursor:pointer;flex-shrink:0;padding:2px;transition:all 0.2s;opacity:0.6;
}
#send:hover{opacity:1;transform:scale(1.12)}
#send:disabled{opacity:0.18;cursor:default;transform:none}

/* DRAWER — menu from bottom */
#drawer-ov{display:none;position:fixed;inset:0;z-index:60;background:rgba(0,0,0,0.5);backdrop-filter:blur(3px)}
#drawer{
  position:fixed;left:12px;right:12px;bottom:12px;z-index:61;
  background:rgba(22,14,10,0.98);border:1px solid var(--border);
  border-radius:20px;overflow:hidden;
  transform:translateY(120%);transition:transform 0.3s cubic-bezier(.4,0,.2,1);
}
#drawer.open{transform:translateY(0)}
#drawer-title{
  padding:14px 20px 10px;text-align:center;
  font-size:11px;font-weight:600;letter-spacing:3px;color:var(--text-muted);
  text-transform:uppercase;border-bottom:1px solid var(--border);
}
.drow{
  display:flex;align-items:center;gap:14px;
  padding:15px 22px;cursor:pointer;
  border-bottom:1px solid var(--border);
  transition:background 0.15s;color:var(--text-dim);font-size:15px;
  font-family:'Inter',sans-serif;
}
.drow:last-child{border-bottom:none}
.drow:active{background:var(--orange-glow)}
.drow-icon{font-size:22px;width:28px;text-align:center}
.drow-label{flex:1;font-size:15px}
.drow-sub{font-size:12px;color:var(--text-muted)}
.drow.active-row{color:var(--orange)}
.drow.danger{color:rgba(220,80,70,0.75)}
.drow.danger:active{background:var(--red-dim)}
#drawer-cancel{
  padding:15px 20px;text-align:center;font-size:12px;font-weight:500;
  letter-spacing:2px;color:var(--text-muted);cursor:pointer;
  text-transform:uppercase;transition:color 0.15s;background:var(--bg);
}
#drawer-cancel:hover{color:var(--text-dim)}

/* OVERLAYS */
.ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.65);z-index:100;align-items:center;justify-content:center;backdrop-filter:blur(5px)}
.ov.show{display:flex}
.pop{background:rgba(18,12,9,0.98);backdrop-filter:blur(24px);border:1px solid var(--border);border-radius:18px;padding:24px;width:90%;max-width:360px}
.pop h3{font-family:'Inter',sans-serif;font-size:12px;font-weight:600;letter-spacing:3px;color:var(--orange);margin-bottom:16px;text-transform:uppercase}
.pop p{color:var(--text-muted);font-size:13px;margin-bottom:14px;line-height:1.7;font-style:italic}
.pop input,.pop textarea{width:100%;background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:11px 14px;font-size:14px;font-family:'Inter',sans-serif;margin-bottom:12px;outline:none}
.pop input:focus,.pop textarea:focus{border-color:rgba(212,129,58,0.4)}
.pbts{display:flex;gap:8px}
.pbts button{flex:1;padding:11px;border-radius:10px;border:none;font-size:12px;font-family:'Inter',sans-serif;cursor:pointer;letter-spacing:1px;text-transform:uppercase;font-weight:600}
.bok{background:rgba(212,129,58,0.88);color:#0c0700}
.bok:hover{background:var(--orange)}
.bno{background:rgba(255,255,255,0.05);color:var(--text-dim);border:1px solid var(--border)!important}

/* TOAST */
#toast{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:rgba(212,129,58,0.92);color:#0c0700;padding:7px 18px;border-radius:20px;font-size:11px;font-family:'Inter',sans-serif;font-weight:600;letter-spacing:1px;text-transform:uppercase;opacity:0;transition:opacity 0.25s;pointer-events:none;z-index:200}
#toast.show{opacity:1}

/* scrollbar */
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(212,129,58,0.18);border-radius:2px}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div id="sidebar-head">
    <span>ЧАТЫ</span>
    <button id="btn-new" onclick="newChat()" title="Новый">+</button>
  </div>
  <div id="chats-list"></div>
  <div id="sidebar-foot">
    <a href="#" onclick="doSummary()">📜 Итог разговора</a>
    <a href="#" onclick="showOv('ov-key')">🔑 API ключ</a>
    <a href="/admin?p=1234">⚙ Настройки</a>
  </div>
</div>
<div id="sov" onclick="closeSide()"></div>

<!-- HEADER -->
<div id="hdr">
  <button id="menu-btn" onclick="toggleSide()">☰</button>
  <div id="hdr-avatar" onclick="toggleSide()">
    <img src="data:image/jpeg;base64,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" alt="Дед">
    <div id="online-dot"></div>
  </div>
  <div id="hdr-info">
    <div id="hdr-name">Дед</div>
    <div id="hdr-status" id="hdr-status">в сети</div>
  </div>
  <button id="mode-btn" onclick="toggleDrawer()">
    <span id="mode-label">👴 Обычный</span>
  </button>
</div>

<!-- CHAT -->
<div id="chat-wrap"><div id="chat"></div></div>

<!-- INPUT -->
<div id="inp-area">
  <div id="inp-inner">
    <div id="inp-row">
      <button id="plus-btn" onclick="toggleDrawer()" title="Меню">+</button>
      <div id="inp-box">
        <textarea id="msg" placeholder="Напиши деду..." rows="1"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}"
          oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'"></textarea>
        <button id="send" onclick="sendMsg()">
          <svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/></svg>
        </button>
      </div>
    </div>
  </div>
</div>

<!-- OVERLAYS -->
<div id="ov-key" class="ov" onclick="if(event.target===this)closeOv('ov-key')">
  <div class="pop">
    <h3>API Ключ</h3>
    <p>Groq ключ если дед замолчал.</p>
    <input type="text" id="inp-key" placeholder="gsk_...">
    <div class="pbts">
      <button class="bok" onclick="saveKey()">Сохранить</button>
      <button class="bno" onclick="closeOv('ov-key')">Отмена</button>
    </div>
  </div>
</div>

<div id="ov-edit" class="ov" onclick="if(event.target===this)closeOv('ov-edit')">
  <div class="pop">
    <h3>Изменить</h3>
    <textarea id="inp-edit" rows="3"></textarea>
    <div class="pbts">
      <button class="bok" onclick="submitEdit()">Отправить</button>
      <button class="bno" onclick="closeOv('ov-edit')">Отмена</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<!-- DRAWER -->
<div id="drawer-ov" onclick="closeDrawer()"></div>
<div id="drawer">
  <div id="drawer-title">Что сделать?</div>
  <div class="drow" id="opt-normal" onclick="setMode('normal');closeDrawer()">
    <span class="drow-icon">👴</span>
    <span class="drow-label">Обычный дед</span>
    <span class="drow-sub">грубо но по-человечески</span>
  </div>
  <div class="drow danger" id="opt-yarost" onclick="setMode('yarost');closeDrawer()">
    <span class="drow-icon">💀</span>
    <span class="drow-label">Дед унижает</span>
    <span class="drow-sub">без помощи, только топчет</span>
  </div>
  <div class="drow" onclick="askSovet();closeDrawer()">
    <span class="drow-icon">💬</span>
    <span class="drow-label">Попросить совет</span>
  </div>
  <div class="drow" onclick="askPredskazanie();closeDrawer()">
    <span class="drow-icon">🔮</span>
    <span class="drow-label">Предсказание на сегодня</span>
  </div>
  <div class="drow" onclick="askPervyi();closeDrawer()">
    <span class="drow-icon">🗣</span>
    <span class="drow-label">Дед говорит первым</span>
  </div>
  <div class="drow" onclick="doSummary();closeDrawer()">
    <span class="drow-icon">📜</span>
    <span class="drow-label">Итог разговора</span>
  </div>
  <div id="drawer-cancel" onclick="closeDrawer()">Закрыть</div>
</div>

<script>
const DED_IMG = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/4gHYSUNDX1BST0ZJTEUAAQEAAAHIAAAAAAQwAABtbnRyUkdCIFhZWiAH4AABAAEAAAAAAABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAAAADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlkZXNjAAAA8AAAACRyWFlaAAABFAAAABRnWFlaAAABKAAAABRiWFlaAAABPAAAABR3dHB0AAABUAAAABRyVFJDAAABZAAAAChnVFJDAAABZAAAAChiVFJDAAABZAAAAChjcHJ0AAABjAAAADxtbHVjAAAAAAAAAAEAAAAMZW5VUwAAAAgAAAAcAHMAUgBHAEJYWVogAAAAAAAAb6IAADj1AAADkFhZWiAAAAAAAABimQAAt4UAABjaWFlaIAAAAAAAACSgAAAPhAAAts9YWVogAAAAAAAA9tYAAQAAAADTLXBhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADb/2wBDAAICAgICAQICAgIDAgIDAwYEAwMDAwcFBQQGCAcJCAgHCAgJCg0LCQoMCggICw8LDA0ODg8OCQsQERAOEQ0ODg7/2wBDAQIDAwMDAwcEBAcOCQgJDg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg7/wAARCAKAAoADASIAAhEBAxEB/8QAHQAAAQUBAQEBAAAAAAAAAAAABgACBAUHAwgBCf/EAEUQAAEEAQMCBQEFBwEGBQQCAwIAAwQSBRMiMgZCARQjUmIHERUkM3IWITFBQ4KikiU0UVNhsggXJsHCY3Fzg0TwoaPS/8QAHAEAAwEBAQEBAQAAAAAAAAAAAAMEAgUBBgcI/8QAKREBAQEBAAMAAQMEAgIDAAAAAAISAwQiMhMFM0IBERRSI2IxQxVBcv/aAAwDAQACEQMRAD8A/Mptq7YbF2bYupjbSmC1XYqH8011VTjVexEOLaADAyD00m4uzcCsmWgBuiMub376jKM4cP8AaChgLgX7ERfs/BGMcuUYtsk3YAQ21BeHO+EncYCaucr4ZDK+LbLWzZWgLn0TVRuJiw63noGO6kMIrImHEFqMHIOSoQHSjZAgXA9CmxlfCRMDU3+xbCEaHBx9j8BbAATOU4cP9X7+FuJ5e9h4YjTj9qC54F/JQMkDbGOeOggXsTMl1NEheB6W80BTMjMy7bxhYwFPqvdjw/G79um79IVHi0EzqBsHT2EfBWOSah/c5xmDEDBDEwzYkAdxAw7FGeaA4xnIeJt4wuHzRrb9J4TmIlMxpMtZUI1BMzNM6uwxlkGTihqbOxWvRMVl3I+LxhqSQc5n2LRZWBjSnDPzO8w3gBrC2axbHMH00z5g5MwxoG6imSspJfzAQGg04wbQ2I2wuEkwurHgf9eNQ6XVb1fMjYvHgzCjAZ95gHBPmvRXyq79qRm+lY3UGPPyYaklrYZh70Q4n6avYeYD2QMqFuoCy7pnM9Txc2YYjVpIOx0BepemZ+blOQwyxlcN1DDmq+U7XVOxJ0n0DDGQGSaZPf2H2LQm3ZnnzhgAgyHCgLtHzIA4EYWdNE8Mgdcu6Arv+NOPtPU/xhVQcWDrYH3q+cig03d3gCshAGmwAa81W5qUDUcyve67kk5BOcyQC4YCexB7YGbhgZ3Awsu0qUbsg7hcLqHfSjmdzAzBbo6eCtkO+VmAZGbYKHljDJYsDOrhgGw1DlStWRR0BcUZvIsg5o0ok1Tu+NOAxKim1IC502KqJ0HXNnp0RbOIHW3jMLhTYs9kGbUw9lAvsoubVPo+U7X0d/06Ae8Fai6814Bf1PehhsgYoZnp3Vq3Iu3cTLepZpVMr4gjSo/DTP3qqewhnQwPUXFm4tmYHqBfgr6LIA4dz2AkVRkyoRxsw3LtGLdD7FZDrC2YX1DXaQBi5rRTJsA5gCrZxveT8ywZXDmCRRiYLD2ncwuBKHKimLgSQ3gC7YXJG7HO4aZhzurVwQfbOnP2JbzLjj6G3R3gaZlIoRaPBwNMEwBsA4GG1XblJWPADC+xFDNhgQAPWDYCZQ5VzI9gKyjwjFswMNQLri21V8wHYBpZ+Cei+mDwepRRvNRordDC5q7bCscAP00PTI4feBmIahpOxhVPa0rwM2g1DDf/AGKkcnnpnQNMA2InigYZEwdMm9ijZDGsljjBoN90bbwBideJy59/BcfxmmbwGLdPerKQ0bTdD5goYtG+4e+iRVe5kz6LKHnjGOAGAvmp4yjFwD9/5gIejsHHkH3ndXzbRynN+wKLe3mUxs4ZyKXEDMPekWNjHIOgamzsQ3KEIsg7+mHYaUXNnFbMBeWXvuUiGbTh7CBTMXlJ8LIUK2jfvVrFzMaZHAJgah+8F2cxLMpvzMKSJgHYp6lufQf4s4GUjgbR7+9U+cwwC4fkj3h2IPZlScXkANo9D/mB70bRcuE1sz/rU5gp87MZXMfeiyN9gO+9XEHIvaoHfUDT4K+ymLZm49552tw/+msxo9AyBgJlv4AsTODJHkh1mfHo7VY/1V05Rwza4GjBuaZ+Jh3ga4zJQSNjof3rYyxNzDaUczfqHwWb5CgTDPsvsW8ZzAyX8eZxT2ew1g+SAxyEmMeyh70Fq2QAOw7iG9VvF3dvVkJ0b56gKB/VTJoGDTUTw/klXuXS37qD/BUF0+CIalDXchAfGnBcBuLa7DQ20xikMh9RM71Jc/8AZcF5Umf3N/qbk9v/AHjaly5+KQ7HFhsiuLiVv/smufm+KYgO32jT+C52/wCib9v2pLyqBJJJLAJOH+CanD/Ba/oDUkkloPdjA28aKyGL3+KUWOrUmg0wQ/k3r1zaGIALfzXO/qfxXRwgC4XVU5MZBznc0wRyux7iXY8iLJB0N9Nl1cwPCLEeu74j9o9yziPkjjgZt81WTMhNmnpA8Tfge01FdQirwenkXjWIbDJ6oxvi7QDC/wAFW5YpMrH3A9Nk/YayzwxXjHdAzI3nj9hrQXDyWOwYGcYjAQ2XbWNPP/jOHj3Fcr2G/uSTK8Q0gI99TM0VFiwgYvyzQCB096zqV1fmGJBg0Gwj7AQxM6tzZZcJJmYVPgsV9vsfG8PvcCeR0pkpnUAbKMmfNFUjpzAhmI2NlTxce2UC+9Bg9a5Wfjz8qGmAczoq3AtSZnXEaS6ZXuvHYnhcR7tI6ohB0504AYgBOSf5hhzWaQ3c2xnGZLpunc94GtpykV52MFQ/EgGwPeuOJwb2SmB5oKb/AGJs7E7XGLA5jbIUoZrs50rgQyh/eUYn5J7zA+CuNX7t6ojY2BDF946DrexaFkorMjHsnko13g9gb1dy5XbpTyiAfj8XhIUe8PGjemwwBXeFwMx2R5x9kmP+XdWsE40BsKwzMD4AjCG+cqOYNATZ04Gu5y4LXbEwmTjn5oAN4O+iJI8Azc/5YAarcfCNq5yD3n2InE9CGC7czgi0Bw/9oH7KbEMZp0Dx53r7lJmSjPIADR/rQ31FKBrFmB7z96r1hiZ2DJBAEynYe81SZKeYO0AxoYb1WvZExzB3PZ2Ieyk/VjGAnS4IqvR2eHJDnTwPMUI+HeCgSMl/tED4H2KhcB52QFf7zXGcZi2Zga51U7c8PQeR5oT4dLjeih+QA3DB0NM+xA0GRJamAYWcDvWix5QT2LjUDp3qSqdKeVwGJTRhM0SMaBvup8H8wAd9O/BXHlw1KSAFwDPvUPINGEgAjhpglKpnfoUhgGmzMHtML9i7Q6OuAAHqB7DXGO6YueWkeoHzXGZFNpw5IWoHsWbMmdi2O0yDlDPTP/BJzGg04ZjvvzBUmPyQH47t6JGXTLefqAselwxU4D0iH5ds5LWw+8FMZMDpT0z71dkGq2ZuhqAAbFTk0cWQDwhdk+YUUlHTJSgDUptXaG08Pjs9QEmaOyDB0NnzTNUIUgwukaGFq2AbDL0zVU4ABkDuo3nzdcuCmCQP8+a8MztGlGYOXLgobwaUi5endMkOgLhg76gLs2QOx9p3AEnYmcIcgTFszpqGAbFDjygdjgBBpvH71akYG4G9VU5o2sgBgGz3o22gTMcD8d4yDTMOfzQ3HaZixzNqxn2XRyy6DrpgICYGG9UOUhBFcuHprJitZoLZm7Vsz3b1WyMyYOGDFKB3qny0qe64AMemHehWQ6Y3ZvpmaYJkSSpBzY1zevRQIpRibuX+tUkUJIbNxgnuAYuXACbBKsZFscgFyjR3BT4cw4swKGQAB3+CDIso2pgVe2exEjJhK3ie8FjRdNC8xDzLYAdQP3p8eLJxsy5HqAfsQTHIx2GGn+hG2Fy1JkaM7RwD5pdSJWrjoSo5g0fDeYIJzUAJres1skgddi0XIYYAkechcDDeALOpxG1Ik2s2d9gKepUaAZOvNZU2XbA8B+zmpjgg62Bhzur6VF842BmAtmHeqF50IWUADAmwvvNAoQx4+rHADDnzBYn1p0G8WUkz4Qal9xgC2xt0zcA2j9Ew2KBKocw6nv8AZ70vRbxzKhnFkUdAmz9hqtc2OB8luXWGDjOtnJppn37FjOQhHHcvzD3r2Qri3Nrs2Qj4V+zcuAlQPmneFdMfsVcsUlCQFsJIhrxTGw9/BdnCq2nwXlDK5uJhfxSt4r4vW33+Pil4eP2F9q+JLww8/GzvimJL7/DxR/YGV/6pF/JIv5JcvFYBqSdXwSr4LzINXRc0l6CTq/8AVIf5pW/6ID9FILQadytsSmTWWrhtUYpXl3DC/ND0gzdcPel6w/kmeG71atyGRM712KnZdM5Fz5qS9H9Q1Gbaq4l6u7fVRPOIxItx5RnXKPnpgQc/Yu/kDOYYNBqB7w9ipseYBJDV3grgsycVwwY9O63Uw5VTe/QYYkMPhvEJORMnz9nOiM4PUOKzbcllqMQAHvWNY6HMzuToPgX2mtixeDh4nF9pnTea9yi6/ji819g/OYE36fdtWD5HcFlecxJsNmcp4XKdgGtyyGWhjHOMZi2ZhQKLPS6Fn5GOZgZv3OwXR+K3036f5Pp7gDA5mBFB7GunTV4HTvRJ0u6DH1AjG7XywHvRng/oi9lJgG76Bga0iL9GI0PIXkTNSnYC3PC7fRa4W7PNBKvJi+uyAbKdimYP0nLk8NO8D2IwwfT4YtqkX1AP3q4cwPmrmUYgp30ouzy8PHu9mYhSDjo33yGVgAJnfeCJxmmd9WMLh+81WxQCLkQjRQuYbUWx4t3AB+oGfYurPKINU4kAOAbrOpc+AAjmG1GGGFGdM1Mx+NZBu7oC4HYZqS40Abw9/Yrpl7Z7LQG2BnVVuQlM+XMB7F2lT4zUcAM9OnNAGWygH5kGjvssmmT8IzJm7mHjM+HZdCXVzpnHMLkHvV9hZTMqQ887wAFnXWmUA8xQfUPsomK5lm+ayRnkwBo6AHNQPMGbZ39RRpkIAyBvPnqGZ3ChrsMOzgb9imt2+EmC7ZwwENMzU8cWciOB0v8ABJvHATYUve/NFWNB5qNQw4Lm1N7fQcp9A23jaOXMNP4KyiwjYkG8Aad0TiwyblyDeu3jCu5cP9CXnC7+CM20Bxw1WdnvuuLkUGnDN0AcDsV95X8GAEfNdmYoNR/fv714JkHyodHDeACcOnCmxQGykhDA3QGhnwWkOY7zUc67A5XVPIwzzrZ6TPBTVTeQM9C0nLx/TM+wFPxsp5r81s3L+9XYw67HQ0/7FGkQ73pwDgkVVjO1qLpu7A2BzUMna3O+nv4GlHE2GwMuALs4PmG7gG8OCXrb2ZwrXDeFszAxcM094Am4MJQ+oYBQ0nDs3Qgofeu0c2YrZw6ajLu9J/8A2f8AisPMiAXBrvT48o2shQw1Lq4ci+VkGdLgf+CY2ASJmtQaACNtzKqeihImUPYB70wTCLHMADZ71caRuyNlmwXFxqlwps70u2KlDcEDbB6+9Iryo4AYJ7kUyco0emFFJZaMI4W5rSfIeZE4Ew7epdPmCEqHs3gCsnIoSHOGma4+XNpyh8FnAAbkMHXDD8s/mCG3unLPmYmLnvWkZKK8Dus0YUQq8ZjcDDUM/YjB8/AJJrSuAmTdFx/EyscYA9qGH9iJ3DAXAA6th33BME8abZgYEB+8AWnoDKA8NzdPepOLEGJG6SVDPgidzHQ3d4GTZn71TuQpLEig1cAFNUhfNu3kXEyp81MjyDayIXAm7nsO6oY7rwOXdDTD9CuJQG7jwktAR+xFegavicycUAM5IuAAd6jdRBAymP1mqsSQ9iAILpym6GeofwU8XzCQEYz0z+aQWTkc2owA7wPvQ3noRuuXGrgAtgitMyMeEabW5hsNB+Wxfkn3mSsbJ96P4GSzqDNeiyAjHvA+F+xXDm/KXANOm5UOQjnHygGPDsVrj3dVswLmaWFD1FA81h5Ol6hgFzXnvIXC7NBoHYa9LSjAZBgWwFhvWGO0sqcloPRNAZcVD4hprpp/L/8AwvkprSkUFIQPTuqJIo8ho4AJOb+/ikX5d+9cbp8vHNJOEfEv4JEPiP8AFeghHxL+CVd/2Jw7Uwv4oBeP2fbtSt4r6PPiniI6n8V49c+TH/VclII7N7Vxr/1WGzUk6v8A1SEbeKAcuad/USHmgH8fFck8/wCKVdn2ryg9/wCRaPV8bAqzSPsDUNEk/c2B/NQSGo+Bon3fydy65iQ28wf2eJ0VeTSKzZsBmKpng9TctzLo8uukdj+H2D/BEOMwD2WkBT3qkbAQ8B8RR90jP8vmAAzEAPa5dVzy2R5nXpEVfJouLxcbB4cDoN+JmgzqDNzDcONFDnzMEVdQZQIWL2mLhnwVJ0TjZ+e6oMyDUZA7uHTmujy8O7vGHzHh1eL8rq79K9DSck6EmYBG8R2ADWmuRYfT0gHnXhfp/RANgJnU2cDBtBjYB6cmnrmCHsbi83lI5zyB1yNfma6X+DHL6fY+HO42LYvUGYyWQBnFwBigG+4BS62DD9LvHH8zknt581m/S8WTjcgD0rxIwA6UAFs13ncWBxbXNPnhDuTNx8uLwYfF6IUFw/fp3uqHLOyclICNAZ02T5mGxEMPDA7laO75J8L9iJ3sCELHm8POif8AihbNX/JnuPw0bGt6xBeSfMzUluGcjMeqHohuulIjvO5A622GichOFgwMw1HjCix8L590OQ6BUZj7AANiG8tlo2Djmcp71jDYCjZ7qOHg4e0xOYfD4LHJ0iT1N1AB3Jw7re1X4rsSDlHszlDMAJtkD3hdVuWMIrZ79PZwROzADFwwZIB3/mUWb9STWQyZm6dKcAWlcytcCZhi5IFsA96zfqYwLOGDXO+w0Qt5eSeKu0GynYhiLjXpsx6YXD5pufQ6Z9wTkoZuzIwEZUpvoriDF0o4BdWUgQ85tq4AKY20BuAB8EipfQcPSHaO0yDfDUNWQmZUAvTNcY7RhcA/1qyEQ7+aTl2ORCAA5cTK6nxz4HuM0zS/TRdtIxpTZdSVK6U9uODrm46UXYY/76U1AUBsHh3mrhh0xh0ML/BSYVzy2hvFRsAaPeHYuzMow2EBU/QpLYAfjvAbrtpB7Fi1cyjORWZVDCrZ96rZGLDUMAs4Zq4JowcCgUUwaf1QK6kpueQJKFpeBgfD5pml6FA53Rm5DZdO64lAjeX3hQ0ivQTyBjkUCvcN6gSGgCPw39iLXooA2dFWvRbthvFIqjPwbQ2WrY8APmYKMLBtSDBoFPJqjoBuUkgM2/SWXlcIhWiBnHOwEx81GeGnhQAJy/erUheOgEuJX1KBVw0MfiU+kZuAYBzUkWqyLkpN7OGA812EA0w2LUEdZVr0Iz3tdi4+Xte/NXDhmDdAA1xKOZNXNOYqYwp3scGnQuBqhcxoNeBmLOof6EYE0Bt0MyUYoQA2dTJMIAz0WMUg9WNqbEMZTHMk5+FMoprS3IobzP1EK5AWfMbWTcPsWKkAlzHGEcDde1KdirRjyXZmwCbAEbOQDILmen8FWyAOBQBC5n+YpgoXGDCQBkeoHfRTG7nsHh2AuzxslIv+WZ9nsT4Ym7MDfSnBATGYoRZgGAaYH+Yl1JjgHHhJinvV3Kih5MHjs5Tmo0poJnSZ1PeAUolVIdum5r0/B+WdMTeAK371PGYBtnGyXqdgGs96ddkxcwYEemi2d+KjADvpnfZRIn9sAzqSL5XMXaDUZ5qtZlMhI37LgjBw2XWzjTa8NhoDyUU4WUOvqMmfNLoJOQC7gGAXu3vQxlIrMrFmy6F7/wCCKo5+dxZgfMOCGJEcwyhgZlRAY5lIUOFIMCDUQrIfjDEpHCm9aF1RjTJt572c1lBfmEiRREVvFPtZcklRJbsJeI/wXZsQ07Ef9iYImfHtTiIPsoKewQj6h1TKnfgm7h8Url7vFMeHH/NIafavpGBePBOEQosAxc10IP37Uq+ogGDTUS8Sr47U8RSp7Ut7pHSXWvprkhs4f5pqSSWH6RyYxh40INgKscaDTR71RjXsdJAKFSnNBDlC2Eury4e7+OOVKeRt4mqOR/FErwB9poekCGptXYnxnc4I/h438RqiDFx3jmB+vmqRugOAatmp5g4ACdKKrlwg/vvGZaFIjs5VxpkCJx4Nq2Xo/FxunOjzMzEHnuHvQh0lhocfpTxy8095eNgViWUezOUOMxZsB9nYC+n4cI5Ru3571q+vf/Hj4SXuknuo85cPTDUsZma3iLKwPT3SUaHKksbAqbId688TOo8rCbCNFAtEDrenNScW09KcDK5d4nAAzoBmudVRdv0jw+F4iHoqDlsVPcuDItxu8zAKKZks4ECPGCAAPhTnRYzBkZLKZQI2NsxANapBxFI7IOgTlG/UM0j0fT8uS+6dIymBPlHpmfYr6Zlzf8dEQ1A96EnpoB4Ay16dA59iUXJXkADR6hhzPsWl0zgVY9qNHcOZIAGwDndZR1t1+HmDjY57efeAcF26w6mkyG/urGnRkPzz71lbeGkzcgBkFGb8/eprXTPurXIuS6gzARrme+5mYLUYOEgYHH6xnqSTDefepMGHDxcMDH86igZJ3/Z5yXToAe80TP8ANdr3wGM5mTFwzI6BRYbOmvZvqx4xPTZD/NWXXHUdmzjRe/vBB+DlaDZ/0zPhdE0qmRa9KBpsIzR6Yd6tSfNrBnUyD01QxwN2Rd2p371ZSjN1vRE9iu16HzKnHY5Sg0PvV9DYPmXqUVbHhG143P1N6vo5mbe8P0JGHZ5S7CP7uGmuwh6mwBumCF3A5tqeyAeY39iy6szh2ZAz2GA0BPIzBvZVxdm2vw51PenjFNreXBTVKqcW7QxA3AuGh3qe4AB4Xpw4UUNkT4D6ikiBm3vPU3qXrMOtMnjcqKSIGPjsDUSqBOB/TXagBwPepLWzg9szOQAGCshaA3AooAnddmyMHKAGxS1KiZ24yDAHDClFxvdwKBqK1Kmnd0Fx8qBt3DZ81JR8yqnGq7DBVsxoAY2AirQPT4E581AlRT1AMA4KZueUWEhAB3mCYIeofJu6u3IoFIufp+9cXGAFZmcCuShITDw7j3phCG8wDUP3q1GPXYXDkoZUBzbwXtpM+6qcaA9ggS4kJg4AAeoCuCBns9M0wQA6H/msae/ii1PqvB47lJbI3W96mOQAd2AaY21peNDNbgiuCtIwC++n9i4k7pNnqvXBWT0cC2Ga4i1GFyjoaifNEV4wbJ2MfhQIxOGfeoD1zcMxDTAPgjkmmQb9IKXVPIIBcMKaiNlzyBj0XV8L3JU8rGg7xeJs/ejmZHs2ZgHNDbzVNhcz7EkZDYwgiyKOgL90igAxIAwMgDkpjmyRu5q1Fg3cWBgGogipKHIZkRzZd7FDIwiyDAQFwHeYJjYeX5BqGa4zmjjnrEeoB9iEoJnG9A6gAwAnAM7bETvOg7DZkgZAHeCGMwTzUkJLQXZVlicozNwxxg/ODsNT5McZ1HWzO5XVO46brZs03h71ZSHdJyhBpn7EHzpRjlAeaOhhzBLqS0zHyjamGF6H7FJkUfkge25oecIHcgDwcz5q4Fo/L3vv7EsBvqyABw3gINhhzBefJsPybgEB3AuC9NzhOVizB0NQzBYzl8Ib+LNxqoG0dqJgZ0RW8U5TSig02ZunvHsUO1nATJLP1KN7O5ciLf8AapwiydL80iigTuw6JgQkl1JgxeoO9MrU/sJalghHxL+CdWqb+/iuhfwWnj7ai7CQaajH/NMr4oDsR+omJtd/2JyARbW0wdvik5/7pV/+yWYYX8E1PL/3TF5QfrJ1lP1ZBh2diyWQ6BmfuRt1FI1bmIF+tZjIdPzBr7z8ERb+PPD5bSSd9NU7h+opJEHi2djUBwvU2GqsxEO/zhxI7uUSbdMZIfrUYvzLpmoIuJE4h0ctvw8+XIx7MATKh+zsWkYuFGwjkmS+8O8Kmsc6Byj3mJLIAL7xhsutFg9QwHcgEbMxiOTqbwD2LpV3u4cPl+nxPe13OygTWwZhRtMOfBXGJY1f96u4FOAb1MLHQ5XljhGLDJhvAwoaJMT5DExrumLgBzuuVVe77vxvGiIha4k5LTgaUMmGQDnRFrcqS7cCuAd91SOdSwzj/h/ToHM0K5DMz5Thw4YEd+9E07k8owLchlGRb0YoXP3h2LtDinDhvSXzJyS7/gmYvF6Edk5RjcAud+81a5bJQIsehGJmYcABNGQ25FPJNmAAND5mlj4rMdwAD1ABMgypMqP5ZoCYAz7AVrOJnFxwAPUM+Z3SrUTKhyU09Q6cAWP9XdUGcc4YHs76GrjqjPG1Hk6RjffsuvOuemPTWzC+8z3mCRXV1OXDfsk5CUyewDFwwXGG6eqAc7qhgxQabPSu+fzRniY56garJNomnV/FAwx7QBHA7rsVNTanxw/Dhvp8EtLv/ndXT7wJl2ZYM2zMDufsV3DYMo93Q3qHj2jN3hpgr6O1dwDvprcr5lGca7wP9CYTRhSh6l+auBaDfvC67DFAIx1qCM26kz6OMVoAbC5q4EQNv4GoceFahiatSapH22olKJn3VrcX8TsNWXl6uAH+tMbDSc+CsmzA29qm6ythAKKZObfUT3mjapsUkWjNznRSdK/hz3qGsL5n0VQxz500wVq2B6gU3gpOlVvfsD9CTYeptCils+awjOABuUXEmjBy99itRas5c9gJ5RQNs99EipUoYunp9qTZmTm9ImnhcoBimUMN593sUlSbM+7jIaDfQNQ1VFF/fvBX1DNvhT9aQtX2HsSLVVOw25FPTMA/1qhcYrHMCDUM0bONANwM7qqlQKx9YDuaRVJM4CVQa5rtdnvCiUgK7zMW/gah3Mqe9J/LBmUkR1W7jsUYmruU3NrsJnqGuwl6apn4Lyhk0Yc1AJoNQ991fE0Du+9PgoBRYwyLnYz+C92xX/ZWuBT9HYqqQLwXP8w0QuNVb4aiqpToBIoYL1jCAW5sNVU8pqrhmFTDsV3cC5go0qL3ieoBpeklUFZkUHW7gG/3pkEzi7BPnzU+QZg4YH6YIPnSnoWQvfUAz4Le0PWbsTyNE5Hpcw5qA86yTdHToobc3zjfpbHqKG8Ruub6gYL1DU4CvUDT0VzzInqAZ7ABDEHIgOQAC9C580cymgmQzZdMmzvYFm+QhG1IMHdhhwMEqp92Pux5lKPx2TaPfTeYIGnAbrhmHNT8HKP7ThygLeGw1AnAcfIGBcL80upiwpNcw2HseBEmLleacBmnMOaoZ0fVcA/Z3guMGU9AygGfqMkkZwB420emYOgs06sxpwI8mSweww4I8jzTlSAATG5uKNmI4SsW9DdDTQHl2Q7qyDMthrkW1tEmYwhxZB6AXC+9UIw5J+O1kv7lRJbiI2PnvTu+n+akuRdJ2hODfvoa4kFb22JjDkJmBlQl1EgJzcC4jz8F2I/UWvh4fYD7EiGjf6kzxH2/vT2xt3p+dluIif2pviR/aSsRAA70haDwvc0ipe6Vw+FjXUfyvBPFoN6Y9TYILRn05GX718tZfFzStNnF/JNSSWA/SvLOmUMwPgCzeUX4i/YjaU7ZswL2IJl/mGv0zr6P5N8GcI3i7fxNQHC9QCUkP5Jjn/uoqrbvz6WjOGYtqtIz1FauFdVxNWc2+H7lhfFDXonMs43rCNq8D2mt+baw5TDmEA6wBzNedunMOcrKMvOloADi1wpsbHTDN97XjU968qsOj43jfl6fAz+8npTgBFeLYfMFcC6EVuk+ZrmZ2pdZWXVYBM8tAZG596mY8JM3IAch4gMz4HwSNbfaT40RDYILR5RwAEy0Q9iPyajYvFAdBcePh8Fm8PKRsbHCNFP8SfM1cDKedjh5gycM+Zp87IqcCT75M45vOvaYBsAD71AxcCTlMj5k7UM+9ScfgXp8gAppxj9605uEzjenwBoKHTsBXSlr/qqhajYjHmdN/vWV9SZn1DMD1P0In6iygNY87PBs571546gz2rkDBgCP9Cl71Eei7hN2rc5NOVIeBoKB3mazGYfmJHlop6h96Kno8yY4ZyD0GfgfNMixY0Jw9IBMz/1rkz7u/M4PxuG0oYG7zRI3otRwMeCqrGUcKmTZqyjtGFAOpgr5k/K1i0dof5atW2DLeSYyAC2Gzf7FZNtGLYGez4K2D5lMitALYAXpmrUWjJy4mNAUCLd1ygmiRtoAb3hvT5bmfdxbaZ1Nwb/0KY40AthQNQzXaO1q7yDgk87pObQv8ExdLs21doAENP5qYLBg2AX2J8Whw7mGmplQBvdY/mp1fKY2qnIoamzmnsgDTtDPepjlAbXFkGTcA+9TVLpTKS20ZObQT24Rm5c1JHZw5rs2QcB5qSpiFU+6M5tcCx71xrdz9akvABSAuni16e2pqSz8OJFVugJ7YGXAFJ0gJvdQDUlsTHgpqPlAcaAOfhRQyA/tAA7FayGjNu5h/oVbQwc4Eo8q5nB4nw2ahrsJgfIE+4aYbE8Wu/8ALSapQhvRQd2fl/NVsiGYNmBeoAcDROyIG5vBPejg/sANNLqdl0yiZjTdbO4bFTuRfL0D2LUZUUAbMC9RBmSis6lwP+xc3rOLAbb3yDAw01MFijexdmWgG+rzPvSITDYHBMnYQ3APUoIKGzdp3/mXVw20e8zPYoekHmNgEqC6n0diofZzVPkIYeYu1vBWRAYOXKziY4IFHuB6ZoT5DDkUD4bDVa8Bg5QPUDvRUTtHNwC4qeVQpG0NO/sTGKkKyDs5RUkyEEqPQq3BGcpoBcoIb1TvMfvPYN0ukVAlyKbG8PTP4KG4YG4dth/rRJKCjZmXpmhiUNHL300xzesoDkA3eR/5qhcgTzbMDZ16cKK+eKSDZmZ7A7AUCkl1zWivFQOYLy0lTgJFCnsOG86BN0T3HfOQztzBEjkqS63zpTsMFAeaZOOYf1j9iXnDAYed0m6Ohph70xuKEiPt59iuChargA6A/wB67OQACQAAegYcFip2FO209FkAYASuCdN2ODxgXNT5BvRceAEAuH71TuSngx+iR6m/Yp8imRdTOyYvUDxugTbPNtA8mZIJ0qnsPx2UW0dSQzymLuYABgsUlxwYdJsD+0x52TPgtCEg+z7S5LtcD5rgulw9ifNFugtfusJp2kZ/BJvfs4J5FTZdNDjU9RJwKurt81xcIDcTvhgid/euJFbxXxJT1Rky6CRgmEVuK+L7xbWQZy8Uq/8AVfW/zfBOr6hobckl1IF98C+wPsXmQ/RaVFpf2UQbLZq4a0SZTT3dgbEDZLxBpwzM9MPYv0nvL+SvBq7+VILSYQ+nwUORlGWnDpXgqGV1MBuGAKLNvtPG8Hv1tbPPADdyPTVf58NTnvQfMyRv96htyHipU959i9fVeN+lRN+7UYfUZtN07/gp7mUn5FvRvzQTi44OxwP8sw5onhz2YrYA1vM/zDUdPquHjRyj4GGLpC/3refYieLkTlUOKZbDQZDgT8k4ZxQJwFp3T/TwRY4BKMQPU4JcnWM+n4r0qRGOUBHfh+tbZg+njdyASZVQAeyiG8GGNhRwMjFsADZdH8efJn3jYsNnvMF0ocfuJGyjNOel6Yd5qk6kzMkoYMwuB8zRPDxIBi7zK0AN5+81QlA81IMzDTjBwBPqsIZn3YP1MEl1uhnvM0AOY0BkXLYFN62nKQDkZh46agAdQQZmosZrwMB/O7wUNTu3c5YiGS5DWdcBloNiht442PC7p70bMwqOGezYmSIoC2ZmemAJGYh0ZCrdzkAAGiGKB7PeoDLVphmAbOxXbNwbCyYoXEFozc3bzVxvOZT8yirYdzoAIhZaBqlufeaqhVM+ifBaAnAAA01fNxdJwDd3gq2PRpsDPmrhsjdbuQbFdLeubszR1z0uCni0zsMwFw+81DZMAboAaant7mzAuCKPkhpp7A2KS2wAuXuowgY7GgUmx6dDq2aWvmXFxq7hhtontxQFvb3/AAUkQMG77aJhH6lDcSaw6MkLR8APYkJg03Q+a7CHp7PTUkYoFcz/ALFLSuZQHN/ZqJCNN4ArIooC7s9RdvL3bp3qCjVO2BnI7gBTxCnJPFo2vE+81JFq9LgparaiUYg9P9agOAZucOCIRaAG/wBShuRat7TusUomlC4Hp7TUyK6YR6AGoCRMGcjcrJuOAuAF9P8AQoKnZmiZK7ZgYf6FM0gBu9FxFowc2HQEnHdLv1DWKnAU84AJvcFEHyooG/vRy8Bu3PndD0iEZOfBLzFmAmdHNp8KBs+CmMgDre4FauNVcMNyY3FA+JrJdIHkg09tmzTBhH2grVxgwpQyTxAw33uFOC8ssPORTMKKA5FBpswMxRU4QcPy7qkmAHl7mFwWBkJSgpvM7goBFGIzrsROJAbZhQWwQ9KgMnMMx9Q79nYvK9E9Kec0Gne+9DxHZwzuid6PfY6ZXD3oYkNUmHb00T7pcKfIGYx/+KGJDoG5R31EQ5AuYFZsEJSN7i9S1KBKfPTMwDYlHPVbAItfMnzXGU0YR6AZbz2Jkdo4+QZeD0zA7mC1r0Q9TJzElpswGvmQC5qhbPVdAP8A+SHOji1SdAh5TB/eTQE3JpzBYDIkSYHUDxnYDA1mkNNIEY0+HokdJIcDQ3kIs9qbR8CMOw1ZY3JQ8k0B3EJI/mK1cdB9s2XTJsw4H70ssDOZE49GXbOH80vOsu3tVswBTMkDJ3Ag1Kd6G3ovY0tzIqlq4bL+PoG9Zv1F01eQcmOi2K+YSKSAJgw7PerLY7HMHe9YqSNPPzjBg4dg4JCAfZTvRz1NgThR/MtARgaAxAwc3Bpon0bP4JOAIt3LmaVAL+zmn0s5s4Lc/YcSK2xIhM/Halt8PD5Cnl/JVWHGleSeJpVs58EwhqfxSg6WBc/CpObk9wdn2rj/AA8UPZP8fER4+P2pXTBpqJW7EsZIv4plv+i6f01zL+SG3tvMdeMvSXjjHQP6azqd1HJlSDO5b0JFKvIPekJXuv1Sn5z436L4XiRGYdpWSeKQYEZfrVVqvXVlpATfqqS21Aapc9T9akqXVzEKdkJLrncaIcbg58+YBtAVAVxBlQGpNzMWw+AIzj5nCNR/SeIDPvUNqp9FC3DkhkAgB6ZhzRtjelw1AedkifvAFDjz4ErIXakk+Z9iIW5QHHPSDT+Ch+2xPByTMWMcaEzQA2XNtHmFi0hhJlHqST4AsrxYG65d0N4HsBbZ0fg8llHLuhpncAAPgtzLFfA86Z6cn9R5RmM1YA7z7ABeh4ODjYZsIDAXMOZpmBxsbpfpuNGuPmSDs53RIWjFh6xnvPcd12ZmMe7gda3anzhm1iwZaq3fmgydNCHhwAD1DNPzmZORkKRd5/8AYgbNSjOQYX30rQFJVQfy5KqVNMpBg0HP/BZ7lpTP3oEZo9SSfM0VZCeEDH6O45hghXF4YwcOZKMvMunwSNbdGZw7NxQaxx6obz71Q5SL6ewN/sR55cGm7uhsAOCEs5lI0VzaA71hXyoKi0YN3IKfBSWaE5vXEpXmN9KKZFMNT2IXT7riC6AOfBFUUwd3lvBDEdoCkU/MBEMUNKOFfTAFVPwrmfRa0A3AATRCyQC2ABZDEdp7miGPQ2796un9t5hZUA3N+wF2uAUAQ4KGJvG4AXUwQM2wDvWKlfyk9u4uXpsT3A1ezmpLYADffdSRANMAFKXTKHQwboJ3+CQjfeXpmrsYrPl7mG9MKKybVzOgXSbVTKG2dG6U2KYLoAAAP+hdhi+odOFPYuItA1vpe3wUtOlh2bAzuZ+mpjbQF3qNUPtoAEuwiYXPsUlFzNnkANSAqGoa4kX4jeFF2Ej07gGoaeQUcuVbqXC6ZwZ8FxJozc2npgplQNvhRQxA9XcexIEmODRuneoZNGLlwPUVk4AE3c1AsYXojKjLs2Vmt6YTR6gbNQE/eTYcUxsDFvuS8t4SSaDy+0CVPKaDeHA1M8wY7DsoDwGT5n2GkVLCkmNU2CBOfoUMoulHuHNXxDRo7gX9iYIgVDuTf61iZbwqm/VbMHQ0zpsoq0mnmpFDMqIqJoPMAY+mdPYqSQ0YSAO+oF96XYqVU5HtI2eoocpow2GGmCvnBPTu0oDjoG3SQFPmssZDZRQORf8AL/QoDghvMT06K+eMBkHT1ApzVC4Ab9+815aOlDOoDhmB70H5ADNy4H3ownNUuB+mgmZ6TlwO6xpOocgdm9570KuGYyN4aiJMhR1szM9NCrhgDZ0S9JqlWvSgDIeqenQ+9WTYhIbCS169+dEK5b1Wwtw+CIek6FSMG8+G9bn3Q9ZE+LmMxbwH7N3D/QgPqrAsyMhdoNQD71oU7Fm1kAO96BvuqHICDt40jhTYfsT7c6mMtwpOL6gA/wCj71p0ekrHhJDeYIVnRXorZm6GoHvT8LlDxeQADDXjOn6l+xZLPzkUDkXa9M+8ENk0Z3AT3h+WjDMRzdcOTH3gfYgnJa0VsJLR/wBiVXoXR5Neaa0T/O96YTRtbCAmzDgZrtByITI92gHzIcwRCzoz4dD5gvZGQlkAOV0vJA95hvBYzKdPUptXoeRFDUMD4GCyLOdP6GQM2nhoZ8DRQkEkHpnTvSK7TlKKS80bThgX+tMcdM6AiQieDdgL7dh+H8l8Fo0iM+BbErAP8E76BUMP0JEQbEhM9I0wQs4iw7N0000RsZWXwb6nhsTx2ndYphxEaOJ5BdIt/gmFdYbMcAw8f3plf+q7fBIgAQv4H+9D3+7WiapvBJs6ObAT2wMnD37F2Fqjp2MV+p1T5uyIjKOoZAYNncyU+vNSY8CTKcAGmdS/vUPWhnaA3fS29imR45ynAAARPF6a/eAOnp3PsRzDawmDhgbuk3T381xuvfBkzakxOGmRY4G1GK595rQouDnu48DdrFANxmZ0Qfmvq7jYuLONiYwvvA3sP2LH5X1B6tyUgzlTCCMZ/kh7Fy68yIdHl413D0zHyMCBkKBJGWepsADXof6V5yfNmGboCxGjt7z968DdLzALqCNJlHsM/evYH09mHMzgQIFm4xnQzVXjeTu0vk8MQ9k9LyPvzKyZ8qzkZrgZrj1V1CA5AIzR/roa4yMjA6X6HZZExAwDeAGsHi5eZmfqIbzp0jGezeuzXf0cOfG3bRW5BsOSZJ23/loenSgCOcl0PWNPyE22QCGB7ORoSy003coAAdwDsXNqtujPLCyx8Vl2Qc+ee/TuCk4/18gckg2Aez4Kq1TkOaIHphQKUV23H8ljzAD1DMOa3LeTCpI1qmTlzuZ+xYz1RKAupPLBvpwWwaQQOmzudzO5msNnABZx6eR7Aumawr5SnttAEe5GpMV31DsCGGZpypFLlRE8Ig7g7EvSuZEkF0Nn9NFUczKgAGxCsVq9DFX0eUYN0DZ810prbesCRkzPYB0VxHMBbAO9DcN0zc3+oCKo7AG2BgCukTSZHEyc4KY3HMJHPYS4sj6e3YrJsLOc1itunJCNW+eoa7MtGO++9dhANOimNx70DaAe9Q6wtlxEDNuhLsIWb/QpgxT7KUXFwTByg+n/APNL1t0eU7giM9OgWp+hPEAdj0MNNMJ0AbAN11MENVsK+okVS+ZRm2jNygnsT6mF991MKL3ieoa4txTGQZlwSKqLPzDjqm02ZmHPgmX1XNynkF+AairXGjGSdNm/glNzKY20AcLGk4F278Eo4mFAupjgBphs/vU3wZMwrSECauJ8OxMEAJz9e7grIgAY/iFNh96TbQBI2HcEagWp5DVOPBPGgOABd6uHo4G2GlVcXIVmzMfUosV7j3tWyooFHMw9NVoxTJvcrIrjcLkZ+xMIgJzeG9Ly3MozkUPLhX/9iqnI4C5vDerstjexQHjvv71iphpDcA9PcYqqkNGTgUMbqY4RhsUBwAPYZk2kYamUBxqjZ6p7/gq2UJm3sVlqg05QvUD2KtkPgd6B/mp6m4ItWuDsPV9/BU85qm9oOCtZDtG96HshKMZAaRg5sWK2RUqeVvjnq80B5AjBygBsRm5eQ5c+9DGQj0vfmkJKkHzBA45mKGHDpIP+oiSUFHD9nehtwwJ86mNEuUtSrXAB1zcHA0T9K4sB6gB5rvNULYg7IAD4XR50zHBrMazRls7DVc/aDv8AFiHqCKekZjwCl6IMzGOB3FgA+mfvWnSDCU3JA6tme8EK5KjWL1nQ1A4mCfbjslnGA/g5QXuHNDZCDUgAPh2I86iinMjsyY4UoG9BhQvNN0IyAw4LJi7jumccAMNnYhvLQqSDAN9+yivorpwpDIPhqdi7dRNWbCS13pdBm4wAhZAJLQaYd4K1ju6WRAw9MD5qkkSjGYbJ87qS4TzTVB3gaJLr9wTthdwLH6J96yvrbGvBlLtHqM3sj/HyjFwL1pfYCgdTQjfx7xh6ZootiD0oPyTC+xQCpqc96UgHgyBt04GmOGAOXpvSweQXcTHAAW/mKROnzpRM1eafIcbF/wAV2Hb+8UiI9TgmJodhP1EiO64iVE+3qGlh8L+C+l+UKRHZMXlsf/Rg8/BPLckvpB6d7favW20N7+IUNTG4pk5QjoCeXlotzuNPmoEjqGNHbM7jsX2fXyY/3c6eWxJDhxhcAyAnPmanuZSBAaM3TEADfRZFkOtZJgYRNge9BMrIzJkm8h4nFw+/nXZ88IadmPqHJGSbOLDTAO9BMzM5LKNmcyYTh+y6HLfZ/FdRuXFcaut26XKIj5WsWebTdHQ2d5hzRDHjsyI4PNGTnwNUMGFMlSABoLma0iP0/GxrgedkiFwuYAaSoTOnSZlSAjGYNvAewF78+kODPDdJs5WVVi4XAD714YxMjp6L1RG8qYuHfeZmvRuQ+okYsXGgQp5Nm0AC3Q11fGrDmeTO2zdddWm654xgPeexDeHnnCxYGB6hh3rN5E96VDjHKPUM911MnZQ/u+NGi7AM966u3N5csN+wp+dx5ySPUM+ZmhvNOsxZjxhS5nzSxsw4XS0OMJ0MwshvPA87nAevsAN4JezMjzHmyOKAzPUM27LsUowjyXtzgAGxAePmyXcpotHspVEmWkBF6Wv3nzD2Jk0Xn3MlTXp/TdHT594LOs1DNrH04Aa0LHtAXT8bZzBAH1AynlcWDIVbuvLVzMBuO6DVwaDUP3oqx7tm6GazrEzdVszvvR5jRAN5+pdMmdn1OB5Fd9MKcFfMgDtDAN6FYroNf6FfQZoNU3rs8JS2KoogDlD5ozi/mAA1QGM1lpsHnagruDmYwt3MDcon1WG5obE0BcNimMtG14XP2Ibj5sH2wMAIFMmdTQBjhQxuHsNSV3h1ZpfCJnQBBWTImfMOCBsX1QDs+/5gXRnHnxjb1gPYaRXWLXStanqAALiQG7MvfguzMhl1y995h2KSLQaZmYEFEj7dLl8QrRa/EGbvD2K1jtXj7K81GGnmDAz5qYydW9ikqsOrJ+lTYHNMcCjlFMZMBbPYPzNSXAA4+4BufBTaMyqm2qN9q4uNe+t7qyGObTYHzBcXD/EXIBoGxGm87QxADcM+CZID0wCmoHwU9sANynvU8mgajnsup5eTNwHhaPTpfUBIo/qBQF21dLIGAHe/YphDRsA3N3QoqYMJowjhs2LjpVb3H/YiGKAOw6GobkUwcOn96YyGyEBb2BsVa4JhIMx4Inehfhzp6ZqnFozkGBI0bXwpLBwvQ0wop6fO6uyxwE5fvSFquxT5S7CrjXC4aahvNU8D2CiTINADdxQ3KaPmHqIyJq1DMa9gb1TkIHvIESOUOOdg39ipJTRtOcNixTGlJKMC2H6gIVmAAb2uCJ5TVgMwQNkpWhsvp+9S2XVIbk0PL0I9M7qhyBUbuB3VbkplJG31ANQCfu3vPZ7FJUpNbtTzLm5tNULzQb7+mCuyO8i4mhuYRlfejOCLLH3DIAAcL77o2baOHMB5gyC9LmazFmQ994ADR6dzWkY2UbsekgKGAWA1XDld/sbQ5AFHe36h95qHMdZldFyWabwO6h4l83ZD2+gf967C7GdYnsn6ezh801yshtkgldPgyNXKbDQTOxrzUi7Xp70bYFqsiYDuz09n60pUU5UczDm0s2YCSj6rYea3gp+SCN+z4M8zAFJkQjBsHhDZ3goc6juOMOB04LFmSy7IQ2TkA8BjdMcdD7n3cw5mpOQj/iaGBKqEgCObLpi5dILpDj5EAkAF+BqyzUz/ANNmf5hmgCcRtTLtcNRWXmDlYM2SO4LyvhOD5Wi62ZkdDPgh7SPUMC5qykMGEkzI6U4KtIvU3r2QYTRj47v3L6NdvuTidts7E0i8dTcqA+cHE23H/oupO2bSKmneiARDYPtTKmmDu8VMboHNeQEJJd3CC1RBMLbRegtpH/wSL2JpWv8Av/ilUiXj1OkZSY+56rxfoUHxccP9xGXiK4pw/wA0iqu2yL+Sauo7u9SmSjtHd31DQDI8V5/x9IC8UTQY2LgB4vZJ8ZBjwZBULmReOPRoNMFXbv8Aj9iNGTWRxI6vkjsxcZqCPvAN6rRyUybIu/JJ8/mqEa6fzRhg8Sbse9CceP8ALAEHwsseAG4Grsp3gj/HnXxZyrvoQwPYB8zVJ+zh46GEzKGIGe8I11JlT/OxwMzoABsAOxP5dcF1O2o/tGEqGBj6exEnS8g5syjp6h9iwGHNeiyL/mAZ7w+C1To3qGNFyhmdaK6eu0NTh6EGUepGADvQKH8EQyGtXB3pqfNAeFkBKjyXg2A6ey60VsDGGEYz5grtbS2f07CA8e9JpQ1JyEUzhgBBqAe1dhaOHHBkT5q1Jp4ozIEGn3XT5n0YCThnFx4AAEAAsr60aOfDM76hgtFzkwxzBxg4AgCcWq2d+G9Lr3Uwz3Cg8DlPZzWl49/SbuZlw4LOoJGGQk/0wujAXTLYCr4UZ19xOWZo4nj1CDTYb0HyLg3sDenxcWchy7p7zNXV1xCXO2lxeo/OUB0NcFfDmTdjmDUYgeD2GhXB4gBkAF6I2ehm1IAxOhnw2KHr5K3lwCUrM5sG6EBN79iG25GV+/Ak6xGF94XWqFCedxZnKMXADnTmCGMhAxTscJMKSTZhtMO9c2q/7utPLAhhnP8AKBJxtr03hdWsfrWfCb0XwIw7w9izHH9R/dfUGjHMnAPmZo5cplI/mYRsOSTb3gZ0Umjp9GhYnrIDcAzAnN/vWo4/qONNjgYmfzXlFuVJhZAwdq2ffTgjzB9QHDmAB1MD7wNUTVwone3oonWXWweaAb96hlktKOdvTQfj+o4xXNoxobe8zcVkLrMps6mJ7OC3rbsSMMe+emBnVwDNEkUAdvq1+Cz2LK0mwAOCvmckbTn/ADASFdiRygNnyVPKdPfs1N6ki+bvPYoz1B796Zpuaw7RwAzAyDTXaVKo3TsXGORm5wXF5qSUjYGxGlUztVE6HmAt3onEAOGBkAnsQrlB8vvorvGygdxYAfsU+hQhgmDTdD3ri5s3iYqGzRpwzMwO6rZE0AuA7DRpO45CeAxzse8FSMygdvQ96Hpzsl3IGG4wv2KHIlHCbAyPTWNE1WBg5NBiOZuoPldR6WQoJ7FQ5DKSZjlxPTjBzUZwGXcebzQE/TnvRpFXX3FrmbgOsBaSLYKAM0H5IG0YuB77rHOoMzAakHGimTcmnBB+P60kxZBgZk4Adixsiur0JIyUYPA6GJmhWZIORIM77PYCEm8yGRxYPRzFh4+YGe9U5ZSSDeiLxNvfNvYvNbbnqvshlAitncyNA2YymKnxzoZNvaf/AC1Dyk03ZBg7a/w3oSlNSTkekBf6Fivdjr12pMlMeiumBGRh71Tt5QB2CeoCsp0WSbZ6p6Yd4GCA3HQayBgZ6YAkkbGAyjJ096rZT/4kONO9U8eebswKeoAAnypAA3v9O4Lyp2K9yjjbqQDp6InvotRj0HDnpc6VWb9PiAZAD/MAztRaoy0BthQ6GfMLr2XK8r9x2wLQDHk3q3Q/YphNB5h7S9MKJ8ENLFyXDDYu2PADkUH1LhsVX8EIYi6LWQuO8wNXzIarhnTYfNVsqFpdWADXpmHMEZwWtKR5YgDRdBLsyQwMUAdMDAXAPgdFnuca0MoZgGmC3JnGhqGB1uHBZ11VhjdY9LYfesWGCZyYBtnQN/vQBkpT0dwDACof5hrS8pizjyTAg1A96DJTR8CDUDsukF0zqZlNWQAUKitYM8Gum5Mm/Dan5DEA74+kFDDmoYwAa6bmGdgAKf3oThZ2T4vyzMyvc1xbIC8Kl4blx2+Y2+9ffEvtdIh/4rcvcu5CyW+6ZQOzemeG0PHxT7V2Jrwwg9SiYV+BLp4kYufxXzmvMh98Pt+3auogfemAR/btqn6vp/NefDCOXLkuf2fNdi8QL/ouax9mS6f0ky3ikP8AFPp8014jpJJKMwkkkkAk7+e5NSQEtkquB9vATWu9K5SBFjvSQATMA2X96xj7fFXWJlaE2h+Ow0zR0XkcTsy9NmG9KMjMz4X2Ak27aPcjQ3qgEihKZ52lAS6pRC+cOjn61ZQXXo80ADvVU3d2OFEQ4loDyAGZ8dyoknp8PUX03N5+PAjOhv7/AJrbHIQNdQMmAcAWUfR+GchwJ7p7ANa6475jqAzD1ABdzn8ONX2nzGgPIRgD1O81ayqR8P5k/ZsTMfF1ZBm72UNRuppABh3gACoAe9OqhDGchK85mJJ/mb6ghvIBwChNgiSOAHIPZvVVkAAHAuayqn7Z0W3OGH+CJG76aoXA/wBuH77otjtXjnv303p3Kj6mHbHmeoAOhqXRbHigDYbNM+w0KxQMPEL+mjaC6AAAOhc0VWy+U7tfYkT8wAHXnsNGxNUao7vOnND2PaZ1APgCJGXYwu+q8LYH73FDTuzLtBhB5i+jqIhb6QZlXM4Y70yDKgR3NrwmCNoucxQNgHnOfYAImYv7XTPozTIfTaM62ZjG0z+CG3OiJMKPRoBfp/gvSEWVjXeEkf7wUx7FwJXiBjJFwz9iK5RAw8nOdKzCcMwMmz7wMLp5dMzwjmBmRsn7A716QkYOMMg6VuHPeoDmOjfZcgOnsol1NwqmYhi2BgPQ5ABK9QDWkQ2mQc1mg0z4mCuP2chvuAbVgBdnMC9D30JwAS9K+VQkxT4G0AK7ig9IcC1aIV80cJz1Q0w/Qr6HlAdbAGjHgsaPsQuEEeOZ34bUyOJu0MlW3A3Ln6imNu/h9xi2CJouftfCIDSnBIgr/euMUuG+4KfYHWwW9LppSZCEDrdzPeocUADYHBWU527ZghUikxXDqeoHsSaoUtXnavgAmTZqtyEpkW9/qGoxTwdj3vQw7ENzske/j/eklHuZEGnD1Q1Nn+hDeQdZkRzN31wP8sL7wScYkynD0gI7+xPbwk/ZcNMPetbJqdgOQc/zhgLwhG9iEslNnjkPLNPOts+8HOa2l7pQzcvf+wDXGV0eD8fYG8EW51T7sBLy2qZyr3Dv7zVJKDxP1osYjMD716Hh9Bwzkn5hnUe96si6GgNNgYMi4AcwokTOx+KHm9uUbXgD33UIPe8Fdt5uS7jwCUyLgB2AC2Cd0RGFu4ALnwoobPR9KSShiFPgt5uGKljkgwnuazTwh8DBDcxqY04YNGIH71tmW6XZNsz0QAw37NizGRFOLIPVAT9i0ROwHKx091u7snes9zEIx8KFzvzWzTB8w4YABNgfPYgPNY0Ahmd9Q15YsDRWtJu4qTI3xzsA8FDqfmAAeF0yU6DTdDPUNIphZdP3DMM39QL/AOhbHMa/9PgYBSSZ8wWLYWQYZQDDeHsWxk6ZR2b+ytDT593M7+9p/mji4uMDoXMwqafFE2sxGMD0zA7XNU+QlAUgIw8w3Gnw5gOzAMLbNqamyn5YTLqyNJaAt+w1fYt03chSlKe9U7Z+YyB34BuA/YpmLmMu9QGYmVA2GlvPgWk0fmD376LOss6YTTC60gXQdkGY+mdFm+adjDMMA5oe6ZXnGgOQdT3rPZUMz2Gey6Ns5dqYZlZy/BCsozNygGThgvMJ6DxQNVw6ATfzVVksQf7NPMienvRhY2t5BS6WWhST6POSIc0YLefH4YxfE/AzuY9ihCF1ayI5jkDN33pjbQNXtvNGDEPm4FAScCrq7Uo4fsSIL0NelowiRB+7+CeIUc3rs4B6e1cS2Of9iGf7/wBzBG6Z/DxXdfCGziGnH+Pivi7kFG1xt4oB6QfyTLeKfdAR0kklGYSSSSASSSSAS7Nn4tug4P8AEVxTv6aAsPOGTviZ9yluO3bA1Tj/AB3LsTpnsuln6EmLnmWUCMR7DWnYlrVyJgHD3rFo5+Xlg6NrrY/py6crqA4z4XvvBV8mOnw9q/TeP93dDhQOYc0eY9r1Hj7DQNhckEDpsIYf7yYBQAR/jzvHAKbz3Gu7Lja3YhblHFwZnzNZ7nMkZwnr2cRs4Ju4sw4BwNZR1pPBqOEaKe8zW6qD4U8HfLM702IezkwGsgAX2AHqK+xo06bkyXefYsl6qymg2YAeoZ8AS6r0Pn3tMgyglZU6GIb1p0GEHlwMT5gsH6TPzUz1bXuvS2Dhn91hb1Nnen8q9F1SgPRaN3pwU/HtGcj1diuyi02AF1AcivNNmYBprQn0sshmfuvHnpHc+wFW4drJZSR5ma8TYGdwADVPKaOZMCwFQD71Me6ogYFsAd9SnAAUdV7uzLZsXjQGgAen77mjAcl09i5ABKeG4c968rt9eZvNzQZx0YogG5UD7zVDnoHU5yPMypL7h3RM3Y6+T+L+D3CPWXRJxwB8xbp33Ukcj0TlKeSzegZnwA6L84s0OSxePgGMl3WlvgFz3gC3Xr76X9c9F/Qvp7rN3JRsjjZYAZnGOhgC6P4LiHDr9a9/h6xcxZhIvi82Tn6zvdRvvTJQnKTWfNAHeC8f4nI9VBg40+BlXTjGFwua1TA9UZ53F3lPOmfGhgud15XH07/g+dHl+lvQkfqPFOxwudDVkOUvHvHPUD5mvPDmZB2RR0AAO+h8EQwZphQ2JlwJvhfgue+j/BENCyRxpTe896p44hHcvegKhnSpLUMzvsQY31WHhlPLO2AD7zNawRXo2xufVugndIcuDUi5W3rNCzJhvA9imY/KBNygRpB6hnwonzLE17tgh5ZngR7Fcfe8YGwAa3QZHao3SmorsmowRwOmmfvBbythMkZFkW7mdEHyM0HmKAeoCjZB0AcMzPgsoy2WOPIuB7FLUi2kSpV3KCYt/oVO2GrkN5/61mn7Vg1vdMrqZDykyfvaNLqXje8fKhx4YAAC2YczXaVm4x3ATE6exYnMyMlrHgBPUv7DVbDmSdQDEylH8zWNs1OPZp07LSTkAEBkjM+9T4o9Tut7qtgsiyXXknp+GZ+W3+wN6Cch9c+rQx8mTFgCxGZCxmezYnTyu3K6+Zw5X729UN4vKtOA8JkZgG8AXGRmTYbMHYxXXirKf+ITr/G4tmY/in2IDwXCSbBgBh8DXbG/+ILqfJYcJLsAX2TOpmAJn4rhLy87hd529hl1LGOHuDT+ZgoY9RwPL3N4QP2GvMcX6yHKb0ZsYmL+8EnOsIE+5tPf6DWKrHpbq6i43LfstPgSo99YTv2LH+ommWrm0fP2IPezhhcxklT9aY3ljleAARiYKSvdPnDiUg2t9Cos9z0wzkGBhsM1q7gA7j9gCfpoAyUAJjZhQmzBe6Itm7bQHIM70BVWWaAG7hzV85H0HHgH3qhyjXp0v/oS69yal26Tjg7mAN3/AFrZhmAbZvXGgBUFj+Du1cBDUM9uxHkh0xwbMMTHWPmnz6OV1+yclarbz1xce4qZgTMWjOQd7qhin+HONuuB8ESR2vxDN9lzXpFjnHtAOLOSRkF/eoGJaAZEx6moF+CmShM8OYCGmZ8FGucLDmfeYb6IYpPx+RD7wMDNCvUBh5x4x9+xRorrw5i7oUA+9MyQarnPeZ/2ILBmUlG7jzAgG/YaDyA2pjOrzNHkqEASDMuHvVVKhxpTYPAe8EJ6VUjGg7DDVDZ2LjmGja+n5xgMr9itYMd6RNBl0yoB+mu3VkAwx9GguYNoDyvkgeayhgZ6gGoel6dzRPkIR/eB64ae9ULwWkUHgCDEMQ1eVgBIaCdBTyO7lOxIqc0FlUw/+ouIiDt7emuwn6e46JX9M0FmaY0AUyoC5+lIiMXA2JEJ6d+9D3L6XgJOXJMJsf8AguZGenw+xNsZeO1D3NnVouJfxTyI/tSHchv+yOkkko2ySSSQCSSSQCSSSQDh/mly8U1JAXEBoH3QA7Uvv+xehui8MGDj/ertbmGwPYso6BhwJWcM5piEZncd+9bMMzzThgwGnGuAAHwVEt1Xo2/omQeSkeZds4BnY7rY8bKB2O88B99Fg+Dd+6ehzqZXdOgLWuk2j/ZY5jv5PPeupNYc6pG2QlAx0vcj303rDSdPKdaHpeoDR960jOSDd6XAwPYZoS6VjsxeoHrALmruTM7tufRGzEquPOG1Vv4AslzGGP7vM3amZ8/0LYMxCBrqh4y4IVygMvxz0gvsR1rEYV8J3YY6LwmlJM6UA+816Hx8KkMAENlOay7pdq0cL+mAHwWuwy0o4B/2Krhy3CqvS1k3FBqOZ7L071QvRZkq9KgHsNEjzTx4/aHPglDgH5e5ep+tV/iMmts9cxs+U4cYDFsF2b+nkaVsd9Q+xaQzCDzFxZFE8eL6YGAKGvG93WlleD6UPDZQDNkXAA7hsR/noEbN9PhpMi2YB7EQ+VM5F6f60hhPFzAf7FvlMcrb78v8iMW839UYSBNw7MN1kmzjna4KSMXKzei2cVlOp352EDhGvsBbw50vGlSDAwFwzUzF/TvFR4kll+MLgH33XV/yYuPh8pX6Re9QxllrD/d8DG449NloN59i1pt3GwOkwjY6NryTD1DMFMb+n2HhyABoBYufDsXadCjYuPzFunYuV5NbvHw7ng+D+L7Y5koGSCQcnaF+YJ+JanuuBpbKInnSgOQYGGzsBcYcyNFkGZBpn8AXK/Fj7fV++BCONklizCU9sosxzUPysgHgqYAa0hzKA7jzuez5rN8s6ZzKBvA1vJFOzM0zjgAnqIk6fB45AGPO6FcbFPzoX9Nla1h4QPxwMQpT2KuZL+GkQyA8eyG4Pea7SGj3negLjFEwjhQN67SI8k26ABOAaKxvLpTQDzgGbZ0O4AsB6gmG1kDAjKi9CZ6BJGOdtnprzT1AAftAdfUO/vXNr0vEN1PorWxPJZQGWrHc99DWlx+n5MXF3j2v8zWaQXThZwJIBQ+9eisX1BAldPgBgJnTmjOy4ZFMHKnsdAtjnO6IemZrzUwAdjeifO6IZwRt5tVc7qLjDOM+2FLNn3r3B9TF8MrLrTF4eZ0uD0IBbMNxgBrAessWcz6RvQ4oBe4GYB3gB8F6HkYs5uPoB7z9izTIfTnMSsgflZJMRj3/AN66njVERi3wnnfpXe71K7+pn1u6Y+oP/g7wP06j9DHByWPigwEkItN4BTmvLXSvT8nF9PhAOpvOnvD2Lb5XRHVpuHGlSdOMHAA71fdO9EHCkAcoCcMO8wVdVER6uVw/TO93ilbjegI2UwYHNZFsABZX1R0UeL8DPAmV78F60chSTxxg0AtsgCFZWLAN5sjfvoC4dct2+48Pw/xRi3jkn+oYQGE+NsHvRJ03PN9zdwutgz3TIZmYfo6YB8FTx+iDxce5hcFzqm4tXXJDEXnXABo9M+wFcOY14ceZusi4Zt9ivoeDhm0Btc/1qXIPysMwENSnvS6pJ+N5qzEA2sgbxgTYH2IPlNarmz1AWqdWAZTzMvesxnGcdu4UuCX9pan3WWDi2aekh6fl+YIhgtHKyhvEd6cPgqfFymTxl2jFt4+Ye9H+HahsRzku+hcFfDldZCotGHUDxn2HsNFUEAmRwAgoYGqF6Lq5B42pNwM7ohxYUyAV9TZUFvCG19kCrIZBo9lAulqg/wCjdQ3H6QwN3YfGiWPAC1nr7wWWKSchCBjHgZhqXOoIVlRTG+/+xG0fKRvL6Mqph80pWUwgxw1QHggtnTcKYEbfG1ANSXMWBNGDTOmZ9gK7e6ggNN0YAfhRVsjN+p5kA307EJ6QIuGOO4cl06AHBUmadvv/ADAopOS6hM2wAT3mhjKStKGYAdzMFmqwGIdRDJn5g/L2pdB8po2plL8FpEgfKw5Ml0NO57EATvVyBmAbFia2YgU9O480hE9PeGxdhAz2BzBJsjOQYHwBNLRqgf8AYmObXdpp9PXOiY5/7oBC6YuXHf8ArScd1w4CH6FGIa+NE8bi5RAfSapH8D71x8LD/D9ye4Jan7/3pwjZv9K8e6ciHxH+Kauhf7wlX016NI6SSSjbJJJJAJJJJAJJJJAJOH+aauiALumBnnkDBj043eZr0V03A1WwAQvqnReW4sqS03RpwvC+2gGvR/Sc+e1HjbNPZvv2JmsGZ9GzFC0vIQA4XWtOT42J+nQAPqXDsWYxckyeLAwAX5NNh+xMz2bP9lwhsHvChH81bNbT5HMGV96dFyWWj/3dU+NdNjqADPsUPomQZYuSyZ0MwvREOPgAGQu/2Gq597LpP6oaBrBhMLmaxMpRuyDoemH/AORbT9SnQ/ZeHpemAGCwogpkAqGoBo6z7rODS+nxvHDS9Rapi4pk2FgWb9LiemAEG9bNi4p6YGfpgux43wfYnixWQhgboahpFAs2egHerKPF1WwDsVw3HBpujQagKyhMhsYWk2Gzeu0V02nKGp7jRhMAz2AmPRaRzNpT1TsclkyAG5claiYbKAOzvVDD1nY4X2GCn6rwbDDZ71yq6+7pTKyKOycgDdqBn7DUxk4zUcwIyv2KhK5N9y4i/J1KEBt0TNWflZTpQOx6AG8O9Z7kGjlSDADJxGYgZX+aeziwBwzINRFnTOGVt4Z770MyO4UXGVjjitmZVutRKFGa/XRA2WaMpG1IV1QDeI3XAAT3h2Au0XGm7IM3Q06K7ZgBqGbofoVxFH096M7Q1PuoY8KkjeewEc4UauAA2cQ2TRk4YCGxEmDEwkAd9gK6ZxD1rWPG8cKBpmrUircDAVGxtPu8DpvVk4Buxzvs9ikqsWpn3Z71Fc2zqBGFF5g6uigEzWAKHden8xdqPJuZXovPHVQA63s4LnV9r6n0ABMG7HAxPUv7FcYV2TFyAARkAHtT8K1qyGQoNDRa5hqNmFB94GCyRPL3XAj5hsNmmZ86d6Y3CMXDoBbEzGtH5gAMyR5Hx2rHMwNamleVPj/M6mz0w+aJ2XzJuhhvUbytHAAAoAAp8cDByh+pdVTSSuV7MJ2S63urcFDbaPTM3TV8UIOwFx+6zd2CZqvUYGfRTvO0b+HsUAWtXs2IkLp4/MXdPYpPkIzQLH5IeZwFW4UZr80Buap8s1GdjmFAbBEOQABvRDEowdvfmub3xcMVOwS9jzacvFPYhvJT3gbMDAmzWkFFMXLhwNU+Qisg2YUEzXFoipYJnD8w2dgoay7JRT0zCmoHvWu9RRzaceP8wFlGQdM7gqJn0crrKBhxeGQAEHfwBa1I9LHs3Clw4LH4Mo2p7J3odwutOelHPhhqmJgCrhD3lA1WWmzZE94K4izAahgYHqGCEpjRg3rNH2eoCgY+UbTnq8D969cexVMyhm5R0+9XDeUZaxd+9Cshjzkc6HvBZ1muoZOIkaJHwS3rV5GUA3D7PmCFclPkg2Gl64XQxh+oQyUczvQwUyLnDGYbLrImBopOu28zAhR6SoxAaRZ6MQH5ULh81TuPsvzDAw0/go0oNK9GRAPgjQPKfGdkGcgCv2AobcgJT5hfYoHmobrZg6BXVbkh8rDCTCkk2YcwS9F5VvWTvCM0exAxNH5Y/f70VSJoTY95QA4aG5EgGnDAAAARJikHWFy/eCZYz395qycJkm7iFDUZ6mpQVQnRiuPENRcSIz5BRdiuGwFGcIzc3jsQD3BDUC5pW9O48Fwd4AuKA7iVnNwJV504LkPjU1IHggIq6XMQovhfmpiA5pJJKMwkkkkAkkkkAkkkkAlIZBoub2mo66IA0xuUwmEjawRiyM/s1g2ApTn1AzDvifgNW79obUBEZ/alb/7IM03jpvr+fIxei6YsGB0RsWeOU2ABz/qGa81Y6TouXLxoF1puNyXmI4AewD2omsDL0t0DlNLIRgI9czfpdap1BIDER7iepqna4exeY+h5ul1JGjBsDs3rfs9KZmdNsgZ+sHBdLlRFTtT9XZkJuLxoHbeg9yh5RlkOwN6fOdCVIjAZ7w7ATJEr/bAA0At0DeafVKuUxDWumQ/Dga2nFugEcLb9ixDp2baGFtgLV8SRuuBTeC7HCsKs7aFHMzcCobETx2jBsAoNFSQY5/aBmG9FrLQaYbN6vp0uXJDcgavhvOihvQJLTdwAjDvRUIgbYe9TCjgccwO1FJX26UyzcjOLMA3bUL2K+jzGfu/gJ/rVxIxsbTC4Xuq17EBwH0wUFTu10yTZB2UO6meVA273E/gqf7tAXDNp4tnYuOqcXYZ70yFU8vRcEGk5sAVDkTQBul95qklTzdbPSvdQGxed3kZOGkVTecFKdM5B7P8ANQHoury9NEkeGBt3MN4Jkxoyj7A4ImbtLVA95oB2diTbX4cw71McatIpwNdhjm0Bme9VTOCKrCtEQBzer7FhquXDYAOIeeAykHf3owwbQaYAYfoTMsa3Y5iu6TQB+Wr4Xddun5fzVOMXVpfYrVuPpQ7rnU6vCYBPURgNwPevOvVDQNTDMeBr0nnI4PxDuG/3rz31RC8u4dz1N65tfa3PoFenQMM4FOHsNau4LJxwuZGZLLsS6B5QN9Dv6a0KLKA5gAR3METTOVkON4GHp+xX0U5MWl67+YLtjWvNTACmwN6KpGLZ8vcdhmnzhuFVH0ZXgerW6nljo2ncD0zUORDMGwNoKGHMwSZlPBsMLgq5mDs7T6aDYcX/AO9PbmgHgYEAgoDYUbOwXXby949zAQW8wxn+Ds46fl7tGNP1oYmSD1DAz2K7IPTodVVONGblKbEZgVyULjpm3wuoHkjORcARaONAAuQam9PKKAtmoaknIVGOeoYHVCWcim02ZtBqfrR/KaAWzMEJZZ0DhGB/voChqS6mHnvqgvw5nzDvWFZoqXMD2L0P1QIE28AbAovOuaCkgw/MBYcbrhWtnVxkw96KsHlKdQPRpR/hpAVC/YglsjBwD9iu45A7MA6b+QJ8+jjd/ccyIptZB4CDUpwP3qkcaDUoYEBgaNhinlMfANoxuYVP9aHsxCkteiXMPYkOan4uhXO+/ggD6idMxsy2BxahMD580T4nI/jDjHsPvXHONHzA+G9CapeYIcyf011AUaYBtiB/vBaFj8pGnugd6H71D6wxMbKSPMtGXmQCqD8bi8rDyAH2XTEjWmzpIMzPU+ae5ItHeAzLh71VQSN2QAf6wV9Ih+Xx7xnwot52WD3poNNn/TNVQzQlOeWfP/8A2KBOA5EwA3UVPIA2HNvqGakqRIknNAw0ANHqKncig62Zlz9ifFEDjg868VwVVOm/7RoIf6EyfQyv23EhDVMAD/NMcA/ZqJOOgDgHTYnjKtx2J+y1a46epv8ATNcSdNTHDA3NwbFxJoL7ar0EJAbfBIhAqAkQemo5DRwUB1JjhVMEDFwK/wAV9JwzMR4JzgGPiZoCOVrbv4pqdb/j+9NQHNJJJRmEkkkgEkkkgEkkkgEkkkgHD/NIf5pqcP8ANAXMV6MxAMz9R4uxEcGUYuRgdOgUug5gWS1NQ/HwKmz9S7iT3mAB21wS6k/7bZh8ppdSQzaPf2At+yE85WHjGFrmAcF42xuSNrqADC2zaC9UdPzdXocHjO5gF1XyrDDtHaPVA9t0+UWllADvNMx80HY72/vNMJ1mbMA+8Ni6U+8NzP8As1Hpdo/LAZ+pdbrgxAWwuFKLCunXQajh/UP2LTsbmTCQAU2d66kOrymG3w5gE4ADzBEIzPTpTTNZpjZoagb9O6Km5Wq4Bkr3Z5SJ4r5m5vNE7bobEExXQCQBmexXzMq7h1PYkVKvK7eC9PYoDkU99D3qSzKA26HzXFwwLv3qezp2huQjd51uCgSIAFzq4aJLhpXA1VPCBOcFiz9WoSxoah1Df8FMZgUbuYE38FastX33op5NALYW71ipLqrsN6TINmfeqGdfScqjZ5oAb2gKG8pFPT4adwW9lA9swKRQQ1DUx4gah0M964jFNq71+CochK/EADR/rT5n00jqt27XB18LowxLoA4AAf6EBxSM5G0EVY8TGhlzuqp9IMmWnR37uABHpuIhJq0YA/MuCD8b6sgDL1KI5j0KOFz3guR1+3cmcM9zX4dyixnq5oJDZmIXXoTNMA/HPYNzWG56KYawbth7Kd65PX0XfwYPc4ucAwAr3R/DdM2we7/ghjLQ6XPvDsXbBzwPw0T2GCyXhvHTcgAj3A0ctu6selFlGDlANDD+9aRFdMmwMfUBNgyZXzcUHW6CoxY0A/QpLLoeYuPpqZS7Z25q6fhpWjjg1ANoB/vT5EW8cAHmrUWj0wP2Jlg1KH6dDTZJqvdSDjtVylKGuLmNMHDPsBEMogFu4dioXpl4x1S6FVaqlGAw/mqcnT1D2UBRspNPTM+xD0fNsuyDC/DsRVEau3bIXNwwE6UWe5CbQzB30/mjyY6Btmf5az3NUOOZipKFSyXqQwNt4xrsBee8s7+MOx963XMGbTjzJ7AMFhXUQaWQPZqXUVOH1U5flnRTMaerQDMgoq2CerIorXGhfIGAbDE+aNON1a70iAbzOxsgfqBfgoc6b5zOGAGVAOofoT8LKZawb2rsPW5+9QBaB2YZwzDzN94Jbnfak6ixZwM5GkxXthhcwUbJSr4sDvvU/qa4uRtWwGHMFQkASofpHSiNEVKhyHlprjLzQb+9cZEIAjhpepf2digOEYSHgD85Q/NG1GM2nvxIdiEuSnR5MCkloyv7KInxuUObjwCUFPeh5nqiNKgAEoBuHNPczMAYZm1zW5oupLKRYx5AwEBDeqosNVs3ri5srRPblG/Iudqe9RnJWq5t7DTK9wFXIExrKHcNML7EyVFNqOBmA3RU9PAWjA+ap3J5yo53DhwWDNBgo8l32pE1R0AI9Q1JcM99dm9QyD1EFkQh/YoxU5hZdiE9TaF0wgMGwuCYWYR8EiCyRBwNL1NT4IBEIfbv2Jlg7jT3BMthGuOkZOmAggOR811Gnl/mmEJhyXNBjmkkkowSSSSASSSSASSSSASSSSAScP8ANNTh/mgHidXAP2qUUk3XBtsUIf5pyx/UyV/j/VylAPTNeqOj2D/YOSFx2MLyHGf8Wcow948BNewumSB36dgbXp6oAnyPtZYOLGOOYB6h8jUNyOcXOXECpffQFT4uecXqw2QO4BsWnTGjLB+ZFneYc11eU7g+FlgXfw4UDZ80eQ3abx5rMcLKAYZgXO6PMfIAldNOjypp2NlarYXNHMWUeoAAezvWS490AoAmSMIM8/Mh2AnzTuT+2OfOmOz8tEkOUZtoPZdA2wO9zV9FdM9gbFuq2rmRIMr1FMbdN3eAIebD8Re9FfRzAG9vqGvFUyktmfsUxtoDc281xbufBTC9Khmk23kiEGo535gozzuu2AAa7OXdj0pqLizHMJAXDTS6+GKl2bYN3YapM46DTYARi2AIqlOhFx9+9Yh1d1D6hgOw1iZ3ZGEDLZxlpwwYMTPvQT5zzWUMB2f8xU7zpuuXE96ssO1aRcwua7GfRDXoLYYyScA2jHejmCJ6YMnVszPmhXSNqOANBv8AeCJ8GDxSA80GoHvXv/rVeN7+45igEeP6W81PLI1oHA1AJ1lqPs5gq1mUZTDN0CoC4/X7d2driVKCRHPeQH81m+axzzsY7nRHLz4TI9ADTpwBQJQh93+qG9cyp2qqfR5yyzBjIks/r3msocmnDzH52nQ+w1v3VEX8QZgvOvVECmQN5q1+9J+CNtp6LzgTJgABjTvXoSKIeXA2vUAwXhLpHOHi+qGb+/f+hez8Tl2Xem40loxcAwRNKp9xaOzjZXDJmDgexUMOUDrYWNFWzy4G0Aq6aMdidDTvfYoZCD7h+9cSdpzSGUyEfbzT9EVOzJWxul0MSnQC4Ae9Wsh8wkXM+aHpTX4gzve6WX+K4DeSPVbO4aYIJjwAayl6UAzRzMOjh2QxKd//AFpFMVLtIIHYfPegnKEAtmAq7cm1b37EH5aYBNmd6JSStsu6mdMJG4BWG9QUOYZia2POSgdaMC9Q1j+YYPe8fpqenD71gEx3zi5EzENhohxcoIsg5JhqAZ1ooceHq3MAUyLCNrKgFLhfYlz7uP13DSGzZPpM3ooUM99DWe5rLScdHM4oG28e8zBEPUTpwo8ZmKYgBMBqUWezsoZbDMTS69EkmSOqJmZ8AN09MwDvSLM+VjmBHQz4IeLRFzWa9Oi7WApABKZ/De9LkZXxEzNo9wkgFv1qkyAA7IAw2H8FJZAC8D8u9sMNirW7+YoZ6hgqNE1Kqcxx+YM7g2uLcU/MXarQ+aspTp6h14exITAOPppkpaXEMwBvgNAVDkpQFMOpk2AexWRSNKGYDzMOCFZRWO/C/Nb2jcdVl3fuA0idNpswH1LqteuD9ADZ712bOnNGdqMmCd2zOiYQ3bv/AIKS5QN4JmwKGJowMuNQFvYdEx6/lwADuYqZsFu5eooxGBuXAKL0tAetsSbP1Ny7Ob0xsKeO4EFnkYae5M1T1Aok4FW9ijCdHNqAkuBzvzUaie4R6f2Emi5U/t8EBGSSSUZhJJJIBJJJIBJJJIBJJJIBJ39NNSQDh/mly8U1JAdWxu+AivXXQ9D6PZZuXBeT4dPvNi/5dxuvWfSYg10+yDW8+yiokayu8H0/q9cAZBqAe5bZKgB9xmFNhhUPghLDgEK8ml5J7ABaFY58cGQMW6BWneujwr0b30ZXDaNqRJDbsc2Itx7Rk5cTuoA4YwzjwOvCANHvP3otmRQxeDZNrebqumV/JMiyjB2iKob944GYFvQBHkGEcDOraJ8Tl7R9gC5RL9H03Ctw0KLKDTAB5iifFzTNwALes6gyDdkgZmDZoqhygGQG8QNFVh1eUxhoQ+9X0Ojrf/LQxjyM29yIWb6Zg0vdHyuG6R+HqKYVJHhuUaK0463Q1P0ga5LzVmZcWYpjI57FJkUaj0DmmPH5VsDE9T4KtkSrtmbpi2sVTczsPZifTHnfZsWA9RGbuQM76nwWzZY/NNn/AEwosilRTPMGFE/w53e6IqVDHYM41HQ00W4mLRwKbKc08caA0Mw1AVlFa0pgVP8AsXY61DnVPuu2ROPIAzq4HsRVDA9hgFAJUMUT1AN0NMEf48GXY4b6Aoa6wt4TEQh2o5sDUXZuPds9lDRUzhgOhgF1dt4QzbvQg+dFxqra+aAGgcfjX9FFQ5A7xzAjotCyGOeavYC2BsQfkIX4cNm+m9JqlU1uGV5yFdszH1KBZYzmIQG4eqyt+yQmFw7FlGej3bMwS6+GKlhUrFvRcpcA0+8Ft/QvUJ+WCHKPUAEASGjdkBfgCvsDC9e4GTdDWJluaen8bR9sDE+CLYrto9DPYCyXp2aZR9EA2Aj+O7pcz2exOhfQhIGT3qtkHVw6+n+tcXpAA3cFAelGccEzTyZMnb3Nx71TvTfLtmF967SJRm3Tag/JSDB0wRpinHJTT3nfehWRPPfcNiUqZfZdDGQmnvC+xbQ1RTMoAOfBBmQykYo5gR/5rtknTNswDedFm7hyXchQtgXSapD1pDyEq0g6cOxAeaN4HKFwWhSIF2zMNlN29ZvknTlSKHz4qSqcPufh2jdkGG1uqu3oB/eBvbaMrji4BtYfzLoE3Q6XU/IXxvT8+SR6mqAGHwBYn0cbr7gbKTTDKMg6BUM6ndCuSaDebXvV3ImhlHAMwFsw71AyEI2mzPsAFPXuRoN6VY5+80rG02AO7wXapuuAYcPYmTBB2PQj00wJMcACRcOBrjpGEw/YuMczYhgdCc9TmuzZ3cvfYgikNwg84FlGkHeYFeCUowORt4KMRUcuPqKiXNv9xJmOnpgYGqd4L+OxSZgmDYbxooZCZt0I9P5pjCM3czoYFQOCXl7u81JubUel9igC7dy5emgzR5Aeym9Ig/fQEwne++9METPee9AITDTOxriTVd4Hz+aTgh2JhHegXQXRnBy4pOHai7CFeZ6iRCH2bUFuLhnp+Kjc1McG2zguItB/NAcSIi8Pim7V1JowXIvCprx64pJJKRskkkkAkkkkAkkkkAkkkkAkkkkA8Qs4A+5WreHfdY1AMKfrVY2FnKdyu8fjZJuXIxYZ/XzQFe0AhkmxPe2Lg3XsfosbdHxjFnTMwCl15UlRab4oadP8zWu/TPq2Y1PCHPAnADhdMkt6ibaNqeZvmNKAQKTByRxcoZjbeFj+C49PyoGUcM5R0ANwKSUB7I5B4IoE2yYc6KqawoIcky60dA1DM7q+lOnKx4POhQADYCXTvT0aA2ZzTF94OAe9TBLzTkwKeiH5exdWa2fNKdtg3cWBjsD5qTj3WWnAjXEPmu0UDlRzjbWwVUMUIuUO/DU9MDXrucKvA2gumMgAHgipkzPwAw7EH410DcoVXARPBM2pHvA0U7/Kmi4uYZxwDvRtj9196zHEu0mbuC0Jt0AoYHe4KPWHR5TsYRyNpwPYasnqeXuRoehyLN3vsBPKQbrlGgKi9rrg/MHvO3kbALYqTIPhqU/LVrMlA1DoAHcOdEGTJAalzM/gkVszlPvg+U0DsfYfYg9vHAWc3nvV2Ui7e09iqnDMJgGHp03p8zcQfXJduY0GoYaQc1QuCDEy5GNwUOZ1M9HbAADUNCWW6hDy5m6e8+dOxeV1tDXDdtLizAORvNaRhzZKMG8F54wOWCVQ9zgLXcTKq4FD/wBZpNUZnDcsfKZacDVPZ8FqkXKYoceFwFygcNNee48yjYHe/wDerIc4Gw7jTsBSVTGR5npUOY4ekzoewFj+YKjgUPhzV9Myn4gDI/8ANA2WmRhbMzO90ffutmfQK5ggabMyrQ1i2amgcgwHgZot6iy2q2YCdADhRCuPixnZBvSgI/giaFVj7D33bJdcAxA3APvotC6Nw1o8k5ADfsUyK7G8uYNMjv2AFEQ49oIUe51bvzAE+BOL+TGaYjKGBbwPvRnHdB3xv70HzjCQ3f8AuVri5ABHALk4YJdVh0oFVQd2X2AocoNBu99QEmXTO57qKqyEozuHz70ya29QJEizhmHYhWdKZO+9T5T4C4aAMtNAGzOhNmnI6VU6RWQZ3VDIlat+9QJ2SM7gBkq2DKAsgZkezsS3KqsJMgw8uer6aHnGgBszD+xFuQjxnWwN3gapJTUMY4aSzUoarYDzEo2sfQDJsyQHHim/1AFj0wujDONGUj4IPcaktTQNq1L7wUtOdXu0JykrDnGaAaR+fzVPlpQNdHvMu0ubBhvRVFa8x03SKz+JOlzugPqYXhbCG+FHr70tw6r3ADMUAbMwqBhwXGVKMpgavqAYVoruU7ABsKgV6cPmht6nmPXPgdwQWp5kCTAkazRmbJ76AoAlqxjP8wzRPkGpMfH+ZA9cD7EHidHDp6Z94JhFU7DradAPgrK9MeBmGmdFAEwFy+6h8096UZ48woQAHBBFUrSAD8TMOAKM8PpXvpmp4mBxzMvTBQ3CA27jvW9YSX+4hvCZthvT23QCPQguC4kXqbTSIHgbuIXT9sJ4uxjbDZpqMTTJuUEBXHVA/HdzTODlxPmsgxyPS4DzUNwT4HwXYXTGRvPns3p7lxdoRiYIM0qiaMEy1HNoK1IT0+01xJoCc3mQeCBXuhk6GmmNlbiX71McEP7FDKgcOCCzy/L3Glb01xENXfuTS/Mpu2oLdXBPsXEQMzM/akRmK5CRD47fFAcUkklGYSSSSASSSSASSSSASSSSASSSSA6idXFdsvwGmwMjJw+9D66tj+IBZ/r/AEDZun3cJkoYaobwPgtXxuLxRuMnHZFs+86LCulwjHIB5rYYHQwXoTp9oDcufAA2J0l/+xseFaxUKGyYmLjxhvBH87JMwujwOKA6x7aLE+kWni6ko7vC++62CZjfO5SGFy8sO41bChD6dA5DcmS+ZOHTf8FxHKA03JZENMLq+hjqtnAYDQjHzMAUMcXGPqBkHT2GYXD3quaO5KfEnJPIHsKgd/vVlOigbpvOnQ0Q5Qo0KQcaAzT2fBBky4SD1T1DPsv3pk07PCk+Ht2Nc0WxXTBtm/ee9BMN84tDENT9aJGX2XWwMz00uqfQcPeGiwzDT2ozxoarlD2AazfEvm65QOHvWi48DBsAH1D71zqp2JrEDOO0DTdA4Ls9lI0VugBqPISyGUOLsDmHYo2NJ6bMCSQFQE+Z/LZlVGFxOftHMzPTM99EB5KeZyQAN5+xWWammWUMGtgBsVa3i5Lsa5AYGfA1bU4HDvEe58UrtXM9i4zpoDDMO8Fdt402Mf6oc+CjDgzdmAFNcz3GkzSqvJiI2DGcWeRcM70BVuS6fjRXABo9e/M1qjkI2KMiGmB7dimTOkjPp85IB3hT5qSqcr/M/wCRm/TuLDy5gIUAOCOYONmA6ARQJyiu4uECBjwBre8dLhRaj0vg9JwDdZ3mff7Ej7HXyWXSJUyE3R0CAO9U5ZkycAwsHwWtdWY22YOjIgB/l0Q2PT4feAA7GRMkf5Nx8gmVlJLrdDAvgagOYvJT8ebxgTbIBYDXocenIB9PgZRhufDZ3oJIzi5R7Guhpsnsp2AafU+jE+dd3h5+ZxH3jMOM76dHOZonx/SQGZgbOpQNhgi0umjj5x42gLZu3oqwMUDyhgYanb+hQ/HQjv3vbPcP0rGBx6TfeB1MDUnLYY2I5vNeoB9iNhhG11JPeD/dqUP5qkmOnDbDVDUhmafVN+N5NxbLpTUmLGAytQ0sblwPI6JGtU6uxsOR0fAnwmdgHUwWG5iH5WYEyKGwN5gCkp9HPk7+2otyK0APTuo0qKZ77obxeXCVHCwUMESOFqw735/NHKsWumov5A2UKkg7dqDJExk3DZOpmjbNRZIwzOmoCygYpu5w9UCbC+9dLaXrSNKagOtncKX4IeGEYNmbXAD5onmeW8wYUuHYpMeOyGLoQUPkjbh1QbcMzhgBb6Aqp70pAXC9DWhR4cN/D+kBOSQOiEstD8rJe1efYi0ls9zzRlmKB6gHwVPj4pyswEYw0zRO2+bWUB6QAGAHwP2KyZxsYMwE+E8J3Pez7FLTnd6wnx8WeJksyb0jAe8Pes966ixsplPP4094cwW5ZqKB9PshIP0QDeYdiwrq6Gzjcr5lqSTDJhzA0twmRSmngkGboE38FTymvUADPmCu8pkjCQdD80Ad/vQ25KN2RQz5/wCCYY7NzTit0dPUD2KnlNAEw3h4GphEANmB+oZ8FDlXGGBiginFt8BuBKYR6sPbvCipBMzc3KTq0bAOAIIsm5QOtmy6GnRQCGrlAqYJ5GB3oaYy0BSLkdEJL/cQHrk4FfTXZw6thc12eEAkbOxcXAtRMl7LiVOe5cSIAcvuScae1AMP/wBaY4Z+z9aYDHAA5FwPYkRGe9Jy4R6U5mmf9gILIXTBs72XYQB1vnvUAn6uU7F2bdAg+wT00AyQ0bTdL6i4tndww96kvFYNu81DJox8LUQHbjwqlb1Fy8Br40NOcA+aAY9tdTSARDlvXy9uS5oDmkkkowSSSSASSSSASSSSASSSSASSSSAS6j4WdCq7xYsmZMFmKBOH8EXx8XGjw7vw9QwOl/mgCro2AZZgNIBcZpvXoTFwDNwDoTYGayLpfWiwzMY2mAHsWwYGbPkOADuxkE+fROPMXSLkHtIOZgtUjzQaxd9tzpRZFDkGDet+ZdyiNsWD2R6ojRhPZyNPhYJ5WUZGazGaD1j3nQE+Hjnh6gCZK4HuADXFvHeV6okyTPUMNgUVw8Bj4hJds+8YbA7ABVSfAMemSXeqJOkBOb1VPE87kTCmod1tnTfT33pHeMgEA7zooEzp+MGU8tAjC4d950VErpqIZpBgPSGzN0CbAFcNwnjmAABsDgtX/Yh4MUyDoCBnzutFx/R+HxuLjHIDXkjvokVN26k+ZEQG+n+hpn7JhMdZJu4K+weOOHkD84GwA2B71pAnJdwYAB6bIcABMi4ZnUCS6ZbA70fgFeZcMolYuTlOpHqBp/8A/CMHIoYvpsIzQadw/vRhFhAT4VDXe7zBUOWizJmYCHFZ2cDOifNfi+Uv+Zd37s9wfT72Z6oOwG4Abj9Pmtax/TwG3R0B2Ikx8CN09hqAH4wwoZgphUi9PnQPWd71uaLryb3tm+QxwHnLgHo3oAKS9iwxuLekuhvMKgFEbQcXryGQkBqAAXD9aHuqhktZWMAWM3ToAAHBLqogz/Ju1DDwYSsWBmHrBuNFrkMGuj4YGF99zV3j8bpRwAvzqb1ZY9oJUeSyYbAAwBc6q3/AyetgPpfDHM6wkvOs3jX2XRtOIIfUhwwq3Rzmr7GxQayAaQUBoN5oYnNBI6sN4g1AJ/sWJ/4lU1Fq2dF811ZAAgJwDMF26+xoYaRDkiemFAuru4D1BGCm8D96vutMcE3pOM8Qamz2K6cX7kflx6hWC+GS6XZeaAXKBYwVP1Rhgn4sJ8IB8yFC2KZhxCLQAb02TCh/BWukbTgBom5GM+aXVRguaxYGhxTmx2TdDUeMDA/1guOPxZx+oDMNgHuoriLFex31AmBfUjO7g+CmdRUi4qNJaOhguVSvV2p24oP4eeDVdYDs4CUXpyH1H0PJZExB4NwfrUbBygi/UQAlGNJrB0M0WxYYYjOPGFm2TRP7hn7VsEnPycbIewM8NMw4bOayLPOnCuYhqM86B2AvW/1E6cZmQ/vWKAuPU3mCwHqTp4/2KjZtgBcADq+HwTKdXl32BsDAObiznw7Od9FPj5Gjhsu2bMDpvVrHaPppxl6OBeQd3h7KKeUrCZejxgIGXf8ANL+/VbPe4Rs4d8GyAd/A0KyMay10v5kw05Jns2IqnO2x5stGL5gaRNBlOm2WQ3m0dwVc8riGK8mLZRIxYeXAyDmqqQ0cWQyboHTgfzWxyoTI9PhcN7R+xCr2LDLObAppcwT8JdgOY6cCReL6YGFqKnzjoZdsJJ7Hqf60W5bEG74GbQfk8wQTKaMHQNoCoBpdVgiq2G4uNOZMMHQ2BtNPZxJ47KgYeuBnzRPFOMMgIx+mbp8/Ypkpo4+UOM6BUDcB05qGqcrvSnzUp7yZg1vAw3h7FmPVTuHynQYetQwOhh3gtaEAOYcmguAHMPesf666XCfIN7FmLD17eWvzRLivP0yjUg/LnqMhsoozYXcMwqAKfOxclrKHqskxJ7/Yq1xo2nDB09M/hwTDZoxwDNw/Z2GuImYY8wd9RT45AOwjHRDmoEh0DkHTh2ILpT3pM3+9PLe2akuUFu5hqGoxOhqcOaEtozZh5c/6aVjHsSIfTMEhOjYAfqXQQjEB6gfNP/qGAcwT3HadieQAboGB0OiYDG3Qa2EmaQG5sNIgDU3+olQAj7Q3pgJxoybO1dira0cMDXYjMmzsexcXA7xQWjEFJHBPJoNO9ErXd3+mkTtG6Cd0BxcLSpRcSfM+SkkR6dxBRnCM9nsQDCK6VjTKl/wXxAJOHxqaakgOaSSSjBJJJIBJJJIBJJJIBJJJIBLsI2coR0H/AKpCZj4lXuVjjYBz8gACBU7zQBDgwOPEk+VkiDzoUv7Ef9P9OHKhyZM0yOMAWuYczVI5g2cbDjA0BHfv962/F47y/wBI2QMLmf5ify5bIqlP0/FD7D2eiDiPI/pQ9h0M9iqsPjTBxkBDTA+aLfJB5YzALndPwJ+xDj4oHi4cYz9a9jRzgY5xcoZiGo9wQrBixmGwkvvbz7FoWFnxmphvAF9iJnCuVrHh6Ug5Mp7UAzvS6tXpsYY4GQah8AoqGUEmU4ANARvGavm8WAuQwlBqGHP9afNHcl9Dyj0XFsxooFd3nTsRnjwZhQvM6Im9Tmap8XCCRkLgBNgHsV8zHCRmQB3h7ATJo5JbKTMobvD9aPIuLnyo8aSIeiAd6rW4oHIjMn6bN1rTLQNYcK+mABsBPN0FZAeQxd3fTP2Gq3Cm9mcoYA9pxgRDmIsN3Hmcx4bmGxQOkwvI8tHZ2AfNIqrhjVtCFrFYbp+jQCZmG81Ww4H4g5Ihpge7euLjQTepAhnvorXJADTbLNyv+tT1V2RVWrfKhKyl3TuAHc0+KATMoYH+SB7EzLTQxvTZgxvkm3VtRsTeFgwN2vmTC5mkauB72mSp7LHUgAPMAQxkHwdzn3lKMXGY+8KKnbmvSpE+SYb70A1cSGgdwcaNtp3h3pmtqpld9Om9Kx70yRZt6QCtcaBlmPLB6YXBQ8SAR2wOmmABUET4mKBzHpIHp35pn2r+E+c0bUcwaMGAPYfzQeMU48MHiMuewzRPkpEbYBnqB2AqGVebhrlwANgJFe7c+kAMZRn1oBtGR3Oi1HPZkB6SZgEYtyTCrYLOse0zDyGtIq4YbgWIZjq/KyvrSdDI4AHUAT5rEKvxXb0bg4Tx4Pf+dep3RtDj1jvMnUw7Pggno+eEptkHT0zPfdapFhgThmJ0MD3/ADSM7hD1m4vDNMtjTBx6ZfToB0/QglvJef6Tkg6eocc6N/oWtdTCy1g5gEew+Cwp6EeOyFDOgOsXP5qCq36Olw+FblmpMWZAmCZGDO9g/h3rY8HlI2c6fBl0xN4g2Gsuca1Y7J01GTA+fYpnR5nhupDjO28g6ez4L2axZlTuNtIyzRxel5IP8A7Fm+Nixsp0vksa6AuAYHcAW0uAzMx8mBNDUAw2H7wWRR4T2D6seD8yjmz9CfU7Scut4BLPTgTOh5OKdP8A3e5B8FiEjCSYeQkxhMbgexexm8cy11BJMQoDwXMD9ixDrLDeV+oBvMGLYGdwU9Tfo6PjeTds6xes1AONKD1j2Aan49o4GUuAHQ9qsshQcgyDux5rddWTJsutsmJ6lFXNX8Gfw2Zlo4BDCMdW9UNh/NAzgvYvKAZgQUCj5o26idBrHQ3io4d6GqHJGE/Hgd9R4A5+8FVYqgTKJ6HmJMm4uRj3/BCs6KBSAOmmye8DBG2cwx/svRo9h7gAEGYkrsScbN3gG4D9ilraWqCWah2mMvRT06GBIwbkM5SOyEoBbkgHP3pkfFhNceBo9TvBTG8M8GLC9WzA1DPu5vWgk5izi5SSZ28sfD2LHOrIr0zOHJhSSbNrYYA4t4y0o2nPLGBNgHesH6myzMDqwDaMTA/zADvW5lAx/KZGTvCZG1D43PmaG2QCZIAPy6c7rV8s1Aylz0RAw3BTsWelgZP4nyR7z3KuZChkR7zAZarTvuqSU0cXIGB8zU+RKNpwAdChie8FxkEEqP5kj1DDgms7VThgbdL0TCEPLphAGoer3pPXNsNLgl0RZgtH43ua40M3dvYuw30zA0y4C4AF6aWQ7EPphZcSDvSv6d77Ewio2BoBOXBq/wCWuLj9WwNJx0z3l46gexcXHQCPw5qgHuO2a2d/YuNgMKGuPBwD7PYn1DeaC0YiAXFGI6ObF9d8beP7h+xcx9iDEnVPtAVHsZOkfcnWDwb+wUhp3oD7qbNwfauJF4l/FdSoP7qJiBTmkkkgtzSSSUYJJJJAJJJJAJJJJAJJOEbn9itDx8xqQyD7JsavhYLB2l/NAc4OPk5GR4hHC9VrnTPTIRZDMZ2SN3TAz+CuOlYuBxfS95rOofIzVxjQPKZwAxsMnAvzp2JkyRVbT8lidXqeHGaMXIzXMwWiwYpuwwjRz1A4ACk4/p42phnKMbmHBG2PhBFbjUAG6ArfiC7Q4OLZhtnPyJi3Ga2U95+xUMjMnlMyAQgGJAA/U2JdXZkybCBHPYB2M/eZ8AUOcDOJj4qAAXknvf8AgsTWxAzxrXncgEY/DUAAvdE+JIHcwzGE9MNepoex/wCD6Xek/wD8l0L39gKf0/cW4x997GaNr5a0JBFzj1T9FoF2xb55LIG876EYD2XQ8M8AbeO9zNWseU87jwjRw07nvWj4HjebCLHMIoEd/YiTCvhF/HzK6xhsBCsOAyOLZDnv3h70SR8ccrORqhs9h9ibMnVWGlwZQBDCTKZ0w7Lowh5E8lHM6C2Afl/NZ1lJ8aLDCMVXNldiM8LFMOm/Mu2bAw2Aa3pjaky2SCbMPGsBqST7OwEVYU/uvF6JAXmTD/Qgxx0Mb1B58A0w4AZowiypMrFnJMPWdDYk1XuZ8JmNzLMXKPSTMHDPb/ep8g/O5AJLp6h9gAhWLAjRYTzxmR712huyXXNYrAAcASRUiGUcbzgGZ6lD2J7wAeLOnM+CoSkRgmBqnsDeaoc51gzFxR6Tw37ANefcCZu7dphm1lIcZoNl7nRdse6bsySbvoAB7DM0E4PMnNu9IMb+9Py3UrLToRgMWwdOlwPvRM3hVO9tag5Rl2OACYAF6frRnFdZxeCMyPmG9edYuZPF5tnzTw6PYF1a9UfUiMGDAAMfLUo/Q0/lN3vCqZu7WUzrUHerD9b8M0ZiCtY/VYTOn5IXFunBeNsp1gDTcnQMm9U9in4nqieUc4wyfRAKnvSOU3F+7rT413D0tFdPJZ2hSdgAYbEGZDBhFzBvFsMzQTH6jPDdPY2SB6jzpnvuriV1uciOZygAz7KKqptby5YaLh8y9i5Aap6YNd62zF9aQ5UMAYkjc3K8+a8Q5Tqs34ZxnTBgD4GBqN0v1eeNyDLLsnXAPealqbiENeNd29e9SZ4JXVEaA1Y7vgNEPdcUi5yM86ZAGnQD7AP2LEMT1uZ/VQHpkm8YDsBn2In6i6t+9M5JZJ5o4AbwMDUmdxsVwuL+BPjciEiOG8DAz4BwV8LUkZAPNHwO4AfeCxnH54GupABoBcjHwADWiysyzFbZOO9ThcDSJn0e95uLbN0/lwn0jOnpvBwP4exM6gxZu5gJ7R7ACrgLBG+tTx3VkZmKBHGAwMz/AF816HiyvvbpM5IHpmYbwTJrcYcrvwuL2rW3Td6fAyAWza2n76LKM1i3sjIMzPeG9tajjxki3JN0BoGw1QuRQ/aADAxOMa3/AMll8uuHn7qZoJUNkHT0Jgbf1qnguvQm6Sg0w7PmtC6+wxx85rCBOMu8DBBLhvOyGYxADhgkVuLdnUXCfKdZmYs9X0zANgIYxrtWzDmaJPORnY5gDI3DaYIJeYexfUBmBkDJOLo1X80lUuI7rzrbzLvAD4GgmZCjRc6Elo9hnUwRIU8BzF6eiYbzVJloBzfxMAx2HwSKrZduMfGvYvriMcIyfZdO5h7Fd5x2rZ0Z3gfYqeLKkxJHn5oaZgGwEWibOSbB4q+qF1iZ253WmRZqVGdx8mNK2UDs50XmDq6OB5DzkUxcANoAB816E6yGnUEkL6eqFf7FgOawz0XKMgL2pGA96ZM4ThuODxQ/MtHT3garchlDgTAAPUDnsRDKM48c4zTOmYH/AKwQlmhA2wP8wFuaZ2rc5Ch5KOEkTJgz33QeQHFx5sgeofvRtOdZHp8AABvpoDkNPA2ezZ2JpLiR6re4NM0zeDdFxbfpIMD5ri46epzS6eVTsO3gnlTT3AmDs5ndcXj9XbZeZ2QRB+H28EwQMPEwJQxK96WukLphyXoSSMFGcO9/6gAkO9xMsG9MB5On5elNQFxLY3SiQlXnwunkZm5s9O6C0ZwgDiCjkQ+IfZ/NSCGvh2uAuTniGmFQoaA+CQUSL8z9SYO1wF0e7EGaR0k7bX+f2pqCzS/gvu4jr/NPrYh8BUsWwYC5Fc0qgrkkkkgEkkkgEkkkgEpMdh6VNCOwHi48fjUBUzGQAnzDZKSMc6bL9yM8B0Hm8h1AANMuth2PUomZCtx2Jn4nq2McyALhgdvAD3ga1nE4vN9WtvTJkYQ37HjCgAHsRtj+lOnsHmfOZzJFlZgBsZ570usuqDj/AEvNnGsjEjHsAA7E/BGthIo/SUDOMw8lPKcYHYwZc2JkHqh6Z1A8GDrjsU0dAAOZgCxNkT8wZunvdPmZrTulYTMeGBmdLv3NEyXb0/07eVjwmSN+sGy6mSpphDkyb6YNBX9aBsf1Dq9SQIbQF5ZoNgArXqp02ocaAIUMzudPYnV8MQpIcgJXWEMH7GAOa79/8E+HIPM9cSZJBqBr1C/sTMHQoebyr4abLWwDXbp8NJwDAOZmaxB8y0vMZmNCjhGBkXDMACimYF2TKb2g02F9izpwjdyl5FqdhmjzCvvDEAL0uYf6FlXLVBhhFo8dd4LiWcMPDy0ONv4XVaTsmbIZADE2eKvo8IMdlGQMxceNa2fNDPBtT/LxmZRi2Z7jNGcc5juUPyoFQNl1nrMp4JByZs8W2Q4BdEjOZMsOYRZNAPfdM2dbS8PCxTuVA8keoYbt53RgUqNNmaIPEwzwCixPGuydh7nL/mH71ouJiyTcAxjFS6JoWssxjQNwAaeJxkN6J8a6f7PmbvphxAO9TCaBrHgDptXPmp8cIf3eACYuaR76JFUb/BSDCkniz7A7PmqonTiwzu9R4AtREOSyjMeNcj0wC5gCzR7JHKmG9QnAM6gl1WGpnYbnZySGPkmZugZnQFl2alSZjYBHMm6bjM1rWUxrLuHA3T4GdKIMKKBuGAhqB+hM/LER7u740xv4BMfqafHhhDICcMA5hsT48iZKkAZgRmHfdFv7PA7HuAC2YexQxhvQnNgFRLnycRh9Nw4cLVr0fJO0M3ic37LuIbnQ8qUOSyZkYH2XWhR2jfkbz2Apn3WGrwWJ73F7dyeERG8MEc6UmOuAYGTlOwzUxvF5KFHMDC4LY3OnjNu4Wb9RdnMJSOAFW/vT/wDJv6dWZi2Jk1PkR2YxgWzgBrs3i82TlPMlw3rSJGNMJlwDYHwXaPDeJw9i8nybsyvG4X/Bj7nTmYNyjsnnwU+H0/MhSAB09RbGOL8xQzDTMVPHCAeww599EnvV/AmY5fMM6j4uNqXECcePvUwscDThhQ3AMN90SSoARZFAPTp3qBImmceg9neoPy3BdcruECPFDGxweuIU4B7EMZbJZssgZx5JOAfC6J2YcmbIC4cz5q4c6eZ4Ee8FL+W9uV35cI+gB0+eVPOB5qSVD5r1L0v1HJLHnGkSdQKU5rCnGGYThgAb0W9OkDrYBfTknwRNXFuB35Rt6T6ZzYSm5OKdMXDANhmoH3TMayhgR7DO4UNCuDxcyLlAkunR7sO/NaQ80buPCY0ZOGBrqz7vlO8xF4kGZiaAtmzPh3MA9M1g84nn+rHpMcNAADh716KmSgntmE1kWD96zTqLF+SmAcUBcAw3p9Tsnl1wEosCNK6fOfHo28B7w96D8xPZkZQ4DobDCwH7DT5hz8NIM47xGyZ7wTMpKhliwnzWdAxDmlzWIeT96UkoGYvT7wEeoYAq3FsPSvGNMxr1wDmF0os+HlJgPNPC4HA0hxx4nIGcKToGZ2D2KXW7e2Ic5DN2GybQf/kBScScYcXo8DANgGruORvwzB0N5hvNDzLsbUksl6ZhwNVzP80NV7sZ+o2NOVjzkxzJiSDn+tYVOayTRgbvqAHM16W6kkRjhmEgxcofM/YsN6mhzGMW9PgevGdDZ8FuZ/kRsDTDMG3pIhfZ70KsxTnub2dMD7zRDjzOVQ/yzPYYGrtwgajnG8tpmHAwTSKpjOUYOLIMHQNwANUjk0CjmG1sD4AtslYQMjjzAA/Emsiy3SsmHMO3qU3oeagEyBNpszpzUO56gAVT/WriY08DgUDU+CraUbPYV0umaMIzMwMEnHQ0+G9cRI+80nCu5dElmCaYJn3b0qVbTLUW9jROOgPju/ekQgMcDG3NIgA+aRFWOAGewEbGibK9wvzSKgO0TNnYuJXKRdelnuH81yJwC7PtL/iS+Of+y4IDuQ+Ljd/5pEJ/6Uy56dF9Ej4IMMHw3/YniJk5QfDeu1S1xrwXV4gY2B4et70FmFRqgFzBQydMu9NMjJzxMv3kScP8UsOSSSSnBJJw/wA19rv+xAIQInKCP2kruJjBLx1Jjgxw8Pf3r4L8CLHDytn5Pvooj/npTBSXRM2b8+xMyBvD6kwuEMPGBh2pUkO98LBZTWfqN1JPzDMZ2YMWMeykYKIO6bLH+HUQBkR+1k9qseqMEeEzTbrH+7OgJsGqGKb7DhHpmDpkZm2G83EN/UDOQIuHjYeKGvJALmfzVF0l1k9MbjYqUY6xuANzVH1dFmD1Y8Z+pcz4exawRMKTBsRpXUEbzp0ANx70eOZSMfVAQ8aAhGAN5rJXCBiZQDJszPeaJMGYfeB79gcz96x9t09IfT2G9P6oOeQEANcPmrvqx0y6skmR9lVx6TzLOB+l5z5XoGZ+j81AZM8lMB6UdzM7mZ+xNI1t2ykoGuh4GEhBp6p3fP3q4wogGKM70oFAQ3kBM3DMQ1DM6MB8ESejicNGjP2cOlqBzM0Klw3HN1yM9I/3aP8A5oqw95Eh56mmFNmxD2NinMbACMrmd6I8jiDWYAGjFhkAqAe80rNqJGGLa8v0uEkzGh/lmauMaISMgcwGSfBoOagDFjDh2Y014tm7RDsRhhclDBxmNCAGIwc7r0yQ9OocxmM7A3mfs4LQoOLN3y0ZoNNmm+gK1cy+NBwDKAw/J94HwTHMkYYt6SZ6El7YFOAAtQdC7bjwymRgaeJyh1BkP/mtIghGhx3jM9Qz9/YCz3pmKEOEc+QYsBS9z71215+UkUaMjhme+nOi0Zgc4k5mRyhg0AhGA95n3q7nEcWOzAivCDx7zooeJDyuPjRmg3mG/wCCZKavnLtGLZhsM1PTczYYyULJecMyeJ8L778FxbMAhvAMYTMEWzoputmZnpgf+ajSoEaB03rGYtmXsUFfauZwy7NTTOOzDjhvM7mfsTIcUGsWZunqGriPF+9NYIoahhsuYKtyEWS1lGcbDAnD/rmt637W7HBWxS1XDALXU9tpkm/VAXP1qS80zjnABr1HjDfRdhi6+POgaZpFu/43XFq1yPG0zNitFxGUYcQ1ABX2P6ZeajnJmHph/TBcW4Qah79h/BJ1b6CfJjHshtzDNvgVFDcJ4uzYiR5rSj7woChttGcczKoAt6sz/O4QoSKjdCDeowunqbWVdsxTlZgDANe606D0aBtgZBzC5p87/gXX6rwiGJuSpLTgGAE2pgyJLu8AK/wR51BAZamBGCMOzmarY+NpHA6bFiqu7Vz+q8ATMiyXedm1DLFgEe5hRacOGCY3srcFDHFg7MNkQuAKSptJ3/VYv4AcV2l2Q9On/wBNPlHpSADvNEMfBmfUlCAgAPzFPHEBIyBm6GwDopOs25VeTF+1AkooTZFNtz712x8cwyJxqUktHcD96nyMRJj9UA80GmzfZRG0fCHKynmdEr05gCr5TeEvfvGB507MjZLDssuhqGGxGcMAxsmjoF5Y/mgDH40MbDN6LYz7wWi4+UzmenzAz03gDguxy9HyPet2pOosdGlN60UOfYsonMGxHeAwJw2nO9avMCT91HXYAexZXkskbUgwuDgHzNMqkLOpzQTZtDZ2d/wQ89FZykOTAdo5sMboqenw2swcbzIXd4XUaRhjN3zMWrckNxgB81J9n6wxaD04zjXJMaKBNyb8w4K7KLMlBGB09R4OZo5yWLeLH+cx1QMw9Rk/emYkAabNmbGJs/esfzGtn4uRSQBmBUaCh/NU852A7MOS6HlDvSnYasvv7GhIkxgDTodf1oVyEiNkpAA7ZgAOwfNbmsIaZv1wwGLbOS6BPwJBhem+iAIrQBDONFk68AzsF+xb3nMR96dFvADPnoxhSgdiwrFwPubIHjZXqRpB7APsV816JaoJZTEnFyh1hjogGww96FXHclwECoB0A6LYIsWfF6lkwAAZcAw2Be6G3iPDZCScqGVL8KL0iqBMf7ya8DN2zBht/WqHKA9I8TM4zph/UMFpeP6ywkrWOeANxuH5fBWTbXT2ShvBi57B3Dh7F5M2Xp51eaxQOGHB75qqmY3Gu4c71beDfcFt8zoGNPkPA7G1KH+cBrMcx0aGLyBnCeJ/3gfNbwNMclQDG5tWMFWkNOwlp0jFyXWwDRpc6UoqGR0zPGYdQKnMNiRm7L0CXCAeSWwt/NX0/EyfBgw8sTZ/oVI3FMXKH6ZgjJm4RiENQOSRAAc1ZeSN3fSlEwoBhv505omQqh8PEvH7BLauxDRvZv8AmuxMAMf5+xcWxMdhhsTQjES+iNvGqe40QncQ2fyTN3814ZL5pH/wXZuOZvnTsTWxeMxAbKe7SGxTmZf4L0Obj+lDoPNVpFY9y++J+JnYlzL+SzXwWanD/NNSSQf4bvFdtA9O+39KnCcZqJem/sBRGo7r/gZj+8Q5miZDjXxFsDqpLcMzbFz7RAPmpOLjBIyoCfAUso+buSIBDTba2ACKnIfCaCBovD4i/f8AwR/0/lIeZxZ4qeyLYe8AWWeJkX8SUmHMehSdZgvsNEhPy8D7rzjkbxPUC9gP4rRIM0M99K5MV2rkmOGz3oWyzp5jpyNMpSSyG/5ghuFMehTANsyAL71vWPUJOJfKB1PGePZ4tHvutuzhQ5nScyfAPzckwAgp2AsZy0UymHMYC8Y92zsX3D9QTMP4mDXrNnzA1vWGKlzGK87kBA6gd991dxyAMh5Zox0Qc3mhmVLObk3pRhpmZ3Onak4HlnAEDLeG81ovLcZHVEbNuQ4DRk3AigA095gjnCgewzMnApsD4LzNBN4fAHmj4GvTPRMoCw4GNnHjCt/YnTO0vwNsaAeYCTIAbhegH2KNkJQF1IyZBqew0hA2t4nrmYKHKA2poAWw/wDsW+s3B09Ysc42RRzzJnoUCoADnNGfTMcMj1xAC5GzH9U795rN23bQ4wNB7LmfetR6JlGfVk8zDTBphIzascyjjBlZkkuZhUKdijQZ8x+OEBqN6xnf5mCQxTn4x44YXMDpdT4sV5rqWNPOrBtN1P5rFn8sCqP6uQjRorOo8FNfZwR4LXmJGtKAXIzQbA+aG+nckDWLn5UIwn5g6gZotkCcqOEZoNBkGwI3v/gsKXbIZGS/i/LAzsIKMbNgK7g6LGDZhtSaGAeuYe9CuUOS7i40Zo9Nkz2GrVuLGCHG37++5815q1A5xco9RkB9Q6bN/NXbhAUgANkg96EsXNhw2zNqzknjT2GrLG5STK8y9Q7gdVgSLYrAA3JMz1DAOB9iG8s6yEc7e9TymmxDOx6ZmG8NNDEhgJXhcnic38PYvK+FEmFIDG48/Khp+Y7/AJoGlZTy8w4zRkcm+87ok6klAciHDihsALmYfBUjeGZdkeZELme41Lr0djhWDMeIC35mUeoZnVFUGKZ5EDP/AHYO8FT/AHWANnbsO9FZYN8yypxndkY0vDo6x8rjJSglQwjNAe89iIcTi4wYPWIBcMFAlQo0LRMA1AAFP6dkHKaNkQJsL7A96r5Si797+Q9kMDJy+YBmLsAD3gmdRdMvRceAC9vAN9FpbcUMbIOS+YgZ9ihuQvvls3r6gd4KrMIPy3/uFei8GEjHXdPf+hbMzjghdLPSXT1NmxVWHxwRZEaMwGmAfnoz6gaA+m/LNHQO+iJ+EPWvdjLmGjZSOZnveM0z7rjBICAAbwBFrMUIcMJN9gKHiQOVMOfQT3rFYXTV4UJQo2GiGboDc7gCFcW1q5QzDgfNFX1GMyykDQDYAb6KHhccY4fWECNQUvneFbmDjQ2wAQC5qqeaB3DmYhQzDsSyhm/1BouhsBEONjhp6JgNKJMztd6RAMj5KNqAy7VzfVavi45hj4xhWgBb9ayidhAi9aGYAWi6dwP2LYMeQfs2FQK7Xf70+Zw5vWkCO08WYkgYaYGfNIYs/FzTNqujTYiRyEDscJ7RlrAuLjpvx6SLNhTnS6J9HPAcXqgGpEmHNDUQlnmo2oZtGLmrwBFU7BxiyBnHMTMDsfzQr1FjTPpOT5fZMDcwALek1/uMizWEeNw3jZ9YPy6KhjnlYWYjSbk+AHvD4Ikh9UZWK2EPLMjfhcwUmZkgajmbDLThnspf/NAr4XBEzlMGZxT0JlN4KqcdBqkCV6ckO9Dbmch4Zo3jsxPPcfsQ9H65xXULk+BKAmJIHsNDC46ixcObDAxsw8ezWBCUojjxAjSo2uDXN4OaMGyA+nzZdki4HO9+CgZLyzWLB4DBsw7w4GgigxB616eiyDhtTxY7DA+9Cs7L4qflDB1kaAdgMO9D3UWGxuUvPh18yB2MA71ieQdkwurANqe7BAD/AN2MNislL19G8SMXbIBJhSdB4exVWSyk+BkP9pQBlwz57Lrji88DuHo6enJNjYYLN8x1B1JFceB02n4x8FuElDbS6M6hM43kximYb9lFQzvpvGDHvfcM8m3jDYCjdO6ObwZyXw0JIHQDAFPkZufg6AQE/GDmaqlJYPi4brnpW5kb8oD50O4IPyHVf+1DOQBA8Gxy4L0Vi+qmZkcGQMXLhwNQMx0XhM3HM5EYQePmYAinjBJXUGKm4vWB4WDBCsrqGZFkABmNOw/gjDqL6QSY7ck8NJFwOQBdY5moebx2LAJkYmzZ23ovHsDn7+gT2w1a3DnsVPKHFO5AJO1sO9AceZVu4Hv9i7NzTMPVAqanMENjYTgHc2gGnBcRGG64YbWwQ2QGDd2j2JOTTBugGGzms1I0mSI8YeFTt30VbIisjwNQ3JTzraZqmLZ2NZM0eUUCcABPmmOQDDhwUYpgDHpTeChFKkF4mOoQW57/AOKWYsyleVhmAgJn2Gqdx03XblzXbVq2AEoZfxQCLn4phfyXT+mmpVBzSSSWKCXIICcAQUrzBsQPLB381AaHxJz9P704j1ZC3NBfR5TOOxYGP+8nuVK46b+QMz2XPelJAxk/Ye+oKOsVQF3UUXDxcRACCYuSaeohNlonZAh4JlvHx+2371ZYzxIZJ/YifawJmS0o5s02U3qimYx4bSWm/RL/AAVoUinM9gKI/nXPAvBtkBoKfUwXNWpLyRjmAmVO9Q1Kdkm74n48PAu0f4KKkUYktu1bIC4EpszJnMoBNiAgFQ8A8FUpLegI8PKAp4RneBr0z9PYvmsXJZaP8oLryS2RtSAMC3L0r9G+pYw5B5madDNuqu8T3vFOb5c3+P1adDdu3o9gHUzVrlMWbuLMxArgFwUaPDD/AMwAAAvGM7B7DW0yGmXceAaIUD4L6CvG3FuHPe4ti2LftjwjEBAYHv8AgtOwJPNZiSAB/Quf6EE5bFnFyhvNBRkzs+AI8wMyN5h42quGbFDXD68Lh3eXfY/6LngMOYABe52O/eiTFxfvzKyQoTZtAYAHwQl0qOlHn0DTM+C1HoPFyZXWkkDMW9lzUOFs1g8QOF0+zGis+ib4AaOckZsY+AEUNO4b0wsI811IbNPwwe/3qTOkSWnDZENSm0DMOCKldNbDbxyZEwAdCgcUZx8cBY9mS76nlAqHzQTOhTzkBJN4g0t1A71qMEwdxjIH6eqACCQuVUdo3ZBvRw0waC57EVdMtUmPHTYe6ijRYXkI8x65GAHwPvU+DNBiQ9JGzgGG8/YiqY+A31A7JldQMxotgAz3/AF2mQJLrYBF9OgUM781dtugcjzhgLbN9lA5qey08cc5JmLjN9lwS9bgyaCo4YBxZnKt8FJhwmYsMDpqGe0EWjCA44GZ7PYhtx3V6kBkLaIGl5dTlWIVWSYOPSgc+afiYAHMAw4czVlmqG4AFZsOxRsW1JamXMybjGCJ5e6+aXeQA3cWez9CXRseS1kPV2BdTJTX4cDA9QD5qygiHnGa7FXPpZFV6LvOQvPzAAToC7YtoIc0IweoFFcaRtR/Mn6h9iqoJPSsxv5ntBMqohJM7SYsg5HWBstbADmjCdQGzAj2ACp8Xiwi9UBJkbzNScpIA+oNG+ww3gjYzu2bzsyEqR92tBQAcV2JBA9FoNMDb2frQT1I0eJ6tjSWg9Ez/sSlZQ5WcjGZkAU/zUPWnSngmZi7scPNeoYH2K1wboBgzCmzgqdwD85e+oFLndXeNaCV02YNHR5Tz7n/ABAY6kxZtSGZjQbDPfRdsWQNZAI0oOfBFrkU3elwA95gak/dcZ1uMYBvDmq5lDXVG/Z5nIxzAQv7FDxYvYtyTGmnqAB7EVQQPHdQAYHqRjUzqDp+HM8DkgZN3C5mBrFfaGuuzChsnH1mj2GFgAFxbCMHhovhpn2Kni5R7HOBDIyNnhc0pg36gCTrFQ9oUS6pjQVzkN5rKa0UKH/3qBOaCb0+bwBR4AqYInlSjj5Dy0q1DPYZgqp4wHKHGEwADC2z3rxPVMQnYaNlI7wCGo8Hw3oMykWNFw5s3JieC3J5ozyBmJjEeA/ZzQH1NFjO4+TMGMD7zXMw71jZdPOr0057c/FSgpkv6BmHNCoxzxdJIs6hmdX6Iz6idOV0+zm4cYXJ8eUAGkWicg3opjrOgBORj/8AgmT7mK2O7DPHnGamXmSA4X4KtzDUlroPyAPE2ZnYDvwVVHxcMvqQE+E86wAfngZq1y00Goc+BIeFt4N4Hfeq8kUEsXAhxcocbJSSBl0AIHgPgaEsxiYYSJIZL8WyZ0CSCniZlIBl09QDPYYJZwP/AEm8bR3MN4AaZKTqy4YEnF9USZ7U/UjNMU0briXUMOY2fmgFsD4KknYvNypBz2jLyxuVMDNBkrzMeZJgOskAHwNUIaapjcyGDmgEI7xndxgBozZymNzOPvIrvClF5RcymSx0cw0SOh7DRt0z1hAm48I0o/KTAXsJ2qNw3sXlAnxfUAD4fBHmN6ojZKOYEegYdiAIORki2ASg14Z8DU+RiwdjhJhHpvH2AngfypQHHMxPfTms6HFszW3gmgL973AwXH77mMSAgSgJz3mCeOUNrIXaMTD+pdYyzrDK+rPpkAx3pmL2U3UBYd4uSsc49GdA2z9hr2FI6gjOtvGfsPUBebOoIwT8o88QFzOhgsVNx8nzWweM28MwM9/YnjKMIdxPU96jPQHmnT2XAFHEjbuH27C5pGrMyumyB1gDdq2BqGWs65sDUZVd4Olp0Lx2KQzMcaboNUaeZdhADkUpvT9IGnKUFRxkhqGZs/aaf5wNQDMLrzUGPjzWwzH+CjUryUkpgm59psjT2KSL8Dy+4CujUBXEJ/ZTtTqdhbDUwpUYG9jO9cnJMcqnp7/BGoCMTZ/ZayjK7bmQ/APsOMKilKjlxjCCxQQBKviuzNKGRqP4fv8AFTmfYYbETIK+rHMFE8PH7fD/AKqeLrLUg/GmoFNihuGGvYR+xFSz/R1GK9pgZBph71NGS1Faq14XL/iq9x83fHca5o1EtOrjpumZkXJRl0XNYqgSSSlxYr0qSDLQXM0Bx8fHxUhqJJcau2yZD/x8BRpH6aCG2y9NC5mfA1cSJUaLpsgHDmAK7l4139Ib8mJ+WZEw805vAgqrvp/JBi85qEZNh70auDAmtmbsbTCmxDDmBAnXjCwABq6fDvl7yx/k879abZ0b9SAi9UQ40w9eMBgAGa9aTsleFG8mAHGeADNfnRHxwMRwkjJLbwD2L2T9L+oQzn0/Bl09STH2GBrt+NV4w4fkzG9wM3HWZEgAPv7FT6r2DzEk4oDo0vQ0WyMaB5WMY8DXaRhglNyQkdnBM7zuHnCsJnQuZjZSPJ5A9ffdavj8pMgZwPJAQGHMwXm/Gv8A3DmDkhZv1N9O9bZgcueUx/nIp6gHzXzHWcPoOVbeh8XlDzMdkxr5kNhndT5kdnG4ozkeu8fALrLsHKeahmcc9A77wRz1RFeldJxp7TxMGAABmCit0ppDhgcqO8Er0wR4zFAcfDC/ClAQNHMGsPDAd5mH+tGfmjixwCUBAZgAgsUfra1ygmLYRmjHfzUwo4Rcezx3h66pPLmWQCS7J07hsuantmcjHmZGJmGyiXSv+CS3FAG4Em/4Z06gCIcgdGwgNV+dFW4Vpl/Ihqhw307AVlHaAuoDN2xsgewwS3k07OCAUjGGmABb9apMXhDkdRyZLtmwDcCsstIOLIOTQqU4K1x8h6RiwMPTA0K+VBjLQrusmPqUVJnnTi9NgDR+sfBHkphkL0DgagM40Mi5+IAdEA2JmT+VI3TsKTK6TZOVzUlxo4/UDIDagIzbistdP+kAt07ENzAB1wDY596PgV7jCc0Z9JgbB6gd5qtw7WlkI0kzvQ1Mhz2Q6bOMZ6YUVlhYUZ3BhJvqHdbqdnz6QuJw/iIZgenTesxzWZ/9eUvcACh0RhFmm71DJZkHsDgs36kisw+qPPu7AOhpdViHnCv9h5lsWzkujweMB2BsosNIZJ5gGS2BH4LacXkQm4swvcKbFm7kUw6sMCC4GexSdfh0uVYtPcaP7nAw9S4b1JxcoIWOuddh70yK0871eEZ302R20T81iwDMAy0dAM96xNF11jA8Fr7y6L8zDPfe2xQMS6ZOnGdDeC7dHuhFjnDM9QOJqy8kEfqAz/LAzVenEqvdxkNAGLP3hvBWWPN6V0/R3mALjmgrDZCnMFGw5m1HDVPeeyikqvcKTIR9WO9pGNwUOOZuw7hzA9nwUyRFMOpZJgZOAZ/4KHFkeSyjzN7+wF4EyU15yEBmHrNB7FnrxmGU1qE4bR71oTJVceMjufsQHKOMeYev+de9PegtGzwBIhhMjhqGYc/YsuyTrwdJyTM9CSfOnetayxM/dbJtVAA3GCyvqYAlMTGQAQCQFw+Bggtg9DKQb0ILsncXw+azfMOni8oEloyOZvA6cFpAzTxrkwDZ05JnU7rOutnQgdPnJaZ1JInQ/erOb2/2wZhc3P8A/NCNc/RMz112zAPSupHjmnS57D+Cz0ZkwuoIZ46zZme9aFnIck8PipJ2B69T/WrqlBVYVsO4SDAT1AA9ifknTOOf9TZWikk15XF0MPxJ8zVPKIAbC56hn81lLVbY51l1DPgRjxUIKGe+6jdEnJ6hw5xp4aml3mHBEkzGwMl1A8c0+Hea7YfI4rp/HyWYoCZmadMl07ZbpeA7hzjEANnSwGvNkjFvRerDqdDaO3616ByWck5KgRwK58KAhL7pOZkDjZINAzbpcwpvW8k7WWJ6yjDD8tKChgFE9nrAAyD0lqTqU3gB96hzuiJMXHgDoEDJn6hoSyXTgDlAjA8LYXqB32GtstRj9a43JSACZGEJLp8wUyc/igx5nHkjcOy+9YU505ko+QMBk+UeByoGZ7DTIMDLzesY0bIzBYO5iBnwNLprDQpUgAjnJvqB+tB7nUOKJswNmh+9cc9hsrFyjMN2SLerwoexUUfo3KyMqcYy0z7DPvQ8mcOvmsa65czFu/zVDkGIZN60U96KpHQcliMBuyaPGdKfNQ8h0f1DhrnPxT7AH3mFASc7MmogA1L/APvimK9kCAt0pdVDjdD2/wAEipwe4pJJJAJJJJAJJJJAJJJJASBcEOKY46RmuScX8kzQNTh/mmpI0CSSSSwS++Hh4/yT10baM3NqZE3XyCbaN1wAEFtnQ/SgeYB6UyVzWUwfAWsgH2c7r0r03mWRx8YCAbgHYu/4fjRPvbj+Z16fMofX2LBrFwzihsDmayUopv5c6hReqGQh5SO9GdAXAMD5oDx/TkDCZTKycoAuADh0XVzEOVszpzpXDxuiAmZI/wASZ7ANCWakQ4eQOBHZFxkzuqrLdRnImGzHPTZDaCEinvHkLuhc0uqbmVwLAHvNkgAzpwWkfS3L/c31ICAfqRpB96oelc9GmZAIGRjCbJ7Ft+P+nmElZSNPxsnQkhvALpnCd36EdaiPR6WkYaM7j4cwToYHbYhLJSvK5QwINh7USdJz9Vw8VKPUMA5n+hUMyg9WTPNM6bMc7XNdKptLNf6g/IZfGxYZnkgHZwp3on6Hz0aU2AQw8qF70vzWD9UdQw8p1wYRa6LR8Frv0tw33z1YbLRiwy0xc6d6+c8n3vEO3424h6EhymWm3pJyRAz7Fos6Ubv0vjG0fMLU96wTMCGLyEk4oE/TmC07pnLHmfpe8fAw4AfvXJqcW7k0KsWOq3GemHTuAEf48o03IecmbwDYF+xZ1FM/thhS594exGZUjtxo16GfNS1KuahAzmZhtZkAaMdh7ABEOJE3Y4UMt+5ZjOaAspJN0C2nzNFWNyQRZEbQMudDWKX/AMB/iyktZTeBUPaexGEVoAkGHv8A8ENx3XnZd2vTMESaRjHB4z303olKh5Zo3ZjMamoBnUD96MI+LCBhwA+ZhwVVBMHZEYxATp3n71fNm9M6khxjPYB70vLWrCsqLVuhh/rTMfIBjIAzTYirqyKEBujR7+z5qt6Vwf3lIu6BXvZMPml9Hxxlj3nneB/lgsxEni64OG1wADW5ZRoI8MIwHvAFmmPxel1I88ewzuaK9z5oPFHktNgyZ6YGjzEuhF6TAPY4hvOOg1IZNo9RWTzoQukwC+8wuiaM0rXJRx+qAAw/N33UDqiKGZjhDA6GGwzVa5KP7vOSHMO9T45hFw5zJR6bx7w/Qkdai25p2ggGN8I0No7nSiZIihjepAkv8z/LBRoYeayvnL8N4K+zDXnZECT2BzU9e59VgpUUHdGe0Gn3mqd4zmZAHtwAHvWisxwLp8wKtDQ9MYCB0vJMw1D7EfBE1u0PAkHmPMtHvvvWkFFB2OckA1DAOCxboVqY7IkvGZAyb/A1vEcQYwYGRi2BBSnejZFV7gnqJ/Shxnjre9FAjj+MAxs4FLJ+Qa851QYGd2Q4AuLzpxeqI0YgJsKUNJqjHaQIHR4OZhSip4cIHcgbx28yCuKemZu7wa4ACofMPBkDkiGnG4ImiL/bMyDR/cb0lr0zP/BZ05FMpBz9YbtBv3rReoP9m9Pmdy4XWOQ5rxyJLMrg6GwAW9iaXF/vHp7ae/eBrIupMocWYEB2oHT03vYi3HhJhecATIzvsA+xZX1wJ5GYybp6BhvMA963DahzQRiyHn3TFy4VMP8A5rLuvspDamHqs6jLobPmjmK753IBDMLgAUM1mnXUeBlJhg0Y3iHWl10uUl0zRto4vUkB6EH4YzBbHltF2GDLtWwChAZ9iy7HmYxzZD+luurvNZSTlOm2fLhvAKGAArsud1D3VnVsBiQbLR8Aps71nUjKZjKOAECA6fBEmJweEyXVBxpsmkxoLGBmrjLNT+kuqIE/FgL+Klt02b0ZSA+H08B9QRofUEksUcsNnzNXGU6XgdKdN/esIBzIA+APme+ge9WU42et+gwOR+EyuPfq2YJnTMWTFj5WNMPXhuh377qvLFV6GZyb0xM6LnvYQxYnxAAgAApdAcOUz1b0/PjSjGDkmaGB35okHFwxyEx4DBgHQpRY/msp+z3WBgwYGZhzBLojbRXuo554PMYeZV+jACFOxADP4jouYEz03mjA2DVlj8zAlYs5LpjrHzVl5eNlMWbMUxc2JbTPclnvOdJgB7JLR7DvzVaORDI4uHQKT2jtcO9ceosHPgSDMw0wDs96HoPnGpHmY4aZgsZN/gP8lIORDhnI3yY523p8rJSZUOBMa9DS502IV1Z5OA9Ks4HPgrtubDdwbwXofsNGXhZTKHkW4wFL0KPgRnf2LYOovq+fUH0rDCZQI2VMAAWZIGAGC89t4GfkpFwMQjX5mqedCk4vKmDb16cDA0v8txb3K+mbcp5AWRMHQAv0KJIwTRR7wjuYcwNU7mRlPTGXXz1DAKW+KX3m+f2hwsk6izJ9CcajbwdAmXh7w4KscE2nKGiqK0cyOd/UAFEc6fmG4ZtAVPml1PoNwG0lJeaNh0wdbID+ajLGWzi/knLoLVwUdFRkEkkklh9/iS+/v8PH9y6EJiVUQ4DCHl5Z+BnoRg5mqJ53V/2Yqv6T/wCQ+DTrnjsAiUgYckvHgXiS0R5iBjbxotXAD8w1WuGyG++ma6M+NE/dpK7/AOoZj4afKpVnYferKT0rk4mP8y6GxaV0y7AleAA7Vs1cZoLxzjNGRsp3+NBFeTcWwWNAfkO0EC+1HGN6cM4dw33VwzFCK5QWR3qTSZ5cwY9ME/hyiCOve7UmP6ZjPzz81J0KGtCgwsVi4YVnmZghJuHJNu5+mfvUkcQ8/jzs8TZ/rVeYhDVXf21TF5SMLYSWjJ+nOiEuuspJdhhGICYMz9+8wUDHzPuvFgyIXMD3q+mQg6t6kjPEemAAF6J816MsxwuGk5jIEyHjSm+5q4ldKzGobxtALh8TWnDHw+EjnpBpn7z70JSOoYZSNh6YXS+tQ1O2U0kwpFzAgeaNHmJ+pubxUgAaMaB7+akOQoecyB0AbgG8w71VvdDAUMzGTvPgkTNx7wZ6X9tZ6L+r+Sx31UgZvMmL+KM6vgCLfqh9UAldcSWcGZHjZbABdeZnOmsrAbCMAeaAz2U969CReiAn/RsAdZFvKgFgPvTPy3jLeYi2M4+eH3o8ciSVw7F7k/8ADzFgSul5+YCfrzwClNTgC8B5hqTFyBs00JIHvVl0r9Qc30pmDZxckmGZe18L7FDVYtXOP4v0sz2aw8C5gYypJ9gH/wB6n9L9Qg7ogcYIgHvNkHOHzXh7p/q2TKfksynhfeM7hc+C2zA9RvQ32XpGkYG3UzA1D197Vcqez8eYavmS3snwMEWuGbseMdBcMOZrH+l88zKxYADwuAfZfgtOgytKPsPXjHwp2KWpXSreov8AczC43M1ZYuKy/HjVsABzVO80E/OADtgADCiM8XohIMyrSP7EipdKa9BzBM3cWAbGKHvMEbN0+7wZlbwNvYYIYxLEbIxwMHtMD3ItyDoRYYaR3AAqCCSgsMhkABrYH696JMS0AZySZBsDgaEmbk2ExrYfeBq+i5kHXAAmdA+KPgGdRRzldURgfs5GRbj/AC0ByNWjd9qqnmjm+IGZi5Q12IQ+8GbmVARoOPVDpsdQMm0Gw1GkQrOhME6Bp70/qy7uPjPD6h32Ls26Z9B7udEuqs2fRlbzrLuYe1z2Aa7Zh3zUcAE6M0VUTQFmHgKzYG4p+cA4rcZ5oCcYCgmlvduIiyeDp2AqfLOvSm4zI8A2U94Kfa7gRh5mFgU9mKD/AIAYBqGGw/gpzpTIcUGunzpW9K0ur6oH0mzcN4Iejh/tAzK1AVlHmhMxckAtcD2L3BlUJ2XTLFgH5ah5oQkYsGQDUA+aUN2mP2hsAOZqBIKviyYGVDNFlp/TMUItGTre9qIny0q+QbZMxBkPy1DxcUGmznkG8OCqnBOfkHjPYal1bE/ezI4xjzjz3NWuShhI0ZLQDQw5qqedCLDMI4bw/wA1dxz81gwMt5+xMmdt0G3gBpznzCtFWzIf+zwjAemd7gfv+CuyDzDh1AQp71AclA/ICMAcDua3gnYb6sdZa6LZ+8T077NixAjAs55kTdbjNBQDNaR9UMpGj4+kjgHBZRByR5Hp8wdAWAvcA+CMHO0WRJOZMedDTDs/QsW6gmXzmV36gAB7/YtdzXUARcMcaKA8KGfevOvVGSB2G8cWrYAfrrcPZoN4PMhHmHY9QzA96xnzsl3q2ebpk5czCi0KOB6ckxDTjOhsMEN4NiBKkTJJmLZxH6GZ966XL0LqknH9OZIY9x/JM99DT4+b8nnJONmwNM2uB+9B8zqif091RlWQmXjHub3qfH66xWexwBNAQmUpfgar251JPU2LgSshG6nxtmDMKPh81MwYSZ/SYRnQ1AA9lzvRXzkWBM+mcmM16lAuCqun57MLBnQKHTetzW0lUfFxcDHYue9cQePcYB71WwSN3BmAGLnqKHlp7I4eTJdmCBkZ0C6zrKdRgHS9MXPFyYHYBreniyzzsCK2YOyRY2dhrzlnjjO5SSYSSfoew0s5PnysiZypJa1+AGobcKTKhgDUYnzM+wEnV29zhSEbwt0EybBaL9O58kepwAQJ9nZcLrUcT0Hjcp9O2dWNoTKbzMFP6d6APA5w5gvCYBsp71uaeCHLYONkcXQwFwzDZcEGN9Lw4WzRE/fsWo6rIuBqmIGfYqTICz5czPvW9MYBhYuBKbMHQEAAOwFhvVmL+5sqbIbAM7ga9CCUYHwMT1A71mn1Ihg7jAmtb/UqaxXu2yIctPax5xmpJNs+y6riM3d5kRr4LV3E+lL1UnuYj1L/APvilXxrb+Sdy8V2FoxcoSxl7/cRdOZhnGyHQkBsPw5ojb6mZKRS4thf2LOHBq5tTPAP37VuauLFTDbPHp/G9VQCcYktMSQDmCy/M4SfhMibMpvZfYYeNgNV7UyTH/e1INsvga1noqZDzGDn4zqEfMBzAz5gmZ3Zc+jJRdZJsAL01HNvx8HTpvRH1F069iMgfl7PwOQGhgTMe77Emv8AWj3JJTmzju+H2O+mfvUdwPAHCrvD7dpJeQNchCtIMzZ0w7ATIcnxjeBgHhS3YjDJSoDsc6mLhoKPxb8HjovpHD1eF02ISG9a4/NVsoA1aBa6jNum0dL7CU9wLePwXmdhDhuvRcgBtHQ0eR5RlizedO6G4OJ804Ad/vUPIPycW4cYjJwLr0TOxI3lIzskAIxM1fC6DTYGZiGxZG04ZSwMOfJWJSpLtLmTmxZmxlqLk+B913uLh+xCv38bThgAbP8A8iG6PE4G/YmPX8xQuC9qi8rUp8n7DMTKho86KyQR8RMkynt4Bsos9jgAtgH/AHoz6dxZzMe8DRi3v3p00RanzGZkypB65k4F7ghhu5yDIwIwJaL1BhocBtkBMjk0uaEiC7lACiM7MnCfg8oeLckgLIP6vv7Ef4HzPUOZCHQgD3qZ0v8ATk5+LjT5TwsMu7w+aKupsziujcWAYuMPnADmHvTPeIHpd+qqmEEOf5YTHWjuUCnetp6bmG70mck2dR4A4LwtL6qyRdQHPN4nDM7mC33oX6w41rB+Wy5iwfFY/LH8xfC6jSy+o3S7M+Q3mIYCwdPXAF5jcivNZw2RsFD4L1dK6r6eyLgaU8Tu3/zFkXVGGZLKBPgGLgXsdFJ1qLv0P5TcfaqguhHyAPNXP3gtyxZU6cDSDzT0g9gexYzgxeBs5JgJ02rY+i5t3DB0NM6HTYpMnz9tXw+UPDQ2XnQLWPYdDXoHovrIBoBgTjJhwM9685RYWVdb846AvgPAA5ozx45XCScVlZQfhjOpgHZ+tIqbu3SmoegZmZei9WMyRCkB0KHQOBo26fkAcwwA9cHQWek6DuLCSNX2T3GifpMAazDMkT2exS1KvTcsWQBh/LA9pmFBMAR5UBjs24AGy/egAYoSowHFMgePvD3rWsLizf6TAMj68kO8FgaUJBzBoybumC1JiyAr6lT37OxWsjESYoG8Bj5YOzvVO3KM5FD9RFDQkI3ovjGktPeifO6shlWkBq/4KkIQLHnv3hvouxCYQwktHp/rU5i7kSozrYRri4HsPsT9UAx4RgD4mhsY+q4bxmV/h70nJ8mPHA6E4yHNYmjtc1JlMSY5i7QbOWxTMgwDuPZA+GnvUwczGfcNkg0DP3rs5D1cWZmep7KLymQTHYAco8ZHvAKACtelQAnJ4O9596kji7SLme9T4sIIrjzzVgPYsQ1sPZIHmuoDjMemB967Q2jHxChiZnzorKQ1fJnJLnpp8WKDVAA963Ly1lIDyvT5hfmC4ymjdx8MwDUoakvAD7YMnvMOauI7DI4MwMxA/n2IptAIzPDnv4gdAXF4whYdl78wzDeCTwG03sPYh6VKM7g6eoYcAS3srWZNB3HsgAbz71Jwrr0Vzyzv5NOfehgslpOBcxcD/sU+PkowTLma9mRVL6UcYXNYwKh86KBKaAJjLzQaYGCTmUCVHo16gHsbVO9lDJsIYmLYcDM/eiyLYJ9UnWZTZyXTJzyh7/Ysci9Uf7LA7iBmdAD4LRfqIATMhJgT3iA3b0AP+9ee8WJtdWHipQFfQMW7hz9hrw+fSF9kMpJfzByebOnUwA+CA5TEPJR58mK8WtHMBfC9wMFcMtHjsw9Gfe1wpv8A0IPbmAPUGVgY0NQDCwB7EyWNozeSjY3ovKxnauPA/YA9gLJXnXo/3qEX0wmncPgCLfK0kSZLpl5k3N4HwQ3lHTNwAaDUBraZguhJFs9yUVmG2EmQfm5I7d5oDjtZXJdUB5BnZfgC1TKYaS7h9YGScC6MOienwxcc58xkWwMLhdOmdpKo9uRM6c6HM8kY3dDYBmhidnGQ6HektGPmTA9MANBP1U6memZA2Yp3ZA9lOxYa5lMkMinmSp3gaK9CfdMyXUOblZA2SmO6Ooey6gfd2Vj0kjYAM+fYn4nFzMj1QB0JwAOxr1j0/wBLwMph2YcqMLgLcNPM3T7UCf1ZTKGRgZ8zXorGl0rhoYAwDTh9lwVxnPo3ivLgeN9B5Bkj6dz2JFCM3Kflr3AXeQz0k/A/KmIB8AUCPlJjsgAdeLeqcYE/F5CkoCfAFZR58PzH+7E2YAtzJeT5wvC7dqSRn7FA81JdhmyRlf5qe3IZLItmVgA1GnOxhuDHpmfNFBQ0ejyN5lvUCY153HvRnd9+xXYhqx7lwSbjhpmf5iJ9GLef5EByH1B5N/0AvUDNW+Q6f+6XGTfq/GMLXA0YdRNQJnicZ2oPAfNU7cJ5/H+Qdk64AHp3NLt7uABMGOOQPy3j6PYodqubFZToZxcgcYAM/AD2HRScXhnpUwDdCjKMnIbkczga3+CiNEHg6F+C0eRgWfus/Ln2cFmzzRtTHALmJJFTbE+ywkRYxN3jvDf2L7HmTMc4OkenbvVPbf8AaKkuyTebADHw8KImjMjLG56TKkAzKDXjFsP9Cq+ocM1CleEiEepGPd9nsUHEZH7uyGoQXAuablJ/msgfiyfol2IqosSpV0XNJJbGpGZuGHYkLQE5uDYnkINOXHvUki/Dr6Bx8oekAO7VcY0AdmxmXeF1Ttn6e7mrXFnTMRjvsA0SKapoMxYYA0At7Lgs66khm62cmm8EVZbKPFQGAudEJTyyvkDN0CAD53BOsjWAZHD8RQDJTxa9QAMy5qfiYASsier6YURJFxcNpx43TuAApI/cVVShFr1AMTuAKZiWIBZQwnmVFJcdgFizZiskD1/YqfSkmAGLJGfsoqJ90tUOR6XOVMB6EBuM8wuruGf7PY8/NMkBmewLozxNA6XxtgJszDegbrgTGQyAH8lVn0T/AHakzWRPKOBb0w7AU/A9Lz8pIAGIxHc95nsBDEV2+ch39MLhe69Mxc3isXj2TaeFvYGwEZMqrEIiHT307jRnz3tBvXl3rTMhmco8YenRHnVXVZ5S4QjJwP1rJZgG7IuYDcvYsdat5IPkMB4N+9Ushg2nP1LRHMaYN3oO9UMyGHcC5XWdutyrATafdZdu04QfpJGXTfVb2EyhvSgLIxjCpgbiGSi1PgSkNtBp7wKnwSJm4P1FNjwucxsrOeZixvKRj5s6i2npvM42A5eUyLlz2fAF5LgunFmAbRl+heiumcNlc99O5/U+NjebjY/Y+yB76e9Pn3hDWHu3D9OQw+ncPqTFyWslrABHTsUCdFCVi5MN0NNk+/2LGfoH1rPi5ST09KAn8a6F2w56JrfnoZymzkkGmH/YqqxgTWFD06Z46OcCRJIwPYB+xaF07lIASPLNPesB+uHzWXSszhIuQ0RMsk8Z1M2eAInxrUBrOMzGruGdOHNc6vtdNPV2HmGMdl5gybeClz96PMfmckEwDak6Yf1AusKwfUsaK5DAgJ9l06gfs/Wtjjsa7YPRzuBhbZ3qWj9DDKdRm7hzjXEDMN5oPjmZyAoZUM99OCmFjvNNgDvZ/go0gwhNmEcxcMPYajoxduTQajmF9gBYzTBmTJDAPO1cjdlEHkZypAMyAJj2XPmjaLko0fFhDfATMA5gl6Cyiyjn7I/pmCgTi0nDAw0z778FdwWo3l/MwDEzPnTmmTBA2zORWnspvQYEqw5WP3GLhhs2c0+CUzESDDzJHGPsPsXGVDjR6HCM2DPmdOCrRKYTZsyg1794LGzprbQmZlG7lWlPUoF1JFo38WElgwcA+fwQlj5WlHpfYG2hokw82MUM4wHpgZ9/YmTgWG3pFMoEB0xCTfZfga7OOyYbhmZjcD3/AKFT9aYv/akOewenJaMD/WCmFK+8o8kJAaZmFwP5ryRC1J16VH1oskTC/wDoU+Lkg1NF86GewDBAeDfehuSYzuy/eauMkQNSIbzQaZ+++xe1TSyzDsqLcwk6lOwPYqduVGn4cJ8Xhepgpko/NYuSf5lwPUug/p1o4bZwwMnAN+5n2JRjtBlX6on4p0NgBdsz5pNyHo/UmNAQFsDPefZRSXot+pHpLQEcl0KGajZCK8/kIANWbBrmaGap2yT70PIMzAP8Mb/AOYLjmpTINszCMjAzC4e8PepmWhhIxcZm5NnHoR3DmhvOZGM1DZC4gzelz7EEsu+o0WBN6gxUyheZj7wMO8Fi3VEqYXWjMxgBCgVYMOauPqF11GxfXgQ3TI2QDfTZsWOZb6kxneqGYcWMUsJAbHg3gCGtpM4wizHpMp4zORzA/es9ZngMd6ZfUk65hs9ifnnZMqObMqSIN8woe+izrNZ56Lj40aAFDDvAOasmSdCGUGVPIUoTYGey6tcfjr5CjvqGfNB7PWWblSIAT60CgHs5rTidAI/mbiAGHp0V0ynqlDKMIbhsuncNTYF0N5rPSXcOcZrYz7wNSZAXvJM9TegbKP3kHGi+oZ7P70+U7JeogAcgdzuazfIAZSNh7FrXVWEnxY4SZQUA1mjJshlA80GoBuVSK+zBh9P2MkHUNwAjh03ma9IN9R43AwwORJFswD3rFsl1Hjcd0mzAx1WzMN5gg8WsllIZySMn2QD9a3PoHt7A9QQM5j2ZkWSL4HzU/KNA04B32H7F4kwPV+S6UxfloRkYOn/oWxufVAHfp9G1T1MkAbABUfbFU1SVi4cqPf8ALeVaPTkDzAWZFwz+CxbH/VWf58AkRtcLr0zhTDJYOHP4XADXg+wNM6Shk4ANM0M3EK5zoWY1HM4t2/hprbJ0X/aFwt8DU+Uf4MAdAXApvNDzLyi9DyUKAGqBOBw4InwbUN3Fmz+XJWxzIsCU3onGEwPvQHlui5MCYEnGmTgHvoCGKlgPXHS+VHInMYZJxvsohjBuyYuQBmUB7zpvXpNx2TDj0mRv7DBYt1dMhlkNbG1uB7wDndDGcI2Yi1c8zTs9iHm8lbIMsxWdffv2LY8G1Gy/S0Z6UyJmYb1Dh4vFYvIGAxhA796G9YZp1FmQxcgGY4Dcw9QDWbzpQypni9TTMlpH1GhwymhPiuDfiYLKlL1PlzSSTx3OD4KXJj4JV8U1Wk6B5Whj6gEqtAJJdm2jdcoA3ScYea8d7ZAjIHcgL7w4Gobf/up8i9PGvBQN+ma+mw45EH79q7RzMJgH7N6htiepuUkTMG7ishq8U4YY8JJmLh0XaHhp/WUg4cI9MA3maytmZJdb0RPZfgC9IfRWGZSJ5mFNis4TF3i0nWsQzHPdLn0pQHT1D70Blmw1TA+C9CfVSKy7Ie/wXlJxoBkPBfgaR5PKOV+pni1+WB90nlADKeW8sD5uubLgtUF0Irhh5Zq/6F54gynoGYZktENwOwXR5+0cl2YZmA3MFLNN3LYHMk87DC1aBwQH1lrSo7L1zbMEsPnJM/IBDpvP2J/UTrwY8wI+HZRVzRGQMIH5xkzNWRTHikUMyoqEpRk527EcudG9Qh0gGVCGTkYwtcN6PszXoqmXTacMPzN6ssTCCf1hAZkWbZdfADoqqDcmwuBX4ncET4mPJDqSMYMk5QwLYC8md2XU4jb1L9Vvo703059C42VxMYjk0AzP33BeJ8hDkg4Z+WKlO8F+jvUnW8bKfSKBijjXMGAE78NgLzHmIsaU5R1kdH+oAAqO/CL+By6vKMhozdSFijYe8+a3jLdIY2VDvCDTMFl0zDPQLmYbL81zevDDpTQe0tJu/etg+kf1Gk9EdcGyR3wk0NCayfCh96yuQ0YR9ahAHYoAyjYcAxDv3pE1gVW36y/TnpTpKFi5/UOEMciEveBh2Lzf9avqxPPOH0905JJhlnY+YHvNZ79H/qd1J0vDyUM4b7+EkRTADMNgH2LK8sU8upJkl2zkl0zIzW694TzPu9FfQ3rzGyOtP2b6lMQCWHoSTPvXrqVADDZkJJgTkMwoBh2L8r9WS1DN5qzEkD2GAUNfoF9O/qN96f8Ah3wn7TATc+mgZnzOnA0jMYVzTb8XNvkKRQ1GTALmfety6XzJtQ/LSntQ/wCgYGvLTMjVhh5CSNDCwGezf7Fd9O9VRipGyM8YMkDoFzoalr0O09SzM5JBx4Gj05IBsNCuJ6gYizD++bMSTPedNhpnT+UjZKGcN14X5LQbDA95pjbUZrIGzNq+B9jwKWp2ZoWyJhzPADaMXwP+sCtcbKjNHSQYtnTYZ8DQH5AGpFMbJKJc70NTJwT4UPzLoDLZAN4B/wB6jyZprWLlRoEg3osnfffvRszmcJNjgcoxB4O9ebxyJnjwNrefZ8Fxbfkk6FwJsDPvNEmaeipUWNKbM47wmB9iG8k/GxEcPMBpmfBDEWVMhYuMGtp3UbMSgyOPpKu5Thv71i25rCnj5cyyj1juBns+CKoswxyhxnT09gECA2xBqQAbQAOZgiS5+T8yNXDpQD714KqxPMyQPuADtnDMKgae20At0arsDehKOMmZHAL00u/3pFkdKOYG8TZr3WDJpJyzrIt0M99/eob0g3YcYAe1DDgF1Txx85IkmZlQN9z712uDUgOPC5mZ8Fjbexh96UxflmA1HjDeBp8WQDWP2AN/YsEy3XUlrrgDaZ04DW2/vWhYnOasfzLpi/feG9Y2Z9tChlJlOGbQAFOYGpki8eOBnVs3eZobx/UflXJLxRh8t370JdYfUGBCw8mTsbAA2BdE7sj4X3UWUOFH8y7JLRDZdeNvqF1u9lPqRJwjU8mIYMWYkgdAv7FW5j6q9Q5TqyfGkGP3PTYF99PesB6gd+/JAHFkk2cczIDA6XNVfjsuqEnUGegSmjZyjPnp57DOnNQ8fKgYaGEYoAuazBm2Z9iG/vQ2o4RtETmf1zNTCzflcIEaVpPm6djMOz4Jk8sMaBkqVJm+cPWpJMzp+hQBh6Td5G+n5d0QxYoTcockWaB7ARPHx0aVHM5rJMAG/eCumS6oN4fBxnZAT5W8D30UzLOmMgwaOkYOAK+keWFsI0U6AAIJyEikgwI+HeqpkjW1POOYewD0wvsVlg+nzGSc+aeoAb96gNusymwZExcPs3onlQs3M6XCNCAb+/3pky8ZL9TOo40yOGPjhpgB0usTixTkXMw2BwNaj1JgWcXmDxWXPUePds3mCD8s75CGEaLGJgDDYZhzU9gPPMHIbNkzoAHsNHnRp5KP01PZigL4OhWmnvWex4uVlSKBGLee9bl0D0fkmsxGefeoze1LrwwE5rprK4vpcJM2MTbJncDMEKiFcfrDvM+xe8Mx0oz1B0mcCVwMNhmHA1iY/RN4JFDk7AOwXTZAY6N+nM/IzIGVdAgC96e9eq4rRxcWzGABbAKcAT8HjWcX01GjbTMAqp5EyMgAMLmfBPBjhMg2Zvnsoqdt1nI/lHqABq4eaCVj3mT/AEXWaR3Tw3WBxnbeWM6oY1gclDZBzgmSDBqgAez/ALFmP1E6+Ppfy3lYxGDrewz4Lz3K+rvU8qZcD0w7wQ809dTo8Z9wzIBP/mXXlT6odOM4vqQJ+OPTjSD3gB7AWizutfvT6JnMamCxPAN4Ae+6865DqiflG9GZJJ8A7DS6DQuk+o/JdPydffpdnwVD1B1yEp28MNN4EByH3modGjJsD50VMy0TssGSKgmalqrj5e5i0udkZc+QZvmRhfgq/wAP4ouynRuVhTWwaDzDJhcDBEGD+n0mbIA5uwO8AS5m7szUSy79/j/L7E5bb1p0NAxvRfn4DJA80e/9CxHx8N3/ABWKm4sTX9K/8LWPKN2kZ394HtXBxg/MGAhvH+KiNmYOXU5uVaRckycUKTGaQ4/q813yU2NMxgA0GmYc1VTHQIAqa+Y0NXJthS6Nfxkv/sPHjDT7VDbG7iTYWbUxtoAoe26+hROJRQBwDXF6mwCBT5Rhp7VVEZrNvKdsWxq5tkL8z5r1FhTjdKdNGbUkfMmG9eXca/pZtnV2BcN613qCYBY+GbUkTAA3qrlWPdD33fpJ/VHVcafcHT3ntusEnNh95npbwI7ItygG63cDE7mhB4T1DHd+pc7yet3ajlOBTg+nwm4c5lxY303q4bwJ/ekYDki5GM95gg+DmZ8KH5YD9H2IkkZkyxYUDTOnNY0dfs04XcJ05H8yxQ5Id90Htyj6o6ojQL0B1xZu5MkuubjKn60T9Gyji9eQJJ8wcqCfyrdwlqcQ0KR9O5I9QHGism4ABvNekOlclAi/RtnD5ExbktAYGBoJ6kzx4vBhJENN6Rtusoe6tkuyOGmB+w11OuI+Ek1YwchQPvww8sIAZnwRtiWobUhn0Q5+xAePM3WweMCofAz71oWLAPR2b796xymG6q8DZyGEpsAAxoAIJy0NnzBstGLh/BP626hk4vp8Ah2bM9iDPpnFz3VH1cxVgdlwwfDX9gAq7Jn0XD0XSjHcNOgLOstHCU2caguAa9jfWLprpiH0/fGgEWfTeAGvIpRzOG9QxcMO9QdZ91s0tel4vTBfTOTis9GE5J3o9TeCyWd0hDayJg08TbIHsNGbLUlqRQzKnJMyhM+XAwArmoamIWL576hyYv07Z6bagMBGAKmYBvNZ7IyUbI7zkiEkOz3qHOMB5mTfwQ95yHFcu/GEz7DDmkvMtg6TxbORcOZKATBreYGvRo4uMEbGzHT0MaAXBnsXmnoPrmHFbkwJsYW40jaBr0ti2I2ZwbMaLJJ+MDBhe/A1up3AqsMu6s+th4jqDy3T7OpQ63Pgh6L9czz2cjffMBht4DrcDp/egDq7p97DZTKxpQahgZmBmHNZo2FJF6aZ6fNc6uV7Pmtw/RHpX6mw8M4cwZhX5gYHz+C9LfTP6zdPfUaYcCZGJjKx+dwX5KdK9ZTOnm5Jyow5KBcLsvf/AAXpPoH6g9MRZB56GDsGYZgJxjP/ALEVg5+rkXFwJXmTakjKD/MFPbxpuxwjNVlh3h3ryRg+v3slDOTAmOsSRDfQ6XD3/NELf1V6hxccwngEtkw2SWQ3goamDG/SOiwdkHJaeKKYBsBU4sHjplJRidDXldz6/wDWcqQ9AxsAslQzock6bFq/RfW+VzNzz0bQoHf7/gpzGuzpUl2PtZKge9dmS/8AT4G76hmG9DZdQwPu94zMgMAuYHvuhuP1QE/HvSRMWzoYAzwosVJcrsnzmZwAE6RgOlPetIxoHp7qtgAUWOQTCfT1hb0t502UWkPZllrp8DaeEzBjeHvSNqHb7yCHDmGBiBmZ0M+Cz2ZmQjwzkyj337+9BOS6wnuuPWZGgH6Ae80NjKnz8gD2RAvMmYUZDgC39wZpvGJkHK6Xek8LnsBQM5KCK2F/T1QqZ6mxCT2bDp7DvSTsZgGxk+81lee+qcOV0uZuvC3PM6mzTh81LPK9jSZMzLxdSaLoUjGZ8+wPejnpfKBm8p92tGTAUqDwd6805bq2ALd4U8pUx2mwz/JDvNScT9UMbg48kzki5JaC7AAHM0/De3sb7mmQmzCRJuABvua8o9WZ45HUGVjSgdfjNGYgYcKIJyH17zHUOUeBoH2IBBQKXuZ+9CsPqOfKykkJrJeTe5nRVcp9yKo8cuEeOYABOAfv7AQwUoIWYB6KAuA6f+hWXn4bUwwFknwPaqp6VDNwwGNpmHC/YulMp6pPxuDCbmDedO5n81x68gM4H6V7AHzLr9799E96U8UNnQPQMPYmSmvvnFhDyJ6gB3mmYGlD9L58nJdTydhORmgWkZXJG76NBAA2mirp8Oj+l+gzjQIwtzHQqZrN5TrLsgzE/wCoZLczhiqcRPVuDWzYg/qA/K4s5IhqHSiJyMzc/C1cNEOL6UOVizeylWwPcC28Zv8ATno+fmcoeVPYyHMDWzTpAQsezGh/nBt2KHImhiY8aNhvTePadFcYfEGGUZeyNqHuuaZIAcjoiNluoPvWazqSfeazf6sDA6ZjwDOALhnsDZ3r1oMeAcx4IvYs6+o305Z636XjAB6DzR2usVOw8MOdQ5V+QHko2h+gFqn01/a1/rRk5UZ9yGfMzDYvQPS/0jwOGhxvMM68nvM1pDcWBCjhGixhbMO8EueV7Gijxzahhc+xVWSCkcDA6GiQRB3Bnv3mhXKGDUbf2fNPyYhxzPy+47mpPmAayAPFzBU5ZGGNAA96hyskyPA9/wDTQBPOmm63doNO6FcpC814gbuw/eu2PygTHDZdPeCmSJUZqOfmDFsEwZAfWXS4dS9DnAdprB+Qa805j6X57A4R6e6YuMh2B7F66emxihmbTwuUDYCBp2b87DehymfRPYdwSKnad40elSRbo0ZNgfMAXOOF2958F7G6f6D6VleBvFDFw/0IbyX0ZjO9WPSYp6EY+yiVkx5vjuxmpBg6GuBhRE/TOLw83KABAV/Ya2kvonGCPvn0M/YsuymGPoj6mRozrwuAdKGvc2Gl5KbGw2HZOQHo+/TQ9F6+xp5QIzXpgZ81Mz03FZnpc4HmR1jCweosoj9DZt2Z6DOoAHa4H2Lclt1y0/FSul5kaU8NDYPYbi8oPDWY6AHsAyotkynRebn+WBox4VoZoWldOBhG5MbM1B4ws2YLFTtqLZ+fh9rdlx3Ke3TzFC4GrgWIzQcBcBS52ZrIYK/crOA6cPKAbokAfJdZgALgGADQU+S756ABtN/YYfmUS84OEIuhqBc+Ce47dwNI1QvOnpc7+9dopmLly9QF3dOXlfOb46jCHYSeUpny4e9cXJAE4AAaNFuNCakAYbwuifX81HAL9nBUhABb70UNuUYSTADW5oZXDjtHDDsVVIaAnPgp99WP23VaVNTcYtpdSEyLhglRzMDFQ5UWZFc3gVFa4+azFcoZ7D71dyo/nceBj6gdhrGQBhACbuAb0RdL3/auHc6CLgc1Og9LgcM3nZNADsVUy6EXOekeoAGncqxey+vw9OfUDAyWPpvjclKeEAOlAusBcIAcAwDeHzV91B1Hlczj4wSJLrjIAAAF9iDxMCh0I6foVffvu/UjlOGl4vrWmD8hKjAYBwP2LS8HnIB4tkzki2YdhrzfBO8gAM9h96u2z8rIMLlRInrg+p236cQda5SNhMWYvzDOlFpfTuL6h+jGQkg6DThy2AID50WJ/R91n/z8wgA8IAb9TMzXsP6kQ42e64h4SE80/PAL0A+C7HD3jVIanDz91N1LP6hyEmTPPUM1jJPnFyrwBai3vOdKycXINmUAmfwWRZyGDWU3BpmH+aT1k7l8IAyg2HQXD+a7ZggmR2TajC3s7FAoDtL+nRU/WhPR8JGksG6wHvA1zbWBXqgTaaZMuF99EBvADobPTPsVlqyZF/MSSfD5qG4FG1DUnwrRN5rfcgW2/TH6jO43OBAyMkgA9gexYw4AcDO91xITD1mjIDBY+BUvZn1KxH3j0nG6haMTOh3D3gvMeQADcCgaZgtO6X65k9QfSt7pWaY+ZaDYZ8zBAeUjn5wwACA2thrde5c+ihbM/LnG5gf/AHo26bIGsYACH4w3+B+xVuNBnEORslKjeaB3aAKZDyhsdZ7IwuG7/gCXkzbdW/qhJ6fnwIEIGr6FQM/etp6D+oP7TZA8Vm4H3dleTBgew15RemRnXKAyIGfvDgirpvOHiJDMZ2ST8lo7RTA94KGpxZ01t60ywxmpBhNjDE3nR4G+YLti8zMgR2QgSRfZM60PmsWzHUHWb+QgPAyTjIGHZzD5rZss7A/8u4cmKzTKmAGYB2Gk5V6EMrqsCyoeaB2IewLgGxVs4pJ5g3op6kZ0LAYHwP8AQqGKGVyjcYyZFwDDff3qnyHmcHIAHXnWJNNhh70TJjVIfUMnER2YYPXkyOYH2KZB6rA8pPjOmVwCt+xZW3kZ7DhyZUbzwGF7mH/zUMs9GxrZmDOgcjcFzuAJf4w0KZkQix5kwntM7hQOwAQl+3TOGvJJ4n3j/IUCHKZ6gxd2jFxkAMDodN6yWU0zIznln3iYAzqF+xY/ENO3UH1G6kyWQOY6ZN6R7AD2IPbfmZLxmT5BkBu7/wBBq+zGGmQpABCksS5J7gD3/oQ9BHKyGzZCNvDmAGnzyGjBiswunJLxvfiT2gCp480MXlI2SkRvN6XMPer7NAcXBhJmRnWO0DMNl0EjnIwSGWZADoma3Uwn0uP2vNrIGbUMWwM7gHsR5031X97Q5kDJAPmQDYYAsrlY035H4MxfA9wUWhdA4MIsiZJyhnw2AHvT5nBenbhcCDn3ri40AMGZcFxlHJPIGAARhf0wAEmWsrNmBGhRnb95mqgkjQ6bxAOy6T0oGmzudzD2KHkMdJix7zZIhQ6uAHME8sjgcT0mcwDKXJ/p34AgEyUyY5SODrhohxPTkyZkACf6AGhLF9fsx44ST0m2T9gKZI+of3lkACABMb63WNDLSCi4HEx3ozskWzAN595rjHzwZIGYbTwtsjtuslnQJM/KHJkZLUvu5pY+O9HmGDUkmwDvutmPQkXAxgbB5qrh3vdT5DrzuUBk/TAVl37XyYGLBkDE6BvNBOW+pGSi3Mqth2GjRb0hB8nFyBh5nUM+xcXJptTDBoNT2AvHMf6vycdnJMl0yfM+AXWtfT36jB1e5JAgFiSHzXs0Mt4ZlG636vpmoDjX4y5cEwZQA3v5qY27qt0/LT9GJNbxwAA2Gsc6qlZJrqB6GFqAtsb9Juh+p7EH5zBhMygSb096AxaOLzvICM0m4sk8gZkZAAcANau5hGWMeZgAOGALMRiz5mcoIEAAfNFBJhuhFkvGHMwUORKB1x4HT1A7FazsJJgR7/mXbVa3CAY564XM0sK0hM3Pw57KKA2IP5DRdU8WpIzKCH+CfIdhtQzelV2Bvol6LoW9OwAi+sEkTA+xEMh09S4Lz90/1QbX1MBliYRwHTpQ+xbxKMwbM79iNBxedM3KX3rzZ9dI4DMxUkNh8brWpXUehkDCmpRZj9UGvvzpOBJaMW6Gvb/bDzh5qRcPHULZ81svTXX0PH9MAE14jMNvBYvIa0JJtXvVcxvp/BSawblv3/mhigkBUDP50Qf9QOo8fnmID0M/WDmCy4v4r4i708y+iX2KUwZXpb7AUK3/AET2yMHLj+7xSJp7U6TZZlQA/kn46WEbIeBmGoBdikRRCU2ezeCrpIAE0wAKVW6r+Tyf9Uu1TUlsqxw+akk0AN39iZHa87kWYwnQzOu9daqTSjPOmDhj2KfHH8PdNzWOexeUBl/kAbDDvXBl28OiNDMJhPmewExsDCQBkozfpOHddzL7W0Snr1XrYAfhtUBxgBkGpkHdDCvqbFGeA9QzBMphDcD1NvBEmJ6qPHY84zsMXw9/sQ3Q9M7nRQHLhcPsSzMiqR1UZyD0goBbaKnbP8eGlvse9VTNCc3gpn5UgKbAut6FSPHnTDFgBBqBpqnjmGmZlUFcXB3HharlwVC81dwwBe0XMp7Jg1IA77L3U+RKB1u4HpqnbCjdD9RInTBzZw/QjTeRb07IktZgJMV4gktbgMHKUNbB0n9TZPSn1BPN5LVyswwpvNYJi3TCQZiZb+xX2QA344SR9QwVPKrhip2/RTCtYrrz6ds9VTHhiA6F3AvwXlrqh2A71Bko0UxfBozoYHdYP+1XUMLFhjWp8luNxoBmCrY+SyQTDNp4rlzvvumdaLmcDaVmwihsDeB+pdRst1HAzP0/ONICkkOCEsg7Jdj3drv71QjtcO57FDVK4cRHSvfgaRCZt708hM3KdiRbHKJB3ohuNAe+ijXMHN3BWVw37Fx0jPsRlvJmNlPY3MMz2j0zaOwAHet48lA6jjs5jGgTjxhZ4ADgsHIQFy/+C2b6Z5lmE/JZIxbZkBQwNMlNUqHMYl6RHePHSScZAw9H2KhxLptdQUlM7wCrZ+xav1NAk4PKHPxYbD3B7DQNMzgZSRd2AMWT3mAIr0YWsp0AwYaXpyb80zHzXmm7uhqGG8DNMZkBKcDVO4eyintiy1IAwAjC/wDoUle50NO6R+pMAGwDqWe6wDXAzDgavpn1k6b/AG4gY2LPdNmRt8yYbF516ohhsmRamyfMPYgZuaAzN7I7FLnCqX6U9P8AVATI52mMUANhgdABdnJ8bqDHvPNG1kTiczA1+ekXPT2o5sxZLoAfPf2I/wDpz9QT6GcyoSrSo0tvYBnehreBp7AnTZ8r6dzIwG1EMOFOxZWWWgfd4Q8jlRbNoD33vdY5nPqJnspkDBqToQ3uYAs9ygvOxzeAyc9+9GBNPTPRvVEAurHsU1JAI19h+9WXWGGeCRJkwntcDbuxTsXkXDnJxfUkae0ZXAwvv7F6QHrmA1MjUk6gGAXA+xGBVKGGeePp9550HTnx7kBpYfKZXy7zwATD17uX962yDMB2OzMixmn4x8wAFayouNn4p6M1GaYMw2GAd63PoXpkua6hk5T6fnip7IuBsIDp3rHGQgNdWRgygO+TA/UAOa9COYSA1jzCfPabO+zeqEsN0MbZnMniZgfNMqRoHt5voOB1BJOFJfANmmBhwRb0r1v09kuoPINGXPZdvvWOdXYPFD1Yb2Jki/Gd7KKH0zIDA9eRp7oDQD/5a8D1FMyUOLlDPy3A/YoznUxg4fkoxNmYU/LomZDrfox1sHikjcA3ghWR9UOmGpAA08LYAazsZaXielAdwetlD15Lu9VU7pzFSIb2Kdjcw9M6Kte+r/T3l2T8zqAAb6LPct9aYA5wJONjE5QO9GxlVdRfT4MblIzIGQQzO3NScfjQjtmAs7N9DNAHU31fyuckbYwtgHBb90TPjZ7/AMO/n5QC3PADuayYyuQ1MayAA7ZsP1qTvGOdntMA71PlZnFC2fmHtQwT5WGemdL+ZA/RdC4GtfYDczKA1HADe2X3mhjqKfh3+lHmWpOpJ7EGZR16HkDjEZGF+9DbhmLZ1AnN+9I9wp3CeH576o/6Dyk/B9cMm0BaLp76IexrQB1BGOUF41w2L1d050bhzbZntRhcuCdM3Ypp2Pynmo4GAFSgK+byQC4G8m0PNxdKOFAoAexRnNZ2RQw2e9PkNIj5SMdAA9Q1JkGEqOB3FuizHe1IAwO4d6tW8o81SplT9CYBI41e4GexUJNRosg9KvzUOR1BpOeqYhf3oSzmeZdbPyr2m98EAVZabG+7zAngv2IJjx5Lsy7R3DvVILr0qOBkZHRX2DmHHyFNxgYVNAFTbUYIVyDUP9CoZ2Bhyo7wGHMD2IqkPxmodzq2FOayLq7rwMXjj8k8JndIqgweQB4T6saJnQAfXrRmYDuHZMDvdsF4kzGck5nqg58jmB22L1p0XNCb9O4Ek/UMwATWNWXkJZaE8fUnpBsNUX1EinF+j7JgZAepvotTeIP2gZ9hqh62wf3vi2YFybAz4Lf2W8WeJeJOeJF4/aX87LoI+mtzyH05jR8RJMjE3AC6xBzw0pBgPadUipN1tGMa+O3xXLw8fsXUi8S/ivlbJdSZ/T+rknD/ADS/qbktqS2tsVMCM+YmFwL9yizjAso8YcCUMSof2r74ldz7Vuq9AJrnvCmwwVbqnFngYHpmB3BWQuhv43VbMMCc+a7NeiWJEmezMbKY+AdxckgFTVDHdAXAAVV13ipHClTU8V/u3UrsQDmYJj1NP9yh6pk3QjXZsTdbpdUEVK+xbtYDgX3ri8Xpnvuo0QtJswBRiMy3n6aZonLtq3UF781dbep81GkAYSEtuZIaaZ05rs2djAD964eAb/BdI4GGZZDnvQPoeOGAYtmmw6KkuZzNiuCEyj7+wFTiJ+cTC5T3BpH3+xQBP8QipnB5LKdPnJhRifBr8ww7EPOY2ZH3nGJvf3glt5uFxFMGmzV3HdN2Jz0wQ3HaknsMCD9avmwpsA/9CfDKtchyZWcAIrJPmfAAWqdI/SDqfM+ZM4BRTAL+si36HtYEPqhGDJRteeZ0YAw2L3/MGNDjvaQCwFN9AV08twXVYfk11RjjxuRegOhvaOh7EGC0ZuX20Xsb6rdHxprcmfjWR8zyOiAMD9I42e6bjPDJ0JJhvD5rk16WfDzqTXpnRMofOi37qj6Nyemum38r58X2Q5rGXI4Bf/5rBqn0PT3+mkTHpBXgrUgu2GxP8kZ7D4Ie7U5R/UCgK+wIG1kKU2H7+xSY+IN1o+RmruLAAJAAYaYAmTJNejZsHCDOdJnGMCcNoDMDNZXnOnzYkGAhpmB+xeivpnFZLp+e9e7wBQAVbmunAlZADpvN/f8AoVU8rsiqw88Y/FzwkABgRgfwRDMwmVaj3YjFQ9uwLr0bK6cw8LpOkIBOSB3uYIYkSj8nSgtmHYAJFcMHzTHMX0vm5TUmNKgO+WPgZgsi6swMnp/OGZMne+wF7AHPH5cwa9iz36hYSHnOizmNATk9oN6hqT9vLsfImcgAANneiSDM9M2SAXAPvPsQIFouTIHQpU6/wV7Hd9S90uaaHMPc6YF6gBwU8Wjd6fkmId6G480ybvtbMEW4MmX8gYO7wMOCNbe+6hbCsczMN6YMp444AfMNi7ZD0JjzIWbo5sUCtd69+G2zdC9YScHkAjTJJNsmGwDO4L0Ph8jjeq3D8k8IPEFAofevD0W7si5H2IhwvUGSwci8CYTBgfO63NAYddYjK9PdaTIEqS64BncAP2IGbubm4yRbnOo8r1RIjScyYvyQCjZgqdtrysyhhsXhaG5HPy4GB96h5JoIuL8ze5rSOmemXuo3JgRzH0tx3XHqro08XgzeMxfAOfwXtBjkd3zrhgYadw96HihmGUMOwOfzRU4IMZADANigTrhIN4Q2GlKMu0EA+7zDhsXFwAPZQXP7EyO76Z79NIbi5/zEsIY46McwLAX+tEkXM5WBgzxsWeTEa/AFW8XL02KNOdA5gUuGxBeT2ZB6h3PUPvujAuuckPS8bGx66IBW96LPSvqX967ENY96XWtihnhekp/WEwzi+oYOeotjw/0RAIYHPMj99AWb/TPq2N0vlJJyvyTBapmPrSAx6RQJPn/sFwP0v6Yh/mxt5+81pGHwwRcOyywBNh2AvHmW+pObyOQAwkkG+2w17V+n+WDM/SvGyTMXHjDeaqnDHvdk9iz1Av6fwoq16KbTe4NRG0rbMAD9Q1DcaA3DsA39iZmLbB7eOA2zoaYMMxc4aiJKhqbdgLrUP+KxUgA5zFhKw9wD8SCzGR09ktUzEP8AQC3tyOBOHc9QPYoHl4wOU27N6AxzH42fFkAEgCNlFUymO6Xkz4rIm80BnRFsgo3mPVNpv5gl5Bl2OYHVwDDh7wU9B4n6o+pPUOUkGAySgs3rQOazpzKSZTZ6rxOB81pH1K6Qn436gPeVhkcZ07hQFSYn6c5ua2ByIxMAfvU4Q+l8CeezGiAFQ+Zr1R0zjf2c6XCAT1wDcgPpPDRulPAwM9Qz5mZq4zUw3XLtPFQ/Ys7AtjkzK6kuBjsT886YuAAeywAhXpN++Uk3MnD95q+yDur1QF+wKJ8+5dPP3U3Xc1rIzIABSuw1kzjuq6Z+PMzsjP6hwxideyTAKah2QCl1Xu1E+hLoJV8dyYX8V8WNtGlW+3+CakkpaMOEq+KakklhbjtBRHC9fuUsgMktLZ812KSzWUHxIfHw/epbYXbXHSP2Ls2dOKMt1WiEDv8ABT47tJAX4JjY3b+ajUPUuPNMkoWyI8YI4G0Y0NQHd+xQG3XnaMhZdqGDu9MLIhAVWyjtJPvVlKCke91QuGZuJZ2Ulk6ht2KbjhKRnGQ8AJw79irL1b8Quijo2YcDqjzIMi+YB3t3oifexn+Q7Lp7NnjzkhAfoYbDAFSOY56O2BuhvPmHBekPpfnsxnPqIEOfXyGgeymy6X1U+n0/9pDyuLhicM+YMhwT6nCfl8K36O9VYTCNz4GWq2EgwIDMLgvQL2N6D6jbAACC+B86UA142c6I6hazkZlqA64ZhdigK+xPQ3WY5TyxhJivHtA77AWDhb9Xuj+nunG8afTzJtm7e9DvsWMxRMJG8Cua2nKdURunMHGwmWjDlcrHOr5vb6LH5UrzWUOSAaYGewA7E6Zuyq+23/RHAzJn1cjZIa+WiHc/gvYf1OykyL9I8rJxtvOAFwp2Lyj9C2s211wbwRiYgGG8zCgKn+pn1V6h/bzK4ePP0IDR6QAHeC7usQRndn9A9YZXPZSZjclJGVsPTuG+6HnOtc30r1BJAALRAz2G3RAHTOUPHdcRpgHQ9fefYvVGW6XwPWmHChg5JIAo8C4dqsMWzn1OPqjo96A7D0L81kpNAbm8Lr0JkPpFGwwABTLmfBUL3QB6Zm08NFjLfpH2xkWg7OHzVlFi6rm0NT9CmZDG+TmGyQFcD/1on6LxYZfrCHA3MXOm9LyxVR/BcdG4SNkuoPLP2b2Gd6IezmNOH1ZJjNATgAeyi3XF9Ph051Y8YPa9AME9zFwPvw5JMi+Z796qnkRXup/pG7JH7yjSgILthQzBaLOaAHL/ADUbHkDUxkxZFjs2K1ygXjmYhsBdWeVxCGvtAbpKaMLiF0GZpoIrkm/CmxXYmYbxDTM1SZQgdhvA6YmZqTvNx9Hz+4DPvJlpy/5ZpSMpAJsNV4AA9xgB81kuWmSWspJjGZNgBnRD0iUbrZgbxOLj06MKT6iQIzXUBz4BiEYz2ACCYsrgHeCM5EUCcMJBk4B8AQPIiyYEu7rZNiR7P+qjMn4XrMoNTmr6DNOPIAwPvugkSo3ceBqyZlXdCqG2hSPxkcJIc+9VrgVj+N9nsUPHyjCOYdner6DDDIzGWWj3nsAFr79GPhDhmAOAZAV1MEDdcOgE4tLx/QZk2BvmNw7FpGJ6VxUWOBusi4nzywXt54bCS03cAJuiM+m2oGZ6gCHKMmzMAADW0yMHjTbMAjDQw37EAZDpA4uUCfA9MwO4UXmRrmNsXiT6ZyByYpk4DoUOgKHnJmNn4OSzKkjv30+atcfmQdxbIOn6whQw+aw3roZMPqA9IybjO7m1ingGkXayj1/UC+xVswAOh8FPvqtgY80iEHY9OaRaiQ226ByNinkYBSygSmvK5AzANiRPm7wDTosmLJw6N3FVTh2kXunk6ZtmofNxATxINPck8RhD+Cjf1KAu2kZR6HsQXSMLplH56f6EwTM2zsZGuwtHvCieyxeQYEe9agJMHETMlNpDZJ8w9i9n/RfG5XG9DvRsoBsb9nwXn76SkcX6qRgdZ1GTAx3hsXthsYwQ9hi2Z9ir5iUx6gSAPa4Yd6FchlwjuGDXMAVw9MjNOGDskb+y6A8o7DkZAzakjcOxVmLKLmzKgOhv+a7PZyN5cwCxmCA3n6SA3p8eLMdbuAbDS6TruV1BJKRQQoAd6G3Jk99w7GW81fDgZLsf/lmpLeGNqNuDeG5GjAk8Zg36pkaT2SkjTSMqJZSLMCQZmBNgh5wZjtAaAtiRf7YaXHOHKxbJzAaMw7zC6rctKxrWLMBMW7hs2IJEMwGwwJKRFnu48zfAtnvUwZjKmmeQeseoF9i7NzTNuhGSockQNdQSQ/L37FMjgBNAYGvbMaF0e1eRJePgifIAH3gBhW4AqHpegYsz/Luak5KUy04Zme8A2Jk/BFfbAfqs0BdQRpId7ayXw+z7dv8AwWu/US8qGzJANgGsiH+dUjr9vY+HxJfal/wX0RIvH9yw25l/BNUt5qscDURLpskkkkgP/9k=';
const SID = 's_' + Math.random().toString(36).slice(2);
let CID = 'c_' + Date.now();
let mode = 'normal';
let topic = '';
let busy = false;

const chatEl = document.getElementById('chat');
const wrapEl = document.getElementById('chat-wrap');
const sendBtn = document.getElementById('send');

function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2000);
}

function toggleSide(){
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sov').classList.toggle('show');
}
function closeSide(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sov').classList.remove('show');
}

function toggleDrawer(){
  const d=document.getElementById('drawer');
  const ov=document.getElementById('drawer-ov');
  const pb=document.getElementById('plus-btn');
  const open=!d.classList.contains('open');
  d.classList.toggle('open',open);
  ov.style.display=open?'block':'none';
  pb.classList.toggle('open',open);
}
function closeDrawer(){
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-ov').style.display='none';
  document.getElementById('plus-btn').classList.remove('open');
}

async function loadChats(){
  try{
    const r=await fetch('/chats');
    const data=await r.json();
    const el=document.getElementById('chats-list');
    el.innerHTML='';
    const ids=Object.keys(data).reverse();
    if(!ids.length){el.innerHTML='<div style="padding:12px;color:#333;font-size:13px;text-align:center">Нет чатов</div>';return}
    ids.forEach(id=>{
      const d=document.createElement('div');
      d.className='ci'+(id===CID?' active':'');
      d.innerHTML='<span style="font-size:15px">💬</span><span class="ci-txt">'+escHtml(data[id].title||'Разговор')+'</span><span class="ci-del" onclick="delChat(event,\''+id+'\')">✕</span>';
      d.onclick=()=>openChat(id,data[id]);
      el.appendChild(d);
    });
  }catch(e){}
}

function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function escJs(s){return s.replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/\n/g,'\\n')}

async function delChat(e,id){e.stopPropagation();await fetch('/chats/'+id,{method:'DELETE'});loadChats()}

function openChat(id,data){
  CID=id;chatEl.innerHTML='';
  (data.messages||[]).forEach(m=>addBubble(m.content,m.role==='user',false));
  loadChats();closeSide();
}

function newChat(){
  CID='c_'+Date.now();chatEl.innerHTML='';
  showWelcome();
  fetch('/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:SID})});
  loadChats();closeSide();
}

function showWelcome(){
  const w=document.createElement('div');
  w.id='welcome';
  w.innerHTML=`
    <div id="w-avatar"><img src="${DED_IMG}" alt="Дед"></div>
    <h1>ПОШЛЫЙ ДЕД</h1>
    <p>Спина болит. Чё надо?</p>
    <div class="qbtns">
      <button class="qbtn" onclick="askSovet()"><span class="qbtn-icon">💬</span>Попросить совет</button>
      <button class="qbtn" onclick="askPredskazanie()"><span class="qbtn-icon">🔮</span>Предсказание на сегодня</button>
      <button class="qbtn" onclick="askPervyi()"><span class="qbtn-icon">🗣</span>Пусть дед скажет первым</button>
      <button class="qbtn qbtn-danger" onclick="setMode('yarost');qs('Привет')"><span class="qbtn-icon">💀</span>Дед унижает</button>
    </div>`;
  chatEl.appendChild(w);
}

function setMode(m){
  mode=m;
  const names={normal:'👴 Обычный',yarost:'💀 Унижает',sovet:'💬 Совет',predskazanie:'🔮 Оракул',pervyi:'🗣 Говорит'};
  document.getElementById('mode-label').textContent=names[m]||m;
  const btn=document.getElementById('mode-btn');
  btn.className=(m==='yarost')?'yarost':'';
  btn.id='mode-btn';
  document.querySelectorAll('.drow[id^=opt]').forEach(r=>r.classList.remove('active-row'));
  const opt=document.getElementById('opt-'+m);
  if(opt)opt.classList.add('active-row');
}

function updateStatus(text){document.getElementById('hdr-status').textContent=text}

function askSovet(){mode='sovet';setMode('sovet');const w=document.getElementById('welcome');if(w)w.remove();document.getElementById('msg').placeholder='О чём совет?';document.getElementById('msg').focus();showToast('Режим: Совет')}
function askPredskazanie(){mode='predskazanie';setMode('predskazanie');qs('Дай предсказание на сегодня')}
function askPervyi(){mode='pervyi';setMode('pervyi');qs('Начни разговор сам')}

function qs(text){
  const w=document.getElementById('welcome');if(w)w.remove();
  addBubble(text,true);sendToServer(text);
}

async function sendMsg(){
  if(busy)return;
  const inp=document.getElementById('msg');
  const text=inp.value.trim();
  if(!text)return;
  inp.value='';inp.style.height='auto';
  addBubble(text,true);
  sendToServer(text);
}

async function sendToServer(text){
  setBusy(true);showTyping();
  updateStatus('печатает...');
  try{
    const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:SID,message:text,mode,topic,chat_id:CID})});
    removeTyping();
    const d=await r.json();
    if(d.error==='invalid_key'){showOv('ov-key')}
    else{addBubble(d.reply||'Хуй знает.',false)}
  }catch(e){removeTyping();addBubble('Связь упала.',false)}
  setBusy(false);updateStatus('в сети');
  if(mode==='predskazanie'||mode==='pervyi'){mode='normal';setMode('normal')}
}

function addBubble(text,isUser,animate=true){
  const w=document.getElementById('welcome');if(w)w.remove();
  const div=document.createElement('div');
  div.className='bubble '+(isUser?'user':'bot');
  if(!animate)div.style.animation='none';
  const row=document.createElement('div');row.className='brow';
  if(!isUser){
    const av=document.createElement('div');av.className='bavatar';
    av.innerHTML='<img src="'+DED_IMG+'" alt="Дед">';
    row.appendChild(av);
  }
  const txt=document.createElement('div');txt.className='btxt';txt.textContent=text;
  row.appendChild(txt);
  const meta=document.createElement('div');meta.className='bmeta';
  if(!isUser){
    meta.innerHTML='<button class="bmeta-btn" onclick="doCopy(this)" title="Копировать">⎘</button><button class="bmeta-btn" onclick="doRetry()" title="Ещё раз">↺</button>';
  }else{
    meta.innerHTML='<button class="bmeta-btn" onclick="openEditWith(\''+escJs(text)+'\')" title="Изменить">✎</button>';
  }
  div.appendChild(row);div.appendChild(meta);
  chatEl.appendChild(div);
  wrapEl.scrollTop=wrapEl.scrollHeight;
}

function doCopy(btn){navigator.clipboard.writeText(btn.closest('.bubble').querySelector('.btxt').textContent);showToast('Скопировано')}

function showTyping(){
  const d=document.createElement('div');d.className='bubble bot';d.id='typing';d.style.animation='none';
  const row=document.createElement('div');row.className='brow';
  const av=document.createElement('div');av.className='bavatar';av.innerHTML='<img src="'+DED_IMG+'" alt="Дед">';
  row.appendChild(av);
  const dots=document.createElement('div');dots.className='tdots';
  dots.innerHTML='<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
  row.appendChild(dots);d.appendChild(row);
  chatEl.appendChild(d);wrapEl.scrollTop=wrapEl.scrollHeight;
}
function removeTyping(){const t=document.getElementById('typing');if(t)t.remove()}
function setBusy(v){busy=v;sendBtn.disabled=v}

async function doRetry(){
  if(busy)return;
  const all=chatEl.querySelectorAll('.bubble');
  const arr=Array.from(all);
  for(let i=arr.length-1;i>=0;i--){if(arr[i].id==='typing')continue;arr[i].remove();if(arr[i].classList.contains('bot'))break}
  setBusy(true);showTyping();updateStatus('печатает...');
  try{
    const r=await fetch('/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:SID,mode,topic,chat_id:CID})});
    removeTyping();const d=await r.json();addBubble(d.reply||'Нечего.',false);
  }catch(e){removeTyping()}
  setBusy(false);updateStatus('в сети');
}

async function doSummary(){
  closeSide();setBusy(true);showTyping();updateStatus('думает...');
  try{
    const r=await fetch('/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:SID})});
    removeTyping();const d=await r.json();addBubble(d.reply,false);
  }catch(e){removeTyping()}
  setBusy(false);updateStatus('в сети');
}

function openEditWith(text){document.getElementById('inp-edit').value=text;showOv('ov-edit')}
async function submitEdit(){
  const text=document.getElementById('inp-edit').value.trim();
  if(!text)return;closeOv('ov-edit');
  const all=chatEl.querySelectorAll('.bubble');const arr=Array.from(all);
  for(let i=arr.length-1;i>=0;i--){arr[i].remove();if(arr[i].classList.contains('user'))break}
  addBubble(text,true);sendToServer(text);
}

async function saveKey(){
  const key=document.getElementById('inp-key').value.trim();
  if(!key)return;
  await fetch('/update_key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
  closeOv('ov-key');addBubble('Ключ обновлён. Пиши.',false);
}

function showOv(id){document.getElementById(id).classList.add('show')}
function closeOv(id){document.getElementById(id).classList.remove('show')}

loadChats();
showWelcome();
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
