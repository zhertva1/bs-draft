import os
import random
import time
import uuid
from flask import Flask, render_template, jsonify, request, session, send_from_directory
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# Генерация админ-токена (в реальном приложении должен быть сложнее)
ADMIN_TOKEN = "admin_" + str(uuid.uuid4()).replace("-", "")[:16]
print(f"Admin URL: /admin/{ADMIN_TOKEN}")

# Получаем список бравлеров
def get_brawlers_list():
    image_folder = os.path.join(app.static_folder, 'brawler_images')
    brawlers = []
    
    if os.path.exists(image_folder):
        for filename in os.listdir(image_folder):
            if filename.lower().endswith('.png'):
                name = os.path.splitext(filename)[0]
                brawlers.append(name)
    
    return sorted(brawlers, key=lambda x: x.lower())

BRWLERS = get_brawlers_list()

# Получаем список карт по режимам
def get_maps_by_mode():
    maps = {}
    mappool_folder = os.path.join(app.static_folder, 'mappool')
    
    if os.path.exists(mappool_folder):
        for mode_folder in os.listdir(mappool_folder):
            mode_path = os.path.join(mappool_folder, mode_folder)
            if os.path.isdir(mode_path):
                maps[mode_folder] = []
                for map_file in os.listdir(mode_path):
                    if map_file.lower().endswith('.png'):
                        map_name = os.path.splitext(map_file)[0]
                        maps[mode_folder].append({
                            'name': map_name,
                            'file': map_file,
                            'mode': mode_folder
                        })
    return maps

MAPS_BY_MODE = get_maps_by_mode()

# Глобальное состояние драфта
draft_states = {}

# ID основной комнаты
MAIN_ROOM_ID = "main_room"

def get_or_create_state(room_id=MAIN_ROOM_ID):
    if room_id not in draft_states:
        draft_states[room_id] = {
            'blue_bans': [],
            'red_bans': [],
            'blue_picks': [],
            'red_picks': [],
            'all_selected': [],
            'phase': 'waiting',
            'current_turn': None,
            'picking_team': None,
            'pick_order': [],
            'current_pick_index': 0,
            'created_at': time.time(),
            'last_action': time.time(),
            'finished_at': None,
            'blue_ready': False,
            'red_ready': False,
            'selected_map': None,
            'selected_mode': None
        }
    
    return room_id, draft_states[room_id]

def check_auto_reset(state):
    """Проверяет, нужно ли сбросить драфт"""
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        if elapsed > 60:  # 60 секунд
            return True
    return False

def update_state(state, team, brawler, action_type):
    """Обновляет состояние драфта"""
    
    if brawler in state['all_selected']:
        return False, 'Бравлер уже выбран'
    
    if state['phase'] == 'waiting':
        return False, 'Ожидаем готовности обеих команд'
    
    if state['phase'] == 'finished':
        return False, 'Драфт уже завершен'
    
    # Фаза банов
    if 'ban' in state['phase']:
        if state['current_turn'] != team:
            return False, 'Не ваша очередь'
        
        if team == 'blue' and len(state['blue_bans']) < 3:
            state['blue_bans'].append(brawler)
        elif team == 'red' and len(state['red_bans']) < 3:
            state['red_bans'].append(brawler)
        else:
            return False, 'Все баны уже сделаны'
        
        state['all_selected'].append(brawler)
        state['last_action'] = time.time()
        
        # Проверяем, завершены ли все баны
        blue_bans_done = len(state['blue_bans']) == 3
        red_bans_done = len(state['red_bans']) == 3
        
        if blue_bans_done and red_bans_done:
            # Все баны сделаны
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
        
        elif state['phase'] == 'ban_blue' and blue_bans_done:
            state['phase'] = 'ban_red'
            state['current_turn'] = 'red'
        
        elif state['phase'] == 'ban_red' and red_bans_done:
            state['phase'] = 'ban_blue'
            state['current_turn'] = 'blue'
    
    # Фаза пиков
    elif state['phase'] == 'pick':
        if state['current_turn'] != team:
            return False, 'Не ваша очередь'
        
        if team == 'blue' and len(state['blue_picks']) < 3:
            state['blue_picks'].append(brawler)
        elif team == 'red' and len(state['red_picks']) < 3:
            state['red_picks'].append(brawler)
        else:
            return False, 'Все пики уже сделаны'
        
        state['all_selected'].append(brawler)
        state['last_action'] = time.time()
        
        # Переходим к следующему пику
        state['current_pick_index'] += 1
        
        # Проверяем, завершен ли драфт
        if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
        elif state['current_pick_index'] < len(state['pick_order']):
            state['current_turn'] = state['pick_order'][state['current_pick_index']]
        else:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
    
    return True, 'Успешно'

