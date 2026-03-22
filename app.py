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
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#1a1008">
<title>Пошлый Дед</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Russo+One&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">

<style>
:root {
  --orange: #d4813a;
  --orange-dim: rgba(212,129,58,0.4);
  --orange-glow: rgba(212,129,58,0.12);
  --text: #e8d5b0;
  --text-dim: rgba(232,213,176,0.38);
  --bg: #1a1008;
  --bg-dark: #110c05;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: 'PT Serif', Georgia, serif;
  height: 100dvh; display: flex;
  color: var(--text); background: var(--bg);
  position: relative;
}

/* Текстура дерева/старости */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.45' numOctaves='6' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='400' height='400' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 400px;
}

/* SIDEBAR */
#sidebar {
  position: relative; z-index: 10; width: 240px; flex-shrink: 0;
  background: rgba(10,7,2,0.85); backdrop-filter: blur(20px);
  border-right: 1px solid rgba(212,129,58,0.12);
  display: flex; flex-direction: column; transition: transform 0.3s;
}
#sidebar-head {
  padding: 22px 16px 14px; border-bottom: 1px solid rgba(212,129,58,0.1);
  display: flex; align-items: center; gap: 10px;
}
#sidebar-head span {
  flex: 1; font-family: 'Russo One', sans-serif; font-size: 11px;
  color: var(--orange); letter-spacing: 3px; text-transform: uppercase;
}
#btn-new {
  background: none; color: var(--orange-dim);
  border: 1px solid rgba(212,129,58,0.2); border-radius: 6px;
  width: 26px; height: 26px; font-size: 17px; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all 0.2s;
}
#btn-new:hover { color: var(--orange); border-color: rgba(212,129,58,0.4); }
#chats-list { flex: 1; overflow-y: auto; padding: 6px; }
.ci {
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  font-size: 13px; color: rgba(232,213,176,0.42);
  display: flex; align-items: center; gap: 8px; margin-bottom: 1px;
  transition: all 0.15s; font-family: 'PT Serif', serif;
}
.ci:hover { background: var(--orange-glow); color: var(--text); }
.ci.active { background: rgba(212,129,58,0.12); color: var(--orange); }
.ci-txt { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ci-del { opacity: 0; font-size: 12px; color: #444; padding: 2px 5px; }
.ci:hover .ci-del { opacity: 1; }
.ci-del:hover { color: #e05555; }
#sidebar-foot {
  padding: 10px 14px; border-top: 1px solid rgba(212,129,58,0.08);
  display: flex; flex-direction: column; gap: 1px;
}
#sidebar-foot a {
  color: rgba(232,213,176,0.32); font-size: 11px; text-decoration: none;
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 7px; transition: all 0.15s;
  font-family: 'Russo One', sans-serif; letter-spacing: 1px; text-transform: uppercase;
}
#sidebar-foot a:hover { background: var(--orange-glow); color: var(--orange); }

/* MAIN */
#main { flex: 1; position: relative; z-index: 2; display: flex; flex-direction: column; overflow: hidden; }

/* HEADER */
#hdr {
  padding: 0 18px; height: 54px;
  display: flex; align-items: center; gap: 14px;
  background: rgba(10,7,2,0.7);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(212,129,58,0.1);
  flex-shrink: 0;
}
#menu-btn { display: none; background: none; border: none; color: rgba(232,213,176,0.4); font-size: 18px; cursor: pointer; padding: 4px; }
#hdr-logo { display: flex; align-items: center; gap: 10px; flex: 1; }
#ded-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: rgba(212,129,58,0.15);
  border: 1px solid rgba(212,129,58,0.3);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
#hdr-title-text {
  font-family: 'Russo One', sans-serif; font-size: 16px;
  color: var(--orange); letter-spacing: 2px; text-transform: uppercase;
}
#hdr-sub {
  font-family: 'PT Serif', serif; font-size: 11px; font-style: italic;
  color: rgba(232,213,176,0.35); letter-spacing: 0.5px;
}
#mode-btn {
  background: none; border: 1px solid rgba(212,129,58,0.18); border-radius: 20px;
  cursor: pointer; font-family: 'Russo One', sans-serif; font-size: 10px;
  color: rgba(212,129,58,0.55); letter-spacing: 1px;
  text-transform: uppercase; padding: 6px 12px;
  transition: all 0.2s; white-space: nowrap;
}
#mode-btn:hover { color: var(--orange); border-color: rgba(212,129,58,0.4); background: var(--orange-glow); }

/* CHAT */
#chat-wrap { flex: 1; overflow-y: auto; position: relative; z-index: 2; }
#chat { max-width: 680px; margin: 0 auto; padding: 28px 18px 8px; display: flex; flex-direction: column; gap: 16px; min-height: 100%; }

/* WELCOME */
#welcome {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 16px 20px; text-align: center; gap: 24px;
}
#welcome-avatar {
  width: 90px; height: 90px; border-radius: 50%;
  background: radial-gradient(circle at 40% 35%, rgba(212,129,58,0.25), rgba(10,7,2,0.8));
  border: 2px solid rgba(212,129,58,0.3);
  display: flex; align-items: center; justify-content: center;
  font-size: 52px;
  box-shadow: 0 0 40px rgba(212,129,58,0.15), inset 0 0 20px rgba(0,0,0,0.5);
  animation: pulse-ded 3s ease-in-out infinite;
}
@keyframes pulse-ded {
  0%, 100% { box-shadow: 0 0 40px rgba(212,129,58,0.15), inset 0 0 20px rgba(0,0,0,0.5); }
  50% { box-shadow: 0 0 60px rgba(212,129,58,0.25), inset 0 0 20px rgba(0,0,0,0.5); }
}
#welcome h1 {
  font-family: 'Russo One', sans-serif; font-size: 34px;
  color: var(--orange); letter-spacing: 4px;
  text-shadow: 0 0 60px rgba(212,129,58,0.25);
}
#welcome p { color: var(--text-dim); font-style: italic; font-size: 15px; max-width: 340px; line-height: 1.8; }
.qbtns { display: flex; flex-direction: column; gap: 9px; width: 100%; max-width: 400px; }
.qbtn {
  background: rgba(212,129,58,0.06);
  border: 1px solid rgba(212,129,58,0.18);
  border-radius: 12px; padding: 14px 18px;
  color: rgba(232,213,176,0.65);
  font-size: 14px; font-family: 'PT Serif', serif;
  cursor: pointer; text-align: left;
  display: flex; align-items: center; gap: 14px;
  transition: all 0.25s ease;
}
.qbtn:hover {
  background: rgba(212,129,58,0.12);
  border-color: rgba(212,129,58,0.35);
  color: var(--text);
  transform: translateX(4px);
}
.qbtn-rage { border-color: rgba(180,40,40,0.25); }
.qbtn-rage:hover { background: rgba(180,40,40,0.1); border-color: rgba(200,50,50,0.4); }
.qbtn-icon { font-size: 20px; flex-shrink: 0; }

/* BUBBLES */
.bubble { display: flex; flex-direction: column; gap: 3px; animation: fi 0.22s ease; }
@keyframes fi { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; } }
.bubble.user { align-items: flex-end; }
.bubble.bot  { align-items: flex-start; }
.bwho {
  font-family: 'Russo One', sans-serif; font-size: 9px;
  color: rgba(212,129,58,0.45); letter-spacing: 2px; padding: 0 5px;
  text-transform: uppercase;
}
.btxt {
  max-width: 82%; padding: 12px 16px; border-radius: 14px;
  font-size: 15.5px; line-height: 1.62;
  white-space: pre-wrap; word-break: break-word;
  font-family: 'PT Serif', serif;
}
.bubble.user .btxt {
  background: rgba(212,129,58,0.1);
  border: 0.5px solid rgba(212,129,58,0.22);
  border-bottom-right-radius: 3px;
}
.bubble.bot .btxt {
  background: rgba(255,255,255,0.04);
  border: 0.5px solid rgba(212,129,58,0.12);
  border-bottom-left-radius: 3px;
}
.bmeta { display: flex; gap: 4px; padding: 2px 4px; opacity: 0; transition: opacity 0.15s; }
.bubble:hover .bmeta { opacity: 1; }
.bubble.user .bmeta { justify-content: flex-end; }
.bmeta-btn {
  background: none; border: none; color: rgba(212,129,58,0.35);
  font-size: 12px; cursor: pointer; padding: 2px 6px;
  border-radius: 4px; transition: all 0.15s;
}
.bmeta-btn:hover { color: var(--orange); background: var(--orange-glow); }

/* TYPING */
.tdots {
  display: flex; gap: 6px; padding: 14px 18px;
  background: rgba(255,255,255,0.03);
  border: 0.5px solid rgba(212,129,58,0.1);
  border-radius: 14px; border-bottom-left-radius: 3px;
  align-items: center;
}
.dot { width: 6px; height: 6px; background: var(--orange); border-radius: 50%; animation: pu 1.3s infinite; opacity: 0.6; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes pu { 0%,60%,100%{opacity:0.2;transform:scale(0.8)} 30%{opacity:0.8;transform:scale(1.1)} }

/* INPUT */
#inp-area {
  flex-shrink: 0; background: rgba(10,7,2,0.8);
  backdrop-filter: blur(22px);
  border-top: 1px solid rgba(212,129,58,0.1);
  padding: 10px 18px 16px; position: relative; z-index: 3;
}
#inp-inner { max-width: 680px; margin: 0 auto; }
#inp-box {
  display: flex; align-items: center;
  background: rgba(255,255,255,0.03);
  border: 0.5px solid rgba(212,129,58,0.15);
  border-radius: 12px; padding: 10px 14px; gap: 10px;
  transition: border-color 0.25s;
}
#inp-box:focus-within { border-color: rgba(212,129,58,0.4); }
#msg {
  flex: 1; background: none; border: none; outline: none;
  color: var(--text); font-size: 15px;
  font-family: 'PT Serif', serif; resize: none; max-height: 100px; line-height: 1.5;
}
#msg::placeholder { color: rgba(232,213,176,0.18); font-style: italic; }
#send {
  background: none; border: none; color: var(--orange);
  cursor: pointer; flex-shrink: 0; padding: 4px;
  transition: all 0.2s; opacity: 0.55;
}
#send:hover { opacity: 1; transform: scale(1.1); }
#send:disabled { opacity: 0.18; cursor: default; transform: none; }

