import os
import random
import time
from flask import Flask, render_template, jsonify, request, session, send_from_directory
from datetime import datetime, timedelta
from functools import wraps
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = 'super-secret-key-for-brawl-draft'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Фиксированный админ-токен
ADMIN_TOKEN = "admin_9605183db62b41bd"

# Получаем список бравлеров
def get_brawlers_list():
    image_folder = os.path.join(app.static_folder, 'brawler_images')
    brawlers = []
    
    if os.path.exists(image_folder):
        for filename in os.listdir(image_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                name = os.path.splitext(filename)[0]
                brawlers.append(name)
    
    return sorted(brawlers, key=lambda x: x.lower())

BRWLERS = get_brawlers_list()
print(f"✅ Загружено бравлеров: {len(BRWLERS)}")

# Проверяем наличие гаджетов для бравлеров
def check_brawler_gadgets(brawler_name):
    gadgets = []
    gadgets_folder = os.path.join(app.static_folder, 'gadgets')
    
    if os.path.exists(gadgets_folder):
        # Проверяем оба варианта гаджетов
        for i in range(1, 3):
            gadget_name = f"{brawler_name}_gadget_{i:02d}.png"
            gadget_path = os.path.join(gadgets_folder, gadget_name)
            if os.path.exists(gadget_path):
                gadgets.append({
                    'number': i,
                    'filename': gadget_name,
                    'path': f'/static/gadgets/{gadget_name}'
                })
    
    return sorted(gadgets, key=lambda x: x['number'])

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
                    if map_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        map_name = os.path.splitext(map_file)[0]
                        maps[mode_folder].append({
                            'name': map_name,
                            'file': map_file,
                            'mode': mode_folder
                        })
                print(f"✅ Режим '{mode_folder}': {len(maps[mode_folder])} карт")
    
    return maps

MAPS_BY_MODE = get_maps_by_mode()

# Глобальное состояние драфта
draft_states = {}

def get_or_create_state():
    if 'main' not in draft_states:
        draft_states['main'] = {
            'blue_bans': [],
            'red_bans': [],
            'blue_picks': [],
            'red_picks': [],
            'blue_gadgets': {},  # {brawler_name: gadget_number}
            'red_gadgets': {},   # {brawler_name: gadget_number}
            'all_selected': [],
            'phase': 'waiting',
            'phase_start_time': None,
            'phase_duration': 40,
            'current_turn': None,
            'pick_order': [],
            'current_pick_index': 0,
            'created_at': time.time(),
            'last_action': time.time(),
            'finished_at': None,
            'blue_ready': False,
            'red_ready': False,
            'selected_map': None,
            'selected_mode': None,
            'timer_active': False,
            'auto_bans_done': False,
            'auto_picks_done': [False, False, False, False, False, False],
            'bans_completed': False,
            'draft_started': False,
            'blue_team_name': 'СИНЯЯ КОМАНДА',
            'red_team_name': 'КРАСНАЯ КОМАНДА',
            'picking_team': None,
            'next_pick_indicator': 0,
            'team_names_locked': False,
            'gadget_selections_enabled': False  # Флаг для активации выбора гаджетов
        }
    
    return 'main', draft_states['main']

def check_auto_reset(state):
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        if elapsed > 60:
            state['blue_ready'] = False
            state['red_ready'] = False
            state['phase'] = 'waiting'
            state['phase_start_time'] = None
            state['current_turn'] = None
            state['current_pick_index'] = 0
            state['finished_at'] = None
            state['auto_bans_done'] = False
            state['auto_picks_done'] = [False, False, False, False, False, False]
            state['bans_completed'] = False
            state['draft_started'] = False
            state['picking_team'] = None
            state['next_pick_indicator'] = 0
            state['team_names_locked'] = False
            state['gadget_selections_enabled'] = False
            state['blue_gadgets'] = {}
            state['red_gadgets'] = {}
            return True
    return False

def get_available_brawlers(state):
    if state['phase'] == 'ban' and not state['bans_completed']:
        return BRWLERS.copy()
    return [b for b in BRWLERS if b not in state['all_selected']]

def auto_ban(state):
    available = get_available_brawlers(state)
    
    while len(state['blue_bans']) < 3 and available:
        brawler = random.choice(available)
        state['blue_bans'].append(brawler)
        if state['bans_completed'] and brawler not in state['all_selected']:
            state['all_selected'].append(brawler)
        available.remove(brawler)
    
    available = get_available_brawlers(state)
    
    while len(state['red_bans']) < 3 and available:
        brawler = random.choice(available)
        state['red_bans'].append(brawler)
        if state['bans_completed'] and brawler not in state['all_selected']:
            state['all_selected'].append(brawler)
        available.remove(brawler)

def auto_pick(state, team):
    available = get_available_brawlers(state)
    if available:
        brawler = random.choice(available)
        if team == 'blue' and len(state['blue_picks']) < 3:
            state['blue_picks'].append(brawler)
            if brawler not in state['all_selected']:
                state['all_selected'].append(brawler)
            
            # Устанавливаем гаджет по умолчанию (1) если есть гаджеты
            gadgets = check_brawler_gadgets(brawler)
            if gadgets:
                state['blue_gadgets'][brawler] = 1
            
            return True
        elif team == 'red' and len(state['red_picks']) < 3:
            state['red_picks'].append(brawler)
            if brawler not in state['all_selected']:
                state['all_selected'].append(brawler)
            
            # Устанавливаем гаджет по умолчанию (1) если есть гаджеты
            gadgets = check_brawler_gadgets(brawler)
            if gadgets:
                state['red_gadgets'][brawler] = 1
            
            return True
    return False

def check_timer(state):
    if not state['phase_start_time']:
        return
    
    elapsed = time.time() - state['phase_start_time']
    
    if state['phase'] == 'ban':
        if elapsed > state['phase_duration'] and not state['auto_bans_done']:
            auto_ban(state)
            state['auto_bans_done'] = True
            state['bans_completed'] = True
            
            for b in state['blue_bans']:
                if b not in state['all_selected']:
                    state['all_selected'].append(b)
            for b in state['red_bans']:
                if b not in state['all_selected']:
                    state['all_selected'].append(b)
            
            # Определяем, какая команда начинает пики
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
            state['next_pick_indicator'] = 0
            state['phase_start_time'] = time.time()
            state['gadget_selections_enabled'] = True
    
    elif state['phase'] == 'pick':
        if elapsed > state['phase_duration'] and state['current_pick_index'] < len(state['pick_order']):
            if not state['auto_picks_done'][state['current_pick_index']]:
                if auto_pick(state, state['current_turn']):
                    state['auto_picks_done'][state['current_pick_index']] = True
                    state['current_pick_index'] += 1
                    state['next_pick_indicator'] = state['current_pick_index']
                    
                    if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
                        state['phase'] = 'finished'
                        state['finished_at'] = time.time()
                    elif state['current_pick_index'] < len(state['pick_order']):
                        state['current_turn'] = state['pick_order'][state['current_pick_index']]
                        state['phase_start_time'] = time.time()
                    else:
                        state['phase'] = 'finished'
                        state['finished_at'] = time.time()

def update_state(state, team, brawler, action_type):
    if state['phase'] == 'waiting':
        return False, 'Ожидаем готовности обеих команд'
    
    if state['phase'] == 'finished':
        return False, 'Драфт уже завершен'
    
    check_timer(state)
    
    if state['phase'] == 'ban':
        if team == 'blue' and len(state['blue_bans']) < 3:
            if brawler in state['blue_bans']:
                return False, 'Этот бравлер уже забанен вашей командой'
            state['blue_bans'].append(brawler)
        elif team == 'red' and len(state['red_bans']) < 3:
            if brawler in state['red_bans']:
                return False, 'Этот бравлер уже забанен вашей командой'
            state['red_bans'].append(brawler)
        else:
            return False, 'Все баны уже сделаны'
        
        state['last_action'] = time.time()
        
        blue_bans_done = len(state['blue_bans']) == 3
        red_bans_done = len(state['red_bans']) == 3
        
        if blue_bans_done and red_bans_done:
            state['bans_completed'] = True
            for b in state['blue_bans']:
                if b not in state['all_selected']:
                    state['all_selected'].append(b)
            for b in state['red_bans']:
                if b not in state['all_selected']:
                    state['all_selected'].append(b)
            
            # Определяем, какая команда начинает пики
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
            state['next_pick_indicator'] = 0
            state['phase_start_time'] = time.time()
            state['gadget_selections_enabled'] = True
    
    elif state['phase'] == 'pick':
        if state['current_turn'] != team:
            return False, 'Не ваша очередь'
        
        if brawler in state['all_selected']:
            return False, 'Бравлер уже выбран'
        
        if team == 'blue' and len(state['blue_picks']) < 3:
            state['blue_picks'].append(brawler)
            # Устанавливаем гаджет по умолчанию (1) если есть гаджеты
            gadgets = check_brawler_gadgets(brawler)
            if gadgets:
                state['blue_gadgets'][brawler] = 1
        elif team == 'red' and len(state['red_picks']) < 3:
            state['red_picks'].append(brawler)
            # Устанавливаем гаджет по умолчанию (1) если есть гаджеты
            gadgets = check_brawler_gadgets(brawler)
            if gadgets:
                state['red_gadgets'][brawler] = 1
        else:
            return False, 'Все пики уже сделаны'
        
        state['all_selected'].append(brawler)
        state['last_action'] = time.time()
        state['current_pick_index'] += 1
        state['next_pick_indicator'] = state['current_pick_index']
        state['phase_start_time'] = time.time()
        state['gadget_selections_enabled'] = True
        
        if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
        elif state['current_pick_index'] < len(state['pick_order']):
            state['current_turn'] = state['pick_order'][state['current_pick_index']]
        else:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
    
    return True, 'Успешно'

def get_client_state(state, role):
    client_state = state.copy()
    
    if not state['bans_completed']:
        if role == 'blue':
            client_state['red_bans'] = ['hidden'] * len(state['red_bans'])
        elif role == 'red':
            client_state['blue_bans'] = ['hidden'] * len(state['blue_bans'])
        elif role not in ['admin', 'spectator']:
            client_state['blue_bans'] = ['hidden'] * len(state['blue_bans'])
            client_state['red_bans'] = ['hidden'] * len(state['red_bans'])
    
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        client_state['reset_in'] = max(0, 60 - int(elapsed))
    else:
        client_state['reset_in'] = None
    
    if state['phase_start_time'] and state['phase'] in ['ban', 'pick']:
        elapsed = time.time() - state['phase_start_time']
        client_state['time_left'] = max(0, state['phase_duration'] - int(elapsed))
    else:
        client_state['time_left'] = None
    
    # Определяем, какую монетку показывать
    client_state['show_coin'] = state['picking_team']
    
    # Добавляем информацию о гаджетах для бравлеров
    client_state['brawlers_gadgets'] = {}
    for brawler in BRWLERS:
        gadgets = check_brawler_gadgets(brawler)
        if gadgets:
            client_state['brawlers_gadgets'][brawler] = gadgets
    
    return client_state

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token') or session.get('admin_token')
        if not token or token != ADMIN_TOKEN:
            return jsonify({'success': False, 'error': 'Доступ запрещен'}), 403
        return f(*args, **kwargs)
    return decorated_function

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
    else:
        return f"Неверная ссылка. Используйте: /admin/{ADMIN_TOKEN}", 404

@app.route('/api/state')
def get_state():
    role = request.args.get('role', 'spectator')
    room_id, state = get_or_create_state()
    
    if check_auto_reset(state):
        pass
    
    check_timer(state)
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, role if role in ['blue', 'red', 'admin', 'spectator'] else 'spectator'),
        'brawlers': BRWLERS,
        'role': role,
        'maps': MAPS_BY_MODE
    })

