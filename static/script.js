document.addEventListener('DOMContentLoaded', () => {
    // 接続画面の要素
    const connectionContainer = document.getElementById('connection-container');
    const serverIpInput = document.getElementById('server-ip-input');
    const usernameInput = document.getElementById('username-input');
    const connectBtn = document.getElementById('connect-btn');
    
    // チャット画面の要素
    const chatContainer = document.getElementById('chat-container');
    const chatBox = document.getElementById('chat-box');
    const msgInput = document.getElementById('msg-input');
    const sendBtn = document.getElementById('send-btn');
    const imageInput = document.getElementById('image-input-hidden');
    const aiBtn = document.getElementById('ai-btn');

    let socket;
    let currentUsername = "";

    // --- 接続処理 ---
    connectBtn.addEventListener('click', () => {
        const ip = serverIpInput.value.trim();
        const username = usernameInput.value.trim();

        if (!ip || !username) {
            alert("サーバーIPと名前の両方を入力してください。");
            return;
        }
        currentUsername = username;

        // Socket.IOでサーバーに接続
        socket = io(`http://10.101.223.218:5000`);
        
        // UIを切り替え
        connectionContainer.classList.add('hidden');
        chatContainer.classList.remove('hidden');

        setupSocketListeners();
    });
    
    // --- Socket.IOのイベントリスナーを設定 ---
    function setupSocketListeners() {
        // 接続成功時
        socket.on('connect', () => {
            console.log("サーバーに接続しました。");
            socket.emit('SetUsername', { username: currentUsername });
        });

        // サーバーから掲示板情報を受信したとき
        socket.on('BoardInfo', (data) => {
            renderChatHistory(data.payload);
        });

        // 接続が切れたとき
        socket.on('disconnect', () => {
            console.log("サーバーから切断されました。");
            addMessage({ username: "Server", message: "サーバーとの接続が切れました。" });
            // UIを接続画面に戻す
            chatContainer.classList.add('hidden');
            connectionContainer.classList.remove('hidden');
        });
    }

    // --- 画面描画ロジック (提供されたものをベース) ---
    const renderChatHistory = (messages) => {
        chatBox.innerHTML = ''; // チャットボックスをクリア
        messages.forEach(addMessage);
    };

    const addMessage = (msg) => {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message';

        let tag = 'other';
        if (msg.username === currentUsername) tag = 'me';
        else if (msg.username === 'Server') tag = 'server';
        else if (msg.username === 'AI Assistant') tag = 'ai';
        msgDiv.classList.add(tag);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        
        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'message-body';

        if (msg.image_data) {
            const img = document.createElement('img');
            img.src = `data:image/png;base64,${msg.image_data}`;
            bodyDiv.appendChild(img);
        } else {
            bodyDiv.textContent = msg.message;
        }

        const metaDiv = document.createElement('div');
        metaDiv.className = 'meta';
        const displayName = (tag === 'me' || tag === 'server') ? '' : msg.username;
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        metaDiv.textContent = `${displayName} ${timestamp}`.trim();

        contentDiv.appendChild(bodyDiv);
        msgDiv.appendChild(contentDiv);
        msgDiv.appendChild(metaDiv);
        chatBox.appendChild(msgDiv);

        chatBox.scrollTop = chatBox.scrollHeight; // 自動スクロール
    };

    // --- メッセージ送信ロジック ---
    function sendTextMessage() {
        const message = msgInput.value;
        if (message.trim() !== "" && socket && socket.connected) {
            socket.emit('SendMessage', { username: currentUsername, message: message });
            msgInput.value = '';
        }
    }

    sendBtn.addEventListener('click', sendTextMessage);
    msgInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendTextMessage();
    });

    imageInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file && socket && socket.connected) {
            const reader = new FileReader();
            reader.onload = (e) => {
                // Base64データのみを送信
                const base64Image = e.target.result.split(',')[1];
                socket.emit('SendImage', { username: currentUsername, image_data: base64Image });
            };
            reader.readAsDataURL(file);
        }
    });

    aiBtn.addEventListener('click', () => {
        const promptText = prompt("AIへの指示や質問を入力してください:");
        if (promptText && socket && socket.connected) {
            socket.emit('RequestAI', { username: currentUsername, prompt: promptText });
        }
    });
});