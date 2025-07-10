import os
import json
from datetime import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import google.generativeai as genai
# import base64 # 画像処理はクライアント側で行うため、サーバーでは不要

# --- Flask, SocketIO, CORS の初期化 ---
app = Flask(__name__, static_folder='static', template_folder='templates')
# GitHub Pagesからのアクセスを許可するためにCORSを設定
CORS(app, resources={r"/*": {"origins": "*"}}) 
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 設定 (変更なし) ---
CHAT_LOG_FILE = "chat_log.json"

# --- Gemini API 設定 (変更なし) ---
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("[WARNING] 環境変数 'GEMINI_API_KEY' が設定されていません。AI機能は利用できません。")
        GEMINI_API_KEY = None
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("[INFO] Gemini APIの準備が完了しました。")
except Exception as e:
    print(f"[ERROR] Gemini APIの初期化に失敗しました: {e}")
    GEMINI_API_KEY = None

# --- グローバル変数 ---
board_messages = []
# 接続中のクライアントとユーザー名を管理する辞書
# { 'セッションID': 'ユーザー名' }
connected_users = {}

# --- チャットロジック (変更なし、ただし関数呼び出し箇所は調整) ---
def call_gemini_api(history, user_prompt):
    if not GEMINI_API_KEY: return "AI機能が設定されていません。"
    prompt_history_list = []
    # 履歴からテキストメッセージのみを抽出
    for msg in filter(lambda m: "message" in m and m.get("message"), history[-20:]):
        if len(prompt_history_list) >= 10: break
        prompt_history_list.append(f"{msg.get('username', 'Unknown')}: {msg['message']}")
    
    prompt_history = "\n".join(reversed(prompt_history_list))
    final_prompt = (
        "あなたはチャットを支援する、賢くてフレンドリーなAIアシスタントです。\n"
        "以下のチャット履歴とユーザーからの指示を考慮して、回答を生成してください。\n"
        "チャットの参加者のように、自然な言葉で応答してください。\n\n"
        "--- 直近のチャット履歴 ---\n"
        f"{prompt_history}\n"
        "--- ここまで ---\n\n"
        "--- ユーザーからの指示 ---\n"
        f"{user_prompt}\n"
        "--- ここまで ---\n\n"
        "AIアシスタントとしてのあなたの回答:"
    )
    try:
        response = model.generate_content(final_prompt)
        return response.text
    except Exception as e:
        print(f"[ERROR] Gemini APIの呼び出しでエラーが発生しました: {e}")
        return "AIアシスタントの呼び出し中にエラーが発生しました。"

def load_chat_log():
    if not os.path.exists(CHAT_LOG_FILE): return []
    try:
        with open(CHAT_LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, IOError): return []

def save_chat_log():
    try:
        with open(CHAT_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(board_messages, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[ERROR] チャットログの保存に失敗しました: {e}")

# --- クライアント(HTML)を配信するルート ---
@app.route('/')
def index():
    # templatesフォルダ内のindex.htmlを返す
    return render_template('index.html')

# --- SocketIO イベントハンドラ ---
@socketio.on('connect')
def handle_connect():
    """クライアント接続時の処理"""
    print(f"[INFO] 新しいクライアントが接続しました: {request.sid}")
    # 接続してきたクライアントにだけ、現在の掲示板情報を送信
    emit('BoardInfo', {'payload': board_messages})

@socketio.on('disconnect')
def handle_disconnect():
    """クライアント切断時の処理"""
    username = connected_users.pop(request.sid, "Anonymous")
    print(f"[INFO] {username} ({request.sid}) が切断されました。")
    server_msg = {"username": "Server", "message": f"{username} が退出しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    board_messages.append(server_msg)
    save_chat_log()
    # 全員に更新情報をブロードキャスト
    emit('BoardInfo', {'payload': board_messages}, broadcast=True)

@socketio.on('SendMessage')
def handle_message(data):
    """テキストメッセージ受信処理"""
    username = data.get('username', 'Anonymous')
    message = data.get('message')
    print(f"[MESSAGE] {username}: {message}")
    
    msg_data = {"username": username, "message": message, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    board_messages.append(msg_data)
    save_chat_log()
    emit('BoardInfo', {'payload': board_messages}, broadcast=True)

@socketio.on('SendImage')
def handle_image(data):
    """画像受信処理"""
    username = data.get('username', 'Anonymous')
    image_data_b64 = data.get('image_data') # Base64エンコードされた画像データ
    print(f"[IMAGE] {username} が画像を送信しました。")
    
    msg_data = {"username": username, "image_data": image_data_b64, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    board_messages.append(msg_data)
    save_chat_log()
    emit('BoardInfo', {'payload': board_messages}, broadcast=True)

@socketio.on('SetUsername')
def handle_set_username(data):
    """ユーザー名設定処理"""
    username = data.get('username')
    connected_users[request.sid] = username
    print(f"[INFO] ユーザー名を設定: {username} ({request.sid})")
    
    server_msg = {"username": "Server", "message": f"{username} が参加しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    board_messages.append(server_msg)
    save_chat_log()
    emit('BoardInfo', {'payload': board_messages}, broadcast=True)

@socketio.on('RequestAI')
def handle_ai_request(data):
    """AI応答生成処理"""
    username = data.get('username', 'Anonymous')
    prompt = data.get('prompt')
    print(f"[AI] {username} がAIを呼び出しました。プロンプト: '{prompt}'")
    
    ai_response = call_gemini_api(board_messages, user_prompt=prompt)
    ai_message = {"username": "AI Assistant", "message": ai_response, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    board_messages.append(ai_message)
    save_chat_log()
    emit('BoardInfo', {'payload': board_messages}, broadcast=True)

# --- サーバー起動 ---
if __name__ == '__main__':
    board_messages = load_chat_log()
    print(f"[INFO] 過去のチャットログを {len(board_messages)} 件読み込みました。")
    print("[INFO] サーバーを起動します。 http://0.0.0.0:5000")
    # eventletを使う場合、socketio.run()で起動
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)