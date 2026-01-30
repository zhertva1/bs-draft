import os
import random
import time
from flask import Flask, render_template, jsonify, request, session, redirect
from datetime import datetime, timedelta
import threading
import uuid

app = Flask(__name__)
app.secret_key = 'super-secret-key-for-brawl-draft'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Фиксированный админ-токен
ADMIN_TOKEN = "admin_9605183db62b41bd"
print(f"✅ Админ-панель доступна по ссылке: /admin/{ADMIN_TOKEN}")
print(f"✅ Наблюдатель: /")
print(f"✅ Синяя команда: /blue")
print(f"✅ Красная команда: /red")

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
    
    if not maps:
        print("⚠️  ВНИМАНИЕ: Папка mappool пустая или не найдена!")
        print("   Создайте папки: static/mappool/Heist/, static/mappool/Gem_Grab/ и т.д.")
    
    return maps

MAPS_BY_MODE = get_maps_by_mode()

# Глобальное состояние драфта
draft_states = {}
# Активные сессии по командам
active_sessions = {
    'blue': {'id': None, 'last_active': 0},
    'red': {'id': None, 'last_active': 0},
    'admin': {'id': None, 'last_active': 0}
}
# Блокировка для потокобезопасности
state_lock = threading.Lock()

def get_or_create_state():
    with state_lock:
        if 'main' not in draft_states:
            draft_states['main'] = {
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
                'selected_mode': None,
                'ban_end_time': None,
                'pick_end_time': None,
                'phase_start_time': None
            }
        
        return 'main', draft_states['main']

def check_session_access(role, session_id):
    """Проверяет доступность сессии для роли"""
    with state_lock:
        # Админ и наблюдатель всегда имеют доступ
        if role in ['admin', 'spectator']:
            return True
        
        current_time = time.time()
        
        # Проверяем, не истекла ли старая сессия (30 секунд бездействия)
        if (active_sessions[role]['id'] and 
            current_time - active_sessions[role]['last_active'] > 30):
            # Освобождаем старую сессию
            print(f"⏰ Сессия истекла для {role}")
            active_sessions[role]['id'] = None
        
        # Если для этой роли нет активной сессии, занимаем ее
        if active_sessions[role]['id'] is None:
            active_sessions[role]['id'] = session_id
            active_sessions[role]['last_active'] = current_time
            print(f"✅ Сессия занята для {role}: {session_id[:8]}...")
            return True
        
        # Если сессия совпадает с активной, обновляем время
        if active_sessions[role]['id'] == session_id:
            active_sessions[role]['last_active'] = current_time
            return True
        
        # Иначе доступ запрещен
        print(f"❌ Доступ запрещен для {role}. Активная сессия: {active_sessions[role]['id'][:8]}...")
        return False

def release_session(role, session_id):
    """Освобождает сессию для роли"""
    with state_lock:
        if active_sessions[role]['id'] == session_id:
            active_sessions[role]['id'] = None
            active_sessions[role]['last_active'] = 0
            print(f"🔓 Сессия освобождена для {role}")

def check_auto_reset(state):
    """Проверяет, нужно ли сбросить драфт"""
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        if elapsed > 60:  # 60 секунд
            return True
    return False

def auto_select_bans(state):
    """Автоматический выбор банов при истечении времени"""
    with state_lock:
        available_brawlers = [b for b in BRWLERS if b not in state['all_selected']]
        
        # Автобан для синей команды
        while len(state['blue_bans']) < 3 and available_brawlers:
            random_brawler = random.choice(available_brawlers)
            state['blue_bans'].append(random_brawler)
            state['all_selected'].append(random_brawler)
            available_brawlers.remove(random_brawler)
        
        # Автобан для красной команды
        while len(state['red_bans']) < 3 and available_brawlers:
            random_brawler = random.choice(available_brawlers)
            state['red_bans'].append(random_brawler)
            state['all_selected'].append(random_brawler)
            available_brawlers.remove(random_brawler)
        
        # Переход к фазе пиков
        if len(state['blue_bans']) == 3 and len(state['red_bans']) == 3:
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
            state['phase_start_time'] = time.time()
            state['pick_end_time'] = time.time() + 40  # 40 секунд на пик
            
            print(f"⏰ Таймер банов истек, переходим к пикам. Первый пик: {state['current_turn']}")

