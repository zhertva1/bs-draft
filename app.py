import os
import random
import time
import threading
from flask import Flask, render_template, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Инициализация Flask
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = os.urandom(24)
CORS(app)  # Разрешаем CORS для всех доменов
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Конфигурация
IMAGE_FOLDER = os.path.join(app.static_folder, 'brawler_images')
RESET_TIMEOUT = 60  # 1 минута в секундах

# Получаем список бравлеров из папки
def get_brawlers_list():
    if not os.path.exists(IMAGE_FOLDER):
        print(f"⚠️ Папка '{IMAGE_FOLDER}' не найдена!")
        return []
    
    brawlers = []
    for filename in os.listdir(IMAGE_FOLDER):
        # Принимаем разные расширения изображений
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            name = os.path.splitext(filename)[0]  # Убираем расширение
            brawlers.append(name)
    
    print(f"✅ Найдено бравлеров: {len(brawlers)}")
    return sorted(brawlers, key=lambda x: x.lower())

BRWLERS = get_brawlers_list()
print(f"📋 Список бравлеров: {BRWLERS[:5]}...")

# Глобальное состояние драфта
class DraftState:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.blue_bans = []
        self.blue_picks = []
        self.red_bans = []
        self.red_picks = []
        self.all_selected = []
        self.phase = 'waiting'  # waiting, ban, pick, finished
        self.picking_order = ['blue', 'red']
        self.turn_index = 0
        self.last_action_time = None
        self.lock = threading.Lock()
    
    def get_state(self):
        with self.lock:
            return {
                'blue_bans': self.blue_bans,
                'blue_picks': self.blue_picks,
                'red_bans': self.red_bans,
                'red_picks': self.red_picks,
                'all_selected': self.all_selected,
                'phase': self.phase,
                'picking_order': self.picking_order,
                'turn_index': self.turn_index
            }

draft_state = DraftState()

# Функция для проверки и сброса таймера
def check_reset_timer():
    while True:
        time.sleep(5)  # Проверяем каждые 5 секунд
        
        if draft_state.phase == 'finished' and draft_state.last_action_time:
            elapsed = time.time() - draft_state.last_action_time
            
            if elapsed >= RESET_TIMEOUT:
                print("⏰ Автоматический сброс драфта через 1 минуту")
                draft_state.reset()
                socketio.emit('draft_reset')
                socketio.emit('update_draft', draft_state.get_state())

# Запускаем таймер в отдельном потоке
timer_thread = threading.Thread(target=check_reset_timer, daemon=True)
timer_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/brawlers')
def api_brawlers():
    return jsonify(BRWLERS)

@app.route('/api/draft-state')
def api_draft_state():
    return jsonify(draft_state.get_state())

@socketio.on('connect')
def handle_connect():
    print('🔌 Клиент подключился')
    emit('brawlers_list', BRWLERS)
    emit('update_draft', draft_state.get_state())

@socketio.on('join')
def handle_join(data):
    team = data.get('team', 'spectator')
    print(f'👤 Игрок присоединился к команде: {team}')
    emit('update_draft', draft_state.get_state())

@socketio.on('select_brawler')
def handle_select(data):
    brawler = data.get('brawler', '').strip()
    team = data.get('team', '')
    
    if not brawler or not team or team not in ['blue', 'red']:
        print(f"❌ Неверные данные: brawler={brawler}, team={team}")
        return
    
    if brawler not in BRWLERS:
        print(f"❌ Бравлер {brawler} не найден в списке")
        return
    
    with draft_state.lock:
        if brawler in draft_state.all_selected:
            print(f"⚠️ Бравлер {brawler} уже выбран")
            return
        
        # Определяем, бан это или пик
        if team == 'blue':
            if len(draft_state.blue_bans) < 3:
                draft_state.blue_bans.append(brawler)
                draft_state.phase = 'ban'
            elif len(draft_state.blue_picks) < 3:
                draft_state.blue_picks.append(brawler)
                draft_state.phase = 'pick'
        else:  # red
            if len(draft_state.red_bans) < 3:
                draft_state.red_bans.append(brawler)
                draft_state.phase = 'ban'
            elif len(draft_state.red_picks) < 3:
                draft_state.red_picks.append(brawler)
                draft_state.phase = 'pick'
        
        draft_state.all_selected.append(brawler)
        draft_state.last_action_time = time.time()
        
        # Проверяем, завершен ли драфт
        if (len(draft_state.blue_picks) == 3 and 
            len(draft_state.red_picks) == 3):
            draft_state.phase = 'finished'
            draft_state.last_action_time = time.time()
    
    print(f"✅ Выбран бравлер: {brawler} для команды {team}")
    socketio.emit('update_draft', draft_state.get_state())

@socketio.on('reset_draft')
def handle_reset():
    print("🔄 Ручной сброс драфта")
    draft_state.reset()
    socketio.emit('draft_reset')
    socketio.emit('update_draft', draft_state.get_state())

@socketio.on('get_state')
def handle_get_state():
    emit('update_draft', draft_state.get_state())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Сервер запущен на порту {port}")
    print(f"📊 Доступно бравлеров: {len(BRWLERS)}")
    print(f"🌐 Ссылки для доступа:")
    print(f"   Синяя команда: http://localhost:{port}/?team=blue")
    print(f"   Красная команда: http://localhost:{port}/?team=red")
    print(f"   Наблюдатель: http://localhost:{port}/")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