def get_client_state(state, team):
    """Возвращает состояние для клиента, скрывая баны противника если нужно"""
    client_state = state.copy()
    
    # Скрываем баны противника в фазе банов
    if 'ban' in state['phase'] and team in ['blue', 'red']:
        if team == 'blue':
            client_state['red_bans'] = ['hidden'] * len(state['red_bans'])
        else:
            client_state['blue_bans'] = ['hidden'] * len(state['blue_bans'])
    
    # Рассчитываем время до автосброса
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        client_state['reset_in'] = max(0, 60 - int(elapsed))
    else:
        client_state['reset_in'] = None
    
    return client_state

# Декоратор для проверки админ-доступа
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_token' not in session or session['admin_token'] != ADMIN_TOKEN:
            return "Доступ запрещен", 403
        return f(*args, **kwargs)
    return decorated_function

# Маршруты для разных ролей
@app.route('/')
def spectator_view():
    return render_template('index.html', role='spectator')

@app.route('/blue')
def blue_view():
    return render_template('index.html', role='blue')

@app.route('/red')
def red_view():
    return render_template('index.html', role='red')

@app.route('/admin/<token>')
def admin_view(token):
    if token == ADMIN_TOKEN:
        session['admin_token'] = ADMIN_TOKEN
        return render_template('index.html', role='admin')
    return "Неверная ссылка", 404

# API маршруты
@app.route('/api/state')
def get_state():
    role = request.args.get('role', 'spectator')
    room_id = MAIN_ROOM_ID
    _, state = get_or_create_state(room_id)
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_draft()
        _, state = get_or_create_state(room_id)
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, role if role in ['blue', 'red'] else 'spectator'),
        'brawlers': BRWLERS,
        'role': role
    })

@app.route('/api/ready', methods=['POST'])
def set_ready():
    data = request.json
    role = data.get('role', '')
    
    if role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверная роль'})
    
    room_id, state = get_or_create_state(MAIN_ROOM_ID)
    
    if role == 'blue':
        state['blue_ready'] = True
    elif role == 'red':
        state['red_ready'] = True
    
    state['last_action'] = time.time()
    
    # Проверяем, готовы ли обе команды
    if state['blue_ready'] and state['red_ready'] and state['phase'] == 'waiting':
        state['phase'] = 'ban_blue'
        state['current_turn'] = 'blue'
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, role),
        'message': f'Команда {role} готова!'
    })

@app.route('/api/select', methods=['POST'])
def select_brawler():
    data = request.json
    brawler = data.get('brawler', '').strip()
    role = data.get('role', '')
    
    if not brawler or not role or role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверные данные'})
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Бравлер не найден'})
    
    room_id, state = get_or_create_state(MAIN_ROOM_ID)
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_draft()
        return jsonify({'success': False, 'error': 'Драфт был сброшен по таймеру', 'auto_reset': True})
    
    success, message = update_state(state, role, brawler, 'select')
    
    if success:
        return jsonify({
            'success': True,
            'message': message,
            'state': get_client_state(state, role)
        })
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/api/reset', methods=['POST'])
@admin_required
def reset_draft():
    room_id, state = get_or_create_state(MAIN_ROOM_ID)
    
    state.update({
        'blue_bans': [],
        'red_bans': [],
        'blue_picks': [],
        'red_picks': [],
        'all_selected': [],
        'phase': 'waiting',
        'current_turn': None,
        'picking_team': None,
        'pick_order': [],
        'current_pick_index': 0,
        'last_action': time.time(),
        'finished_at': None,
        'blue_ready': False,
        'red_ready': False
    })
    
    return jsonify({'success': True, 'state': get_client_state(state, 'spectator')})

@app.route('/api/maps')
def get_maps():
    return jsonify({
        'success': True,
        'maps': MAPS_BY_MODE,
        'modes': list(MAPS_BY_MODE.keys())
    })

@app.route('/api/select_map', methods=['POST'])
@admin_required
def select_map():
    data = request.json
    map_name = data.get('map_name')
    map_mode = data.get('map_mode')
    
    room_id, state = get_or_create_state(MAIN_ROOM_ID)
    
    # Проверяем, что карта существует
    if map_mode not in MAPS_BY_MODE:
        return jsonify({'success': False, 'error': 'Неверный режим'})
    
    map_found = False
    for map_info in MAPS_BY_MODE[map_mode]:
        if map_info['name'] == map_name:
            state['selected_map'] = map_info
            state['selected_mode'] = map_mode
            state['last_action'] = time.time()
            map_found = True
            break
    
    if not map_found:
        return jsonify({'success': False, 'error': 'Карта не найдена'})
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': f'Карта {map_name} выбрана!'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Ссылки для доступа:")
    print(f"  Наблюдатель: http://localhost:{port}/")
    print(f"  Синяя команда: http://localhost:{port}/blue")
    print(f"  Красная команда: http://localhost:{port}/red")
    print(f"  Админ: http://localhost:{port}/admin/{ADMIN_TOKEN}")
    app.run(host='0.0.0.0', port=port, debug=True)