def auto_select_pick(state):
    """Автоматический выбор пика при истечении времени"""
    with state_lock:
        available_brawlers = [b for b in BRWLERS if b not in state['all_selected']]
        
        if not available_brawlers:
            return
        
        random_brawler = random.choice(available_brawlers)
        
        if state['current_turn'] == 'blue' and len(state['blue_picks']) < 3:
            state['blue_picks'].append(random_brawler)
        elif state['current_turn'] == 'red' and len(state['red_picks']) < 3:
            state['red_picks'].append(random_brawler)
        
        state['all_selected'].append(random_brawler)
        state['last_action'] = time.time()
        
        print(f"⏰ Автовыбор пика для {state['current_turn']}: {random_brawler}")
        
        # Переходим к следующему пику
        state['current_pick_index'] += 1
        
        # Проверяем, завершен ли драфт
        if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
            print("✅ Драфт завершен (автовыбор)")
        elif state['current_pick_index'] < len(state['pick_order']):
            state['current_turn'] = state['pick_order'][state['current_pick_index']]
            state['phase_start_time'] = time.time()
            state['pick_end_time'] = time.time() + 40  # 40 секунд на следующий пик
        else:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()

def update_state(state, team, brawler, action_type):
    """Обновляет состояние драфта"""
    with state_lock:
        if brawler in state['all_selected']:
            return False, 'Бравлер уже выбран'
        
        if state['phase'] == 'waiting':
            return False, 'Ожидаем готовности обеих команд'
        
        if state['phase'] == 'finished':
            return False, 'Драфт уже завершен'
        
        # Фаза банов (одновременные баны)
        if state['phase'] == 'ban':
            if team == 'blue' and len(state['blue_bans']) < 3:
                state['blue_bans'].append(brawler)
            elif team == 'red' and len(state['red_bans']) < 3:
                state['red_bans'].append(brawler)
            else:
                return False, 'Все баны уже сделаны'
            
            state['all_selected'].append(brawler)
            state['last_action'] = time.time()
            
            print(f"✅ {team} забанил бравлера: {brawler}")
            
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
                state['phase_start_time'] = time.time()
                state['pick_end_time'] = time.time() + 40
                
                # Останавливаем таймер банов
                state['ban_end_time'] = None
        
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
            
            print(f"✅ {team} выбрал бравлера: {brawler}")
            
            # Переходим к следующему пику
            state['current_pick_index'] += 1
            
            # Проверяем, завершен ли драфт
            if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
                state['phase'] = 'finished'
                state['finished_at'] = time.time()
                state['pick_end_time'] = None
            elif state['current_pick_index'] < len(state['pick_order']):
                state['current_turn'] = state['pick_order'][state['current_pick_index']]
                state['phase_start_time'] = time.time()
                state['pick_end_time'] = time.time() + 40
            else:
                state['phase'] = 'finished'
                state['finished_at'] = time.time()
                state['pick_end_time'] = None
        
        return True, 'Успешно'

def get_client_state(state, team):
    """Возвращает состояние для клиента"""
    with state_lock:
        client_state = state.copy()
        
        # Рассчитываем время до автосброса
        if state['phase'] == 'finished' and state['finished_at']:
            elapsed = time.time() - state['finished_at']
            client_state['reset_in'] = max(0, 60 - int(elapsed))
        else:
            client_state['reset_in'] = None
        
        # Рассчитываем оставшееся время для текущей фазы
        if state['phase'] == 'ban' and state['ban_end_time']:
            client_state['time_left'] = max(0, int(state['ban_end_time'] - time.time()))
        elif state['phase'] == 'pick' and state['pick_end_time']:
            client_state['time_left'] = max(0, int(state['pick_end_time'] - time.time()))
        else:
            client_state['time_left'] = None
        
        return client_state

# ========== РОЛИ ==========
@app.route('/')
def spectator_view():
    session.clear()
    session['role'] = 'spectator'
    session['session_id'] = str(uuid.uuid4())
    return render_template('index.html', role='spectator')