/* Быстрые кнопки */
.abtns { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.abtn {
  background: rgba(212,129,58,0.06);
  border: 0.5px solid rgba(212,129,58,0.18);
  border-radius: 20px;
  color: rgba(232,213,176,0.45); font-size: 11px;
  font-family: 'Russo One', sans-serif; cursor: pointer;
  transition: all 0.2s; letter-spacing: 1px; text-transform: uppercase;
  padding: 6px 14px;
}
.abtn:hover { color: var(--orange); border-color: rgba(212,129,58,0.4); background: var(--orange-glow); }
.abtn-rage { border-color: rgba(180,40,40,0.3); color: rgba(220,80,80,0.6); }
.abtn-rage:hover { color: #e05555; border-color: rgba(200,50,50,0.5); background: rgba(180,40,40,0.1); }

/* OVERLAY */
.ov { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.ov.show { display: flex; }
.pop {
  background: rgba(10,7,2,0.97); backdrop-filter: blur(24px);
  border: 0.5px solid rgba(212,129,58,0.18);
  border-radius: 16px; padding: 26px; width: 90%; max-width: 360px;
}
.pop h3 { font-family: 'Russo One', sans-serif; color: var(--orange); font-size: 12px; letter-spacing: 3px; margin-bottom: 16px; text-transform: uppercase; }
.pop p { color: rgba(232,213,176,0.45); font-size: 13px; margin-bottom: 14px; line-height: 1.7; font-style: italic; }
.pop input, .pop textarea {
  width: 100%; background: rgba(255,255,255,0.04);
  color: var(--text); border: 0.5px solid rgba(212,129,58,0.2);
  border-radius: 8px; padding: 11px 14px; font-size: 14px;
  font-family: 'PT Serif', serif; margin-bottom: 12px; outline: none;
}
.pop input:focus, .pop textarea:focus { border-color: rgba(212,129,58,0.45); }
.pbts { display: flex; gap: 8px; }
.pbts button { flex: 1; padding: 10px; border-radius: 8px; border: none; font-size: 11px; font-family: 'Russo One', sans-serif; cursor: pointer; letter-spacing: 1px; text-transform: uppercase; }
.bok { background: rgba(212,129,58,0.85); color: #0c0700; }
.bok:hover { background: var(--orange); }
.bno { background: rgba(255,255,255,0.04); color: rgba(232,213,176,0.5); border: 0.5px solid rgba(255,255,255,0.09) !important; }

/* TOAST */
#toast {
  position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
  background: rgba(212,129,58,0.9); color: #0c0700;
  padding: 7px 18px; border-radius: 20px; font-size: 10px;
  font-family: 'Russo One', sans-serif; letter-spacing: 2px; text-transform: uppercase;
  opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 200;
}
#toast.show { opacity: 1; }

/* MODE MENU */
#mode-ov { display: none; position: fixed; inset: 0; z-index: 998; background: rgba(0,0,0,0.6); backdrop-filter: blur(3px); }
#mode-menu {
  display: none; position: fixed; left: 12px; right: 12px; bottom: 12px;
  z-index: 999; background: rgba(10,7,2,0.97);
  backdrop-filter: blur(28px);
  border: 0.5px solid rgba(212,129,58,0.18);
  border-radius: 16px; overflow: hidden;
}
#mode-menu-title {
  padding: 14px 20px 10px; font-family: 'Russo One', sans-serif; font-size: 10px;
  letter-spacing: 3px; color: rgba(212,129,58,0.4); text-transform: uppercase;
  text-align: center; border-bottom: 0.5px solid rgba(255,255,255,0.06);
}
.mrow {
  padding: 16px 20px; font-family: 'PT Serif', serif; font-size: 17px;
  color: rgba(232,213,176,0.75); cursor: pointer;
  border-bottom: 0.5px solid rgba(255,255,255,0.05);
  transition: all 0.15s; text-align: center;
}
.mrow:active { background: var(--orange-glow); }
.mrow.active-row { color: var(--orange); font-style: italic; }
#mode-cancel {
  padding: 15px 20px; font-family: 'Russo One', sans-serif; font-size: 10px;
  letter-spacing: 2px; color: rgba(232,213,176,0.3); cursor: pointer;
  text-align: center; text-transform: uppercase; transition: color 0.15s;
}
#mode-cancel:hover { color: rgba(232,213,176,0.6); }

#sov { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 9; }

@media (max-width: 620px) {
  #sidebar { position: fixed; top: 0; left: 0; bottom: 0; transform: translateX(-100%); z-index: 20; }
  #sidebar.open { transform: translateX(0); }
  #sov.show { display: block; }
  #menu-btn { display: block; }
}

/* Скроллбар */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(212,129,58,0.2); border-radius: 2px; }
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div id="sidebar-head">
    <span>РАЗГОВОРЫ</span>
    <button id="btn-new" onclick="newChat()" title="Новый разговор">+</button>
  </div>
  <div id="chats-list"></div>
  <div id="sidebar-foot">
    <a href="#" onclick="doSummary()">📜 Итог деда</a>
    <a href="#" onclick="showOv('ov-key')">🔑 API ключ</a>
    <a href="/admin?p=1234">⚙ Настройки</a>
  </div>
</div>

<div id="sov" onclick="closeSide()"></div>