@app.route('/api/ready', methods=['POST'])
def set_ready():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
    role = data.get('role', '')
    
    if role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверная роль'})
    
    room_id, state = get_or_create_state()
    
    if state['draft_started'] and state['phase'] != 'finished':
        return jsonify({'success': False, 'error': 'Драфт уже начался'})
    
    if state['phase'] == 'finished':
        state['blue_bans'] = []
        state['red_bans'] = []
        state['blue_picks'] = []
        state['red_picks'] = []
        state['all_selected'] = []
        state['blue_gadgets'] = {}
        state['red_gadgets'] = {}
        state['phase'] = 'waiting'
        state['current_turn'] = None
        state['current_pick_index'] = 0
        state['finished_at'] = None
        state['auto_bans_done'] = False
        state['auto_picks_done'] = [False, False, False, False, False, False]
        state['bans_completed'] = False
        state['draft_started'] = False
        state['picking_team'] = None
        state['next_pick_indicator'] = 0
        state['gadget_selections_enabled'] = False
    
    if role == 'blue':
        state['blue_ready'] = True
    elif role == 'red':
        state['red_ready'] = True
    
    state['last_action'] = time.time()
    
    if state['blue_ready'] and state['red_ready'] and state['phase'] == 'waiting':
        state['phase'] = 'ban'
        state['phase_start_time'] = time.time()
        state['timer_active'] = True
        state['draft_started'] = True
        state['blue_ready'] = False
        state['red_ready'] = False
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, role),
        'message': f'Команда {role} готова!'
    })

@app.route('/api/select', methods=['POST'])
def select_brawler():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
            
    brawler = data.get('brawler', '').strip()
    role = data.get('role', '')
    
    if not brawler or not role or role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверные данные'}), 400
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Бравлер не найден'}), 404
    
    room_id, state = get_or_create_state()
    
    check_timer(state)
    
    success, message = update_state(state, role, brawler, 'select')
    
    if success:
        return jsonify({
            'success': True,
            'message': message,
            'state': get_client_state(state, role)
        })
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/api/toggle_gadget', methods=['POST'])
def toggle_gadget():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
    
    brawler = data.get('brawler', '').strip()
    role = data.get('role', '')
    
    if not brawler or not role or role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверные данные'}), 400
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Бравлер не найден'}), 404
    
    room_id, state = get_or_create_state()
    
    # Проверяем, что драфт в фазе пиков или завершен
    if state['phase'] not in ['pick', 'finished']:
        return jsonify({'success': False, 'error': 'Нельзя менять гаджеты на этой фазе'})
    
    # Проверяем, что бравлер есть в пиках команды
    if role == 'blue':
        if brawler not in state['blue_picks']:
            return jsonify({'success': False, 'error': 'Этот бравлер не выбран вашей командой'})
        
        # Проверяем наличие гаджетов для этого бравлера
        gadgets = check_brawler_gadgets(brawler)
        if not gadgets:
            return jsonify({'success': False, 'error': 'У этого бравлера нет гаджетов'})
        
        # Переключаем гаджет
        current_gadget = state['blue_gadgets'].get(brawler, 1)
        if current_gadget == 1:
            state['blue_gadgets'][brawler] = 2
        else:
            state['blue_gadgets'][brawler] = 1
        
    elif role == 'red':
        if brawler not in state['red_picks']:
            return jsonify({'success': False, 'error': 'Этот бравлер не выбран вашей командой'})
        
        # Проверяем наличие гаджетов для этого бравлера
        gadgets = check_brawler_gadgets(brawler)
        if not gadgets:
            return jsonify({'success': False, 'error': 'У этого бравлера нет гаджетов'})
        
        # Переключаем гаджет
        current_gadget = state['red_gadgets'].get(brawler, 1)
        if current_gadget == 1:
            state['red_gadgets'][brawler] = 2
        else:
            state['red_gadgets'][brawler] = 1
    
    state['last_action'] = time.time()
    
    return jsonify({
        'success': True,
        'message': f'Гаджет изменен на {state["blue_gadgets" if role == "blue" else "red_gadgets"][brawler]}',
        'state': get_client_state(state, role),
        'gadget_number': state["blue_gadgets" if role == "blue" else "red_gadgets"][brawler]
    })

@app.route('/api/reset', methods=['POST'])
@admin_required
def reset_draft():
    room_id, state = get_or_create_state()
    
    state['blue_bans'] = []
    state['red_bans'] = []
    state['blue_picks'] = []
    state['red_picks'] = []
    state['all_selected'] = []
    state['blue_gadgets'] = {}
    state['red_gadgets'] = {}
    state['phase'] = 'waiting'
    state['phase_start_time'] = None
    state['current_turn'] = None
    state['pick_order'] = []
    state['current_pick_index'] = 0
    state['finished_at'] = None
    state['blue_ready'] = False
    state['red_ready'] = False
    state['selected_map'] = None
    state['selected_mode'] = None
    state['timer_active'] = False
    state['auto_bans_done'] = False
    state['auto_picks_done'] = [False, False, False, False, False, False]
    state['bans_completed'] = False
    state['draft_started'] = False
    state['picking_team'] = None
    state['next_pick_indicator'] = 0
    state['team_names_locked'] = False
    state['gadget_selections_enabled'] = False
    state['last_action'] = time.time()
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': 'Драфт полностью сброшен!'
    })

@app.route('/api/new_draft', methods=['POST'])
@admin_required
def new_draft():
    room_id, state = get_or_create_state()
    
    state['blue_bans'] = []
    state['red_bans'] = []
    state['blue_picks'] = []
    state['red_picks'] = []
    state['all_selected'] = []
    state['blue_gadgets'] = {}
    state['red_gadgets'] = {}
    state['phase'] = 'waiting'
    state['phase_start_time'] = None
    state['current_turn'] = None
    state['pick_order'] = []
    state['current_pick_index'] = 0
    state['finished_at'] = None
    state['timer_active'] = False
    state['auto_bans_done'] = False
    state['auto_picks_done'] = [False, False, False, False, False, False]
    state['bans_completed'] = False
    state['draft_started'] = False
    state['picking_team'] = None
    state['next_pick_indicator'] = 0
    state['team_names_locked'] = False
    state['gadget_selections_enabled'] = False
    state['last_action'] = time.time()
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': 'Новый драфт начат (карта сохранена)!'
    })