@app.route('/blue')
def blue_view():
    # Очищаем сессию и создаем новую
    session.clear()
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    session['role'] = 'blue'
    session.modified = True
    
    print(f"🔵 Попытка входа синей команды. Сессия ID: {session_id[:8]}...")
    
    # Проверяем доступ
    if not check_session_access('blue', session_id):
        print(f"❌ Доступ запрещен для синей команды")
        return render_template('access_denied.html', 
                             message="Синяя команда уже занята другим игроком. Дождитесь, пока текущий игрок выйдет.",
                             role='spectator'), 403
    
    print(f"✅ Доступ разрешен для синей команды")
    return render_template('index.html', role='blue')

@app.route('/red')
def red_view():
    # Очищаем сессию и создаем новую
    session.clear()
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    session['role'] = 'red'
    session.modified = True
    
    print(f"🔴 Попытка входа красной команды. Сессия ID: {session_id[:8]}...")
    
    # Проверяем доступ
    if not check_session_access('red', session_id):
        print(f"❌ Доступ запрещен для красной команды")
        return render_template('access_denied.html',
                             message="Красная команда уже занята другим игроком. Дождитесь, пока текущий игрок выйдет.",
                             role='spectator'), 403
    
    print(f"✅ Доступ разрешен для красной команды")
    return render_template('index.html', role='red')

@app.route('/admin/<token>')
def admin_view(token):
    if token == ADMIN_TOKEN:
        session.clear()
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        session['admin_token'] = ADMIN_TOKEN
        session['role'] = 'admin'
        session.modified = True
        
        # Регистрируем админ-сессию
        check_session_access('admin', session_id)
        
        print(f"👑 Админ вошел. Сессия ID: {session_id[:8]}...")
        return render_template('index.html', role='admin')
    else:
        return render_template('access_denied.html',
                             message="Неверная админ-ссылка",
                             role='spectator'), 404

# Страница выхода
@app.route('/logout')
def logout():
    role = session.get('role')
    session_id = session.get('session_id')
    
    if role and session_id:
        release_session(role, session_id)
        print(f"🚪 Выход: {role}, сессия: {session_id[:8]}...")
    
    session.clear()
    return redirect('/')

# ========== API МАРШРУТЫ ==========
@app.route('/api/state')
def get_state():
    role = request.args.get('role', 'spectator')
    session_id = session.get('session_id', '')
    
    # Проверяем доступ для командных ролей
    if role in ['blue', 'red', 'admin']:
        if not check_session_access(role, session_id):
            return jsonify({
                'success': False,
                'error': 'Доступ занят другим игроком',
                'redirect': '/'
            }), 403
    
    room_id, state = get_or_create_state()
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_state()
        room_id, state = get_or_create_state()
    
    # Проверяем таймеры
    with state_lock:
        current_time = time.time()
        
        # Проверка таймера банов
        if state['phase'] == 'ban' and state['ban_end_time'] and current_time > state['ban_end_time']:
            auto_select_bans(state)
        
        # Проверка таймера пиков
        elif state['phase'] == 'pick' and state['pick_end_time'] and current_time > state['pick_end_time']:
            auto_select_pick(state)
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, role if role in ['blue', 'red'] else 'spectator'),
        'brawlers': BRWLERS,
        'role': role,
        'maps': MAPS_BY_MODE,
        'session_id': session_id
    })

@app.route('/api/ready', methods=['POST'])
def set_ready():
    data = request.json
    role = data.get('role', '')
    session_id = session.get('session_id', '')
    
    if role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверная роль'})
    
    # Проверяем доступ
    if not check_session_access(role, session_id):
        return jsonify({'success': False, 'error': 'Доступ занят другим игроком', 'redirect': '/'}), 403
    
    room_id, state = get_or_create_state()
    
    with state_lock:
        if role == 'blue':
            state['blue_ready'] = True
        elif role == 'red':
            state['red_ready'] = True
        
        state['last_action'] = time.time()
        
        # Проверяем, готовы ли обе команды
        if state['blue_ready'] and state['red_ready'] and state['phase'] == 'waiting':
            state['phase'] = 'ban'
            state['phase_start_time'] = time.time()
            state['ban_end_time'] = time.time() + 40  # 40 секунд на баны
            print(f"🚀 Драфт начат! Фаза банов (40 секунд)")
    
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
    session_id = session.get('session_id', '')
    
    if not brawler or not role or role not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверные данные'})
    
    # Проверяем доступ
    if not check_session_access(role, session_id):
        return jsonify({'success': False, 'error': 'Доступ занят другим игроком', 'redirect': '/'}), 403
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Бравлер не найден'})
    
    room_id, state = get_or_create_state()
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_state()
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
def reset_draft():
    # Проверяем, что это админ
    if session.get('admin_token') != ADMIN_TOKEN:
        return jsonify({'success': False, 'error': 'Доступ запрещен'}), 403
    
    reset_state()
    return jsonify({
        'success': True,
        'state': get_client_state(draft_states['main'], 'spectator'),
        'message': 'Драфт сброшен!'
    })

