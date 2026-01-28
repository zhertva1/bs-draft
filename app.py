import os
import random
import time
import threading
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Получаем список бравлеров из папки
def get_brawlers_list():
    image_folder = os.path.join(app.static_folder, 'brawler_images')
    brawlers = []
    
    if os.path.exists(image_folder):
        for filename in os.listdir(image_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                name = os.path.splitext(filename)[0]
                brawlers.append(name)
    
    return sorted(brawlers)

BRWLERS = get_brawlers_list()
print(f"✅ Найдено бравлеров: {len(BRWLERS)}")

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
        self.picking_team = None  # Какая команда начинает пики
        self.pick_order = []
        self.current_pick_index = 0
        self.last_action_time = time.time()
        self.lock = threading.Lock()
    
    def initialize_pick_order(self):
        """Инициализирует порядок пиков"""
        if self.picking_team == "blue":
            # Порядок: blue, red, red, blue, blue, red
            self.pick_order = ["blue", "red", "red", "blue", "blue", "red"]
        else:
            # Порядок: red, blue, blue, red, red, blue
            self.pick_order = ["red", "blue", "blue", "red", "red", "blue"]
    
    def get_state_for_team(self, team):
        """Возвращает состояние для конкретной команды (скрывая баны противника)"""
        with self.lock:
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
                "total_bans": len(self.blue_bans) + len(self.red_bans),
                "total_picks": len(self.blue_picks) + len(self.red_picks),
            }
            
            # Скрываем баны противника в фазе банов
            if "ban" in self.phase and team:
                if team == "blue":
                    state["red_bans"] = ["hidden"] * len(self.red_bans)
                elif team == "red":
                    state["blue_bans"] = ["hidden"] * len(self.blue_bans)
            
            return state

draft_state = DraftState()

# Таймер для сброса через 1 минуту после завершения
def check_reset_timer():
    while True:
        time.sleep(5)
        if draft_state.phase == "finished":
            elapsed = time.time() - draft_state.last_action_time
            if elapsed > 60:  # 60 секунд
                print("⏰ Автоматический сброс через 1 минуту")
                draft_state.reset()
                broadcast_state()
                socketio.emit("draft_reset")

timer_thread = threading.Thread(target=check_reset_timer, daemon=True)
timer_thread.start()

def broadcast_state():
    """Отправляет состояние всем подключенным клиентам"""
    for team in ["blue", "red", "spectator"]:
        state = draft_state.get_state_for_team(team)
        socketio.emit("update_draft", state, room=team)

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

@socketio.on('connect')
def handle_connect():
    print('🔌 Новое подключение')

@socketio.on('join')
def handle_join(data):
    team = data.get('team', 'spectator')
    print(f'👤 Игрок присоединился к команде: {team}')
    
    # Привязываем socket к комнате команды
    socketio.emit('set_team', {'team': team})
    
    # Отправляем список бравлеров
    emit('brawlers_list', BRWLERS)
    
    # Отправляем состояние для этой команды
    state = draft_state.get_state_for_team(team)
    emit('update_draft', state)

@socketio.on('start_draft')
def handle_start_draft():
    print("🚀 Начало драфта")
    with draft_state.lock:
        draft_state.reset()
        draft_state.phase = "ban_blue"
        draft_state.current_turn = "blue"
        draft_state.last_action_time = time.time()
    broadcast_state()

@socketio.on('select_brawler')
def handle_select_brawler(data):
    brawler = data.get('brawler', '').strip()
    team = data.get('team', '')
    
    print(f"🎯 Попытка выбора: {brawler} командой {team}")
    
    if not brawler or not team or team not in ['blue', 'red']:
        print(f"❌ Неверные данные")
        return
    
    if brawler not in BRWLERS:
        print(f"❌ Бравлер не найден: {brawler}")
        return
    
    with draft_state.lock:
        # Проверяем, можно ли выбрать этого бравлера
        if brawler in draft_state.all_selected:
            print(f"❌ Бравлер уже выбран: {brawler}")
            return
        
        # Фаза банов
        if "ban" in draft_state.phase:
            # Проверяем, чей сейчас ход
            expected_team = draft_state.current_turn
            if team != expected_team:
                print(f"❌ Не ваша очередь. Ожидается: {expected_team}")
                return
            
            # Добавляем бан
            if team == "blue":
                if len(draft_state.blue_bans) < 3:
                    draft_state.blue_bans.append(brawler)
                else:
                    print("❌ Синяя команда уже сделала все баны")
                    return
            else:  # red
                if len(draft_state.red_bans) < 3:
                    draft_state.red_bans.append(brawler)
                else:
                    print("❌ Красная команда уже сделала все баны")
                    return
            
            draft_state.all_selected.append(brawler)
            draft_state.last_action_time = time.time()
            
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
                print(f"❌ Не ваша очередь. Ожидается: {expected_team}")
                return
            
            # Добавляем пик
            if team == "blue":
                if len(draft_state.blue_picks) < 3:
                    draft_state.blue_picks.append(brawler)
                else:
                    print("❌ Синяя команда уже сделала все пики")
                    return
            else:  # red
                if len(draft_state.red_picks) < 3:
                    draft_state.red_picks.append(brawler)
                else:
                    print("❌ Красная команда уже сделала все пики")
                    return
            
            draft_state.all_selected.append(brawler)
            draft_state.last_action_time = time.time()
            
            # Переходим к следующему пику
            draft_state.current_pick_index += 1
            
            # Проверяем, завершен ли драфт
            if len(draft_state.blue_picks) == 3 and len(draft_state.red_picks) == 3:
                draft_state.phase = "finished"
                print("🏁 Драфт завершен!")
            elif draft_state.current_pick_index < len(draft_state.pick_order):
                draft_state.current_turn = draft_state.pick_order[draft_state.current_pick_index]
            else:
                draft_state.phase = "finished"
                print("🏁 Драфт завершен!")
    
    print(f"✅ Успешный выбор: {brawler} командой {team}")
    broadcast_state()

@socketio.on('reset_draft')
def handle_reset_draft():
    print("🔄 Сброс драфта")
    with draft_state.lock:
        draft_state.reset()
    broadcast_state()
    socketio.emit("draft_reset")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Сервер запущен на порту {port}")
    socketio.run(app, host='0.0.0.0', port=port)