@app.route('/api/update_team_names', methods=['POST'])
@admin_required
def update_team_names():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
    
    blue_name = data.get('blue_team_name', '').strip()
    red_name = data.get('red_team_name', '').strip()
    
    if not blue_name or not red_name:
        return jsonify({'success': False, 'error': 'Имена команд не могут быть пустыми'}), 400
    
    room_id, state = get_or_create_state()
    state['blue_team_name'] = blue_name
    state['red_team_name'] = red_name
    state['team_names_locked'] = True
    state['last_action'] = time.time()
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': 'Названия команд обновлены!'
    })

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
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
            
    map_name = data.get('map_name')
    map_mode = data.get('map_mode')
    
    room_id, state = get_or_create_state()
    
    if map_mode not in MAPS_BY_MODE:
        return jsonify({'success': False, 'error': 'Неверный режим'}), 404
    
    map_found = False
    for map_info in MAPS_BY_MODE[map_mode]:
        if map_info['name'] == map_name:
            state['selected_map'] = map_info
            state['selected_mode'] = map_mode
            state['last_action'] = time.time()
            map_found = True
            break
    
    if not map_found:
        return jsonify({'success': False, 'error': 'Карта не найдена'}), 404
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': f'Карта {map_name} выбрана!'
    })

@app.route('/static/<path:filename>')
def serve_static(filename):
    response = send_from_directory('static', filename)
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.otf')):
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        response.headers['Expires'] = (datetime.utcnow() + timedelta(days=365)).strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response

@app.route('/test')
def test_page():
    return jsonify({
        'status': 'online',
        'brawlers': len(BRWLERS),
        'maps': {mode: len(maps) for mode, maps in MAPS_BY_MODE.items()},
        'admin_url': f'/admin/{ADMIN_TOKEN}'
    })

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*50)
    print("🎮 BRAWL STARS DRAFT SYSTEM")
    print("="*50)
    print(f"✅ Админ: http://localhost:{port}/admin/{ADMIN_TOKEN}")
    print(f"✅ Синяя команда: http://localhost:{port}/blue")
    print(f"✅ Красная команда: http://localhost:{port}/red")
    print(f"✅ Наблюдатель: http://localhost:{port}/")
    print("="*50)
    app.run(host='0.0.0.0', port=port, debug=True)