def reset_state():
    """Сброс состояния драфта"""
    with state_lock:
        draft_states['main'] = {
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
            'selected_mode': None,
            'ban_end_time': None,
            'pick_end_time': None,
            'phase_start_time': None
        }
        print("🔄 Драфт сброшен")

@app.route('/api/maps')
def get_maps():
    return jsonify({
        'success': True,
        'maps': MAPS_BY_MODE,
        'modes': list(MAPS_BY_MODE.keys())
    })

@app.route('/api/select_map', methods=['POST'])
def select_map():
    # Проверяем, что это админ
    if session.get('admin_token') != ADMIN_TOKEN:
        return jsonify({'success': False, 'error': 'Доступ запрещен'}), 403
    
    data = request.json
    map_name = data.get('map_name')
    map_mode = data.get('map_mode')
    
    room_id, state = get_or_create_state()
    
    # Проверяем, что карта существует
    if map_mode not in MAPS_BY_MODE:
        return jsonify({'success': False, 'error': 'Неверный режим'})
    
    map_found = False
    for map_info in MAPS_BY_MODE[map_mode]:
        if map_info['name'] == map_name:
            with state_lock:
                state['selected_map'] = map_info
                state['selected_mode'] = map_mode
                state['last_action'] = time.time()
            map_found = True
            print(f"🗺️  Выбрана карта: {map_name} ({map_mode})")
            break
    
    if not map_found:
        return jsonify({'success': False, 'error': 'Карта не найдена'})
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, 'spectator'),
        'message': f'Карта {map_name} выбрана!'
    })

# API для освобождения сессии при закрытии страницы
@app.route('/api/release_session', methods=['POST'])
def release_session_api():
    data = request.json
    role = data.get('role', '')
    session_id = session.get('session_id', '')
    
    if role and session_id:
        release_session(role, session_id)
    
    return jsonify({'success': True})

# Статические файлы
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# Тестовая страница
@app.route('/test')
def test_page():
    return jsonify({
        'status': 'online',
        'brawlers': len(BRWLERS),
        'maps': {mode: len(maps) for mode, maps in MAPS_BY_MODE.items()},
        'admin_url': f'/admin/{ADMIN_TOKEN}',
        'active_sessions': {k: v['id'][:8] + '...' if v['id'] else None for k, v in active_sessions.items()},
        'current_session': session.get('session_id', '')[:8] + '...' if session.get('session_id') else None,
        'current_role': session.get('role')
    })

# Фавикон
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*50)
    print("🎮 BRAWL STARS DRAFT SYSTEM")
    print("="*50)
    print(f"🔗 Наблюдатель: http://localhost:{port}/")
    print(f"🔵 Синяя команда: http://localhost:{port}/blue")
    print(f"🔴 Красная команда: http://localhost:{port}/red")
    print(f"⚡ Администратор: http://localhost:{port}/admin/{ADMIN_TOKEN}")
    print("="*50)
    print(f"✅ Всего бравлеров: {len(BRWLERS)}")
    print(f"✅ Режимов карт: {len(MAPS_BY_MODE)}")
    if MAPS_BY_MODE:
        for mode, maps in MAPS_BY_MODE.items():
            print(f"   • {mode}: {len(maps)} карт")
    else:
        print("⚠️  Карты не загружены! Создайте папки в static/mappool/")
    print("="*50)
    print("⏰ Таймеры: 40 секунд на баны, 40 секунд на каждый пик")
    print("🔒 Безопасность: Один игрок на команду")
    print("🔄 Автоочистка: Сессии очищаются через 30 секунд бездействия")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
