import os
import random
import time
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Получаем список бравлеров из папки
def get_brawlers_list():
    image_folder = os.path.join(app.static_folder, 'brawler_images')
    brawlers = []
    
    if os.path.exists(image_folder):
        for filename in os.listdir(image_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                name = os.path.splitext(filename)[0]
                brawlers.append(name)
    
    print(f"✅ Найдено бравлеров: {len(brawlers)}")
    return sorted(brawlers, key=lambda x: x.lower())

BRWLERS = get_brawlers_list()

# Состояние драфта
class DraftState:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.blue_bans = []
        self.red_bans = []
        self.blue_picks = []
        self.red_picks = []
        self.all_selected = []
        self.phase = "waiting"  # waiting, ban_blue, ban_red, pick, finished
        self.current_turn = None
        self.picking_team = None
        self.pick_order = []
        self.current_pick_index = 0
        self.finished_time = None
    
    def initialize_pick_order(self):
        """Инициализирует порядок пиков"""
        if self.picking_team == "blue":
            # Порядок: blue, red, red, blue, blue, red
            self.pick_order = ["blue", "red", "red", "blue", "blue", "red"]
        else:
            # Порядок: red, blue, blue, red, red, blue
            self.pick_order = ["red", "blue", "blue", "red", "red", "blue"]
    
    def get_state_for_team(self, team):
        """Возвращает состояние для конкретной команды"""
        state = {
            "blue_bans": self.blue_bans.copy(),
            "red_bans": self.red_bans.copy(),
            "blue_picks": self.blue_picks.copy(),
            "red_picks": self.red_picks.copy(),
            "all_selected": self.all_selected.copy(),
            "phase": self.phase,
            "current_turn": self.current_turn,
            "picking_team": self.picking_team,
            "pick_order": self.pick_order.copy(),
            "current_pick_index": self.current_pick_index,
        }
        
        # Скрываем баны противника в фазе банов
        if "ban" in self.phase and team:
            if team == "blue":
                state["red_bans"] = ["hidden"] * len(self.red_bans)
            elif team == "red":
                state["blue_bans"] = ["hidden"] * len(self.blue_bans)
        
        return state

draft_state = DraftState()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok', 
        'brawlers': len(BRWLERS),
        'phase': draft_state.phase
    })

@app.route('/api/brawlers')
def api_brawlers():
    return jsonify(BRWLERS)

@app.route('/api/draft-state')
def api_draft_state():
    return jsonify(draft_state.get_state_for_team("spectator"))

@socketio.on('connect')
def handle_connect():
    print('🔌 Новое подключение')
    emit('brawlers_list', BRWLERS)
    emit('update_draft', draft_state.get_state_for_team("spectator"))

@socketio.on('join')
def handle_join(data):
    team = data.get('team', 'spectator')
    print(f'👤 Игрок присоединился к команде: {team}')
    
    # Отправляем состояние для этой команды
    state = draft_state.get_state_for_team(team)
    emit('update_draft', state)

@socketio.on('start_draft')
def handle_start_draft():
    print("🚀 Начало драфта")
    draft_state.reset()
    draft_state.phase = "ban_blue"
    draft_state.current_turn = "blue"
    broadcast_state()

@socketio.on('select_brawler')
def handle_select_brawler(data):
    brawler = data.get('brawler', '').strip()
    team = data.get('team', '')
    
    if not brawler or not team or team not in ['blue', 'red']:
        return
    
    if brawler not in BRWLERS:
        return
    
    # Проверяем, можно ли выбрать этого бравлера
    if brawler in draft_state.all_selected:
        return
    
    # Фаза банов
    if "ban" in draft_state.phase:
        # Проверяем, чей сейчас ход
        expected_team = draft_state.current_turn
        if team != expected_team:
            return
        
        # Добавляем бан
        if team == "blue":
            if len(draft_state.blue_bans) < 3:
                draft_state.blue_bans.append(brawler)
            else:
                return
        else:  # red
            if len(draft_state.red_bans) < 3:
                draft_state.red_bans.append(brawler)
            else:
                return
        
        draft_state.all_selected.append(brawler)
        
        # Проверяем, завершены ли все баны
        blue_bans_done = len(draft_state.blue_bans) == 3
        red_bans_done = len(draft_state.red_bans) == 3
        
        if blue_bans_done and red_bans_done:
            # Все баны сделаны - переходим к пикам
            draft_state.picking_team = random.choice(["blue", "red"])
            draft_state.initialize_pick_order()
            draft_state.phase = "pick"
            draft_state.current_turn = draft_state.pick_order[0]
            draft_state.current_pick_index = 0
            print(f"🎲 Первый пик у команды: {draft_state.picking_team}")
        elif draft_state.phase == "ban_blue" and blue_bans_done:
            # Синие сделали баны, переходим к красным
            draft_state.phase = "ban_red"
            draft_state.current_turn = "red"
        elif draft_state.phase == "ban_red" and red_bans_done:
            # Красные сделали баны, переходим к синим
            draft_state.phase = "ban_blue"
            draft_state.current_turn = "blue"
    
    # Фаза пиков
    elif draft_state.phase == "pick":
        # Проверяем, чей сейчас ход
        expected_team = draft_state.current_turn
        if team != expected_team:
            return
        
        # Добавляем пик
        if team == "blue":
            if len(draft_state.blue_picks) < 3:
                draft_state.blue_picks.append(brawler)
            else:
                return
        else:  # red
            if len(draft_state.red_picks) < 3:
                draft_state.red_picks.append(brawler)
            else:
                return
        
        draft_state.all_selected.append(brawler)
        
        # Переходим к следующему пику
        draft_state.current_pick_index += 1
        
        # Проверяем, завершен ли драфт
        if len(draft_state.blue_picks) == 3 and len(draft_state.red_picks) == 3:
            draft_state.phase = "finished"
            draft_state.finished_time = time.time()
            print("🏁 Драфт завершен!")
        elif draft_state.current_pick_index < len(draft_state.pick_order):
            draft_state.current_turn = draft_state.pick_order[draft_state.current_pick_index]
        else:
            draft_state.phase = "finished"
            draft_state.finished_time = time.time()
    
    broadcast_state()

@socketio.on('reset_draft')
def handle_reset_draft():
    print("🔄 Сброс драфта")
    draft_state.reset()
    broadcast_state()
    emit("draft_reset", broadcast=True)

def broadcast_state():
    """Отправляет состояние всем подключенным клиентам"""
    for team in ["blue", "red", "spectator"]:
        state = draft_state.get_state_for_team(team)
        emit('update_draft', state, broadcast=True)

# Простая проверка на автосброс
def check_auto_reset():
    """Проверяет, нужно ли сбросить драфт"""
    if draft_state.phase == "finished" and draft_state.finished_time:
        elapsed = time.time() - draft_state.finished_time
        if elapsed > 60:  # 60 секунд
            print("⏰ Автоматический сброс через 1 минуту")
            draft_state.reset()
            broadcast_state()
            emit("draft_reset", broadcast=True)
            return True
    return False

# Простой таймер для проверки автосброса
import atexit
from threading import Thread
from time import sleep

def auto_reset_thread():
    """Фоновый поток для проверки автосброса"""
    while True:
        sleep(5)  # Проверяем каждые 5 секунд
        check_auto_reset()

# Запускаем фоновый поток
thread = Thread(target=auto_reset_thread, daemon=True)
thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Сервер запущен на порту {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