<!-- MAIN -->
<div id="main">
  <div id="hdr">
    <button id="menu-btn" onclick="toggleSide()">☰</button>
    <div id="hdr-logo">
      <div id="ded-avatar">👴</div>
      <div>
        <div id="hdr-title-text">ПОШЛЫЙ ДЕД</div>
        <div id="hdr-sub">грубо. коротко. по делу.</div>
      </div>
    </div>
    <button id="mode-btn" onclick="toggleModeMenu()">
      <span id="mode-label">⚖ Обычный</span>
    </button>
  </div>

  <div id="chat-wrap">
    <div id="chat"></div>
  </div>

  <div id="inp-area">
    <div id="inp-inner">
      <div id="inp-box">
        <textarea id="msg" placeholder="Спроси деда..." rows="1"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}"
          oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'"></textarea>
        <button id="send" onclick="sendMsg()">
          <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
          </svg>
        </button>
      </div>
      <div class="abtns">
        <button class="abtn" onclick="askSovet()">💬 Совет</button>
        <button class="abtn" onclick="askPredskazanie()">🔮 Предсказание</button>
        <button class="abtn" onclick="askPervyi()">👴 Дед говорит</button>
        <button class="abtn" onclick="doSummary()">📜 Итог</button>
        <button class="abtn abtn-rage" onclick="setMode('yarost');showToast('Дед унижает')">💀 Унижает</button>
      </div>
    </div>
  </div>
</div>

<!-- Overlays -->
<div id="ov-key" class="ov" onclick="if(event.target===this)closeOv('ov-key')">
  <div class="pop">
    <h3>API Ключ</h3>
    <p>Вставь новый ключ Groq если старый сдох.</p>
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
    <textarea id="inp-edit" rows="3" placeholder="Напиши заново..."></textarea>
    <div class="pbts">
      <button class="bok" onclick="submitEdit()">Отправить</button>
      <button class="bno" onclick="closeOv('ov-edit')">Отмена</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const SID = "s_" + Math.random().toString(36).slice(2);
let CID = "c_" + Date.now();
let mode = "normal";
let topic = "";
let busy = false;

const chatEl = document.getElementById("chat");
const wrapEl = document.getElementById("chat-wrap");
const sendBtn = document.getElementById("send");

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2200);
}

function toggleSide() {
  document.getElementById("sidebar").classList.toggle("open");
  document.getElementById("sov").classList.toggle("show");
}
function closeSide() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sov").classList.remove("show");
}

async function loadChats() {
  try {
    const r = await fetch("/chats");
    const data = await r.json();
    const el = document.getElementById("chats-list");
    el.innerHTML = "";
    const ids = Object.keys(data).reverse();
    if (!ids.length) {
      el.innerHTML = '<div style="padding:12px;color:#3a2a14;font-size:13px;text-align:center">Нет разговоров</div>';
      return;
    }
    ids.forEach(id => {
      const d = document.createElement("div");
      d.className = "ci" + (id === CID ? " active" : "");
      d.innerHTML = '<span style="font-size:14px">💬</span><span class="ci-txt">' +
        escHtml(data[id].title || "Разговор") + '</span>' +
        '<span class="ci-del" onclick="delChat(event,\'' + id + '\')">✕</span>';
      d.onclick = () => openChat(id, data[id]);
      el.appendChild(d);
    });
  } catch(e) {}
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function delChat(e, id) {
  e.stopPropagation();
  await fetch("/chats/" + id, {method:"DELETE"});
  loadChats();
}

function openChat(id, data) {
  CID = id;
  chatEl.innerHTML = "";
  (data.messages || []).forEach(m => addBubble(m.content, m.role === "user", false));
  loadChats();
  closeSide();
}

function newChat() {
  CID = "c_" + Date.now();
  chatEl.innerHTML = "";
  showWelcome();
  fetch("/clear", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({session_id:SID})});
  loadChats();
  closeSide();
}

function showWelcome() {
  const w = document.createElement("div");
  w.id = "welcome";
  w.innerHTML = `
    <div id="welcome-avatar">👴</div>
    <h1>ПОШЛЫЙ ДЕД</h1>
    <p>Чё надо? Говори, не тяни. Спина болит, времени нет.</p>
    <div class="qbtns">
      <button class="qbtn" onclick="askSovet()">
        <span class="qbtn-icon">💬</span>Попросить совет
      </button>
      <button class="qbtn" onclick="askPredskazanie()">
        <span class="qbtn-icon">🔮</span>Предсказание на сегодня
      </button>
      <button class="qbtn" onclick="askPervyi()">
        <span class="qbtn-icon">👴</span>Пусть дед сам начнёт
      </button>
      <button class="qbtn qbtn-rage" onclick="setMode('yarost');qs('Привет дед')">
        <span class="qbtn-icon">💀</span>Дед унижает
      </button>
    </div>`;
  chatEl.appendChild(w);
}

function askSovet() {
  mode = "sovet";
  updateModeLabel();
  const w = document.getElementById("welcome");
  if (w) { w.remove(); }
  document.getElementById("msg").placeholder = "О чём нужен совет деда?";
  document.getElementById("msg").focus();
  showToast("Режим: Совет");
}

function askPredskazanie() {
  mode = "predskazanie";
  updateModeLabel();
  qs("Дед, дай предсказание на сегодня");
}

function askPervyi() {
  mode = "pervyi";
  updateModeLabel();
  qs("Начни разговор сам");
}

function updateModeLabel() {
  const names = {
    "normal": "👴 Обычный",
    "yarost": "💀 Унижает",
    "sovet": "💬 Совет",
    "predskazanie": "🔮 Предсказание",
    "pervyi": "👴 Дед говорит",
  };
  const lbl = document.getElementById("mode-label");
  if (lbl) lbl.textContent = names[mode] || mode;
}

function toggleModeMenu() {
  const menu = document.getElementById("mode-menu");
  const ov = document.getElementById("mode-ov");
  const show = menu.style.display === "none" || menu.style.display === "";
  menu.style.display = show ? "block" : "none";
  ov.style.display = show ? "block" : "none";
}

function setMode(m) {
  mode = m;
  document.getElementById("mode-menu").style.display = "none";
  document.getElementById("mode-ov").style.display = "none";
  document.querySelectorAll(".mrow").forEach(b => b.classList.remove("active-row"));
  const opt = document.getElementById("opt-" + m);
  if (opt) opt.classList.add("active-row");
  updateModeLabel();
  const names = {"normal":"Обычный дед", "yarost":"Дед унижает", "sovet":"Совет", "predskazanie":"Предсказание", "pervyi":"Дед говорит"};
  showToast("Режим: " + (names[m] || m));
}

function addBubble(text, isUser, animate=true) {
  const w = document.getElementById("welcome");
  if (w) w.remove();
  const div = document.createElement("div");
  div.className = "bubble " + (isUser ? "user" : "bot");
  if (!animate) div.style.animation = "none";
  const who = document.createElement("div");
  who.className = "bwho";
  who.textContent = isUser ? "ТЫ" : "ДЕД";
  const txt = document.createElement("div");
  txt.className = "btxt";
  txt.textContent = text;
  const meta = document.createElement("div");
  meta.className = "bmeta";
  if (!isUser) {
    meta.innerHTML = '<button class="bmeta-btn" onclick="doCopy(this)" title="Копировать">⎘</button>' +
                     '<button class="bmeta-btn" onclick="doRetry()" title="Ещё раз">↺</button>';
  } else {
    meta.innerHTML = '<button class="bmeta-btn" onclick="openEditWith(\'' + escJs(text) + '\')" title="Изменить">✎</button>';
  }
  div.appendChild(who);
  div.appendChild(txt);
  div.appendChild(meta);
  chatEl.appendChild(div);
  wrapEl.scrollTop = wrapEl.scrollHeight;
}

function escJs(s) { return s.replace(/\\/g,"\\\\").replace(/'/g,"\\'").replace(/\n/g,"\\n"); }

function doCopy(btn) {
  const txt = btn.closest(".bubble").querySelector(".btxt").textContent;
  navigator.clipboard.writeText(txt);
  showToast("Скопировано");
}

function showTyping() {
  const d = document.createElement("div");
  d.className = "bubble bot";
  d.id = "typing";
  d.style.animation = "none";
  d.innerHTML = '<div class="bwho">ДЕД</div><div class="tdots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
  chatEl.appendChild(d);
  wrapEl.scrollTop = wrapEl.scrollHeight;
}

function removeTyping() {
  const t = document.getElementById("typing");
  if (t) t.remove();
}

function setBusy(v) {
  busy = v;
  sendBtn.disabled = v;
}

function qs(text) {
  const w = document.getElementById("welcome");
  if (w) w.remove();
  addBubble(text, true);
  sendToServer(text);
}

async function sendMsg() {
  if (busy) return;
  const inp = document.getElementById("msg");
  const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
  inp.style.height = "auto";
  addBubble(text, true);
  sendToServer(text);
}

async function sendToServer(text) {
  setBusy(true);
  showTyping();
  try {
    const r = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: SID, message: text, mode, topic, chat_id: CID})
    });
    removeTyping();
    const d = await r.json();
    if (d.error === "invalid_key") {
      showOv("ov-key");
    } else {
      addBubble(d.reply || "Хуй знает что сказать.", false);
    }
  } catch(e) { removeTyping(); addBubble("Связь упала. Попробуй ещё раз.", false); }
  setBusy(false);
  // Сбрасываем режим после предсказания/первого
  if (mode === "predskazanie" || mode === "pervyi") {
    mode = "normal";
    updateModeLabel();
  }
}

async function doRetry() {
  if (busy) return;
  const allBubbles = chatEl.querySelectorAll(".bubble");
  const arr = Array.from(allBubbles);
  for (let i = arr.length - 1; i >= 0; i--) {
    const el = arr[i];
    if (el.id === "typing") continue;
    el.remove();
    if (el.classList.contains("bot")) break;
  }
  setBusy(true);
  showTyping();
  try {
    const r = await fetch("/retry", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: SID, mode, topic, chat_id: CID})
    });
    removeTyping();
    const d = await r.json();
    addBubble(d.reply || "Нечего повторять.", false);
  } catch(e) { removeTyping(); }
  setBusy(false);
}

async function doSummary() {
  closeSide();
  setBusy(true);
  showTyping();
  try {
    const r = await fetch("/summary", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: SID})
    });
    removeTyping();
    const d = await r.json();
    addBubble(d.reply, false);
  } catch(e) { removeTyping(); }
  setBusy(false);
}

function openEditWith(text) {
  document.getElementById("inp-edit").value = text;
  showOv("ov-edit");
}

async function submitEdit() {
  const text = document.getElementById("inp-edit").value.trim();
  if (!text) return;
  closeOv("ov-edit");
  const allBubbles = chatEl.querySelectorAll(".bubble");
  const arr = Array.from(allBubbles);
  for (let i = arr.length - 1; i >= 0; i--) {
    arr[i].remove();
    if (arr[i].classList.contains("user")) break;
  }
  addBubble(text, true);
  sendToServer(text);
}

async function saveKey() {
  const key = document.getElementById("inp-key").value.trim();
  if (!key) return;
  await fetch("/update_key", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({key})});
  closeOv("ov-key");
  addBubble("Ключ обновлён. Пиши.", false);
}

function shareChat() {
  closeSide();
  const url = window.location.origin + "/share/" + CID;
  if (navigator.share) {
    navigator.share({title: "Разговор с Дедом", url: url});
  } else {
    navigator.clipboard.writeText(url);
    showToast("Ссылка скопирована!");
  }
}

function showOv(id) { document.getElementById(id).classList.add("show"); }
function closeOv(id) { document.getElementById(id).classList.remove("show"); }

loadChats();
showWelcome();
</script>

<!-- OVERLAY MODE-OV -->
<div id="mode-ov" onclick="toggleModeMenu()" style="display:none;position:fixed;inset:0;z-index:998;background:rgba(0,0,0,0.6)"></div>
<div id="mode-menu" style="display:none;position:fixed;left:0;right:0;bottom:0;z-index:999;background:rgba(10,7,2,0.98);border-top:1px solid rgba(212,129,58,0.2);border-radius:20px 20px 0 0;padding:8px 0 20px">
  <div id="mode-menu-title">РЕЖИМ</div>
  <div class="mrow" id="opt-normal" onclick="setMode('normal')">👴 Обычный дед</div>
  <div class="mrow" id="opt-yarost" onclick="setMode('yarost')">💀 Дед унижает</div>
  <div id="mode-cancel" onclick="toggleModeMenu()">Отмена</div>
</div>

</body>
</html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
