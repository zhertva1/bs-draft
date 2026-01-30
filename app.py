import os
import random
import time
from flask import Flask, render_template, jsonify, request, session, send_from_directory
from datetime import datetime, timedelta
from functools import wraps
from flask_cors import CORS  # Добавляем CORS поддержку

app = Flask(__name__)
CORS(app)  # Включаем CORS для всех маршрутов
app.secret_key = 'super-secret-key-for-brawl-draft'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Фиксированный админ-токен (можно изменить)
ADMIN_TOKEN = "admin_9605183db62b41bd"
print(f"✅ Админ-панель доступна по ссылке: /admin/{ADMIN_TOKEN}")
print(f"✅ Наблюдатель: http://localhost:5000/")
print(f"✅ Синяя команда: http://localhost:5000/blue")
print(f"✅ Красная команда: http://localhost:5000/red")

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

def get_or_create_state():
    if 'main' not in draft_states:
        draft_states['main'] = {
            'blue_bans': [],
            'red_bans': [],
            'blue_picks': [],
            'red_picks': [],
            'all_selected': [],
            'phase': 'waiting',
            'phase_start_time': None,
            'phase_duration': 40,  # 40 секунд на фазу
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
            'auto_picks_done': [False, False, False, False, False, False]  # Для каждого из 6 пиков
        }
    
    return 'main', draft_states['main']

def check_auto_reset(state):
    """Проверяет, нужно ли сбросить драфт"""
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        if elapsed > 60:  # 60 секунд
            return True
    return False

def get_available_brawlers(state):
    """Возвращает список доступных бравлеров"""
    return [b for b in BRWLERS if b not in state['all_selected']]

def auto_ban(state):
    """Автоматический бан для команды, которая не успела"""
    available = get_available_brawlers(state)
    
    # Автобаны для синей команды
    while len(state['blue_bans']) < 3 and available:
        brawler = random.choice(available)
        state['blue_bans'].append(brawler)
        state['all_selected'].append(brawler)
        available.remove(brawler)
        print(f"🤖 Автобан для синей команды: {brawler}")
    
    # Автобаны для красной команды
    while len(state['red_bans']) < 3 and available:
        brawler = random.choice(available)
        state['red_bans'].append(brawler)
        state['all_selected'].append(brawler)
        available.remove(brawler)
        print(f"🤖 Автобан для красной команды: {brawler}")

def auto_pick(state, team):
    """Автоматический пик для команды"""
    available = get_available_brawlers(state)
    if available:
        brawler = random.choice(available)
        if team == 'blue' and len(state['blue_picks']) < 3:
            state['blue_picks'].append(brawler)
            state['all_selected'].append(brawler)
            print(f"🤖 Автопик для синей команды: {brawler}")
            return True
        elif team == 'red' and len(state['red_picks']) < 3:
            state['red_picks'].append(brawler)
            state['all_selected'].append(brawler)
            print(f"🤖 Автопик для красной команды: {brawler}")
            return True
    return False

def check_timer(state):
    """Проверяет таймер и выполняет автоматические действия"""
    if not state['phase_start_time']:
        return
    
    elapsed = time.time() - state['phase_start_time']
    
    if state['phase'] == 'ban':
        if elapsed > state['phase_duration'] and not state['auto_bans_done']:
            print(f"⏰ Время на баны вышло! Выполняем автобаны...")
            auto_ban(state)
            state['auto_bans_done'] = True
            
            # Переходим к пикам
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
            state['phase_start_time'] = time.time()
            state['timer_active'] = True
    
    elif state['phase'] == 'pick':
        if elapsed > state['phase_duration'] and state['current_pick_index'] < len(state['pick_order']):
            # Проверяем, не был ли уже выполнен автопик для этого индекса
            if not state['auto_picks_done'][state['current_pick_index']]:
                print(f"⏰ Время на пик вышло! Автопик для {state['current_turn']} команды...")
                if auto_pick(state, state['current_turn']):
                    state['auto_picks_done'][state['current_pick_index']] = True
                    
                    # Переходим к следующему пику
                    state['current_pick_index'] += 1
                    
                    # Проверяем, завершен ли драфт
                    if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
                        state['phase'] = 'finished'
                        state['finished_at'] = time.time()
                        state['timer_active'] = False
                    elif state['current_pick_index'] < len(state['pick_order']):
                        state['current_turn'] = state['pick_order'][state['current_pick_index']]
                        state['phase_start_time'] = time.time()
                    else:
                        state['phase'] = 'finished'
                        state['finished_at'] = time.time()
                        state['timer_active'] = False

def update_state(state, team, brawler, action_type):
    """Обновляет состояние драфта"""
    
    if brawler in state['all_selected']:
        return False, 'Бравлер уже выбран'
    
    if state['phase'] == 'waiting':
        return False, 'Ожидаем готовности обеих команд'
    
    if state['phase'] == 'finished':
        return False, 'Драфт уже завершен'
    
    # Проверяем таймер
    check_timer(state)
    
    # Фаза банов (одновременно для обеих команд)
    if state['phase'] == 'ban':
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
            # Все баны сделаны вручную, переходим к пикам
            state['picking_team'] = random.choice(['blue', 'red'])
            if state['picking_team'] == 'blue':
                state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
            else:
                state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
            
            state['phase'] = 'pick'
            state['current_turn'] = state['pick_order'][0]
            state['current_pick_index'] = 0
            state['phase_start_time'] = time.time()
            state['timer_active'] = True
            print(f"✅ Все баны завершены! Начинаем фазу пиков. Первый пик: {state['current_turn']}")
    
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
        
        # Сбрасываем таймер для следующего пика
        state['phase_start_time'] = time.time()
        
        # Проверяем, завершен ли драфт
        if len(state['blue_picks']) == 3 and len(state['red_picks']) == 3:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
            state['timer_active'] = False
            print(f"🏆 Драфт завершен!")
        elif state['current_pick_index'] < len(state['pick_order']):
            state['current_turn'] = state['pick_order'][state['current_pick_index']]
            print(f"➡️ Следующий пик: {state['current_turn']} команда")
        else:
            state['phase'] = 'finished'
            state['finished_at'] = time.time()
            state['timer_active'] = False
    
    return True, 'Успешно'

def get_client_state(state, team):
    """Возвращает состояние для клиента"""
    client_state = state.copy()
    
    # Рассчитываем время до автосброса
    if state['phase'] == 'finished' and state['finished_at']:
        elapsed = time.time() - state['finished_at']
        client_state['reset_in'] = max(0, 60 - int(elapsed))
    else:
        client_state['reset_in'] = None
    
    # Рассчитываем оставшееся время на текущую фазу
    if state['phase_start_time'] and state['phase'] in ['ban', 'pick']:
        elapsed = time.time() - state['phase_start_time']
        client_state['time_left'] = max(0, state['phase_duration'] - int(elapsed))
    else:
        client_state['time_left'] = None
    
    return client_state

# Декоратор для проверки админ-доступа
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token') or session.get('admin_token')
        if not token or token != ADMIN_TOKEN:
            return jsonify({'success': False, 'error': 'Доступ запрещен'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ========== РОЛИ ==========
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

# ========== API МАРШРУТЫ ==========
@app.route('/api/state')
def get_state():
    try:
        role = request.args.get('role', 'spectator')
        room_id, state = get_or_create_state()
        
        # Проверяем автосброс
        if check_auto_reset(state):
            reset_state()
            room_id, state = get_or_create_state()
        
        # Проверяем таймер
        check_timer(state)
        
        return jsonify({
            'success': True,
            'state': get_client_state(state, role if role in ['blue', 'red'] else 'spectator'),
            'brawlers': BRWLERS,
            'role': role,
            'maps': MAPS_BY_MODE
        })
    except Exception as e:
        print(f"❌ Ошибка в /api/state: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ready', methods=['POST'])
def set_ready():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
            
        role = data.get('role', '')
        
        if role not in ['blue', 'red']:
            return jsonify({'success': False, 'error': 'Неверная роль'})
        
        room_id, state = get_or_create_state()
        
        if role == 'blue':
            state['blue_ready'] = True
            print(f"🔵 Синяя команда готова!")
        elif role == 'red':
            state['red_ready'] = True
            print(f"🔴 Красная команда готова!")
        
        state['last_action'] = time.time()
        
        # Проверяем, готовы ли обе команды
        if state['blue_ready'] and state['red_ready'] and state['phase'] == 'waiting':
            state['phase'] = 'ban'
            state['phase_start_time'] = time.time()
            state['timer_active'] = True
            print(f"🚀 Драфт начат! Фаза банов. 40 секунд на все баны!")
        
        return jsonify({
            'success': True,
            'state': get_client_state(state, role),
            'message': f'Команда {role} готова!'
        })
    except Exception as e:
        print(f"❌ Ошибка в /api/ready: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/select', methods=['POST'])
def select_brawler():
    try:
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
        
        # Проверяем автосброс
        if check_auto_reset(state):
            reset_state()
            return jsonify({'success': False, 'error': 'Драфт был сброшен по таймеру', 'auto_reset': True})
        
        success, message = update_state(state, role, brawler, 'select')
        
        if success:
            print(f"✅ {role} выбрал бравлера: {brawler}")
            return jsonify({
                'success': True,
                'message': message,
                'state': get_client_state(state, role)
            })
        else:
            return jsonify({'success': False, 'error': message})
    except Exception as e:
        print(f"❌ Ошибка в /api/select: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
@admin_required
def reset_draft():
    try:
        reset_state()
        return jsonify({
            'success': True,
            'state': get_client_state(draft_states['main'], 'spectator'),
            'message': 'Драфт сброшен!'
        })
    except Exception as e:
        print(f"❌ Ошибка в /api/reset: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def reset_state():
    """Сброс состояния драфта"""
    draft_states['main'] = {
        'blue_bans': [],
        'red_bans': [],
        'blue_picks': [],
        'red_picks': [],
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
        'auto_picks_done': [False, False, False, False, False, False]
    }
    print("🔄 Драфт сброшен")

@app.route('/api/maps')
def get_maps():
    try:
        return jsonify({
            'success': True,
            'maps': MAPS_BY_MODE,
            'modes': list(MAPS_BY_MODE.keys())
        })
    except Exception as e:
        print(f"❌ Ошибка в /api/maps: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/select_map', methods=['POST'])
@admin_required
def select_map():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
            
        map_name = data.get('map_name')
        map_mode = data.get('map_mode')
        
        room_id, state = get_or_create_state()
        
        # Проверяем, что карта существует
        if map_mode not in MAPS_BY_MODE:
            return jsonify({'success': False, 'error': 'Неверный режим'}), 404
        
        map_found = False
        for map_info in MAPS_BY_MODE[map_mode]:
            if map_info['name'] == map_name:
                state['selected_map'] = map_info
                state['selected_mode'] = map_mode
                state['last_action'] = time.time()
                map_found = True
                print(f"🗺️  Выбрана карта: {map_name} ({map_mode})")
                break
        
        if not map_found:
            return jsonify({'success': False, 'error': 'Карта не найдена'}), 404
        
        return jsonify({
            'success': True,
            'state': get_client_state(state, 'spectator'),
            'message': f'Карта {map_name} выбрана!'
        })
    except Exception as e:
        print(f"❌ Ошибка в /api/select_map: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        'admin_url': f'/admin/{ADMIN_TOKEN}'
    })

# Фавикон (чтобы не было ошибок)
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Обработчик ошибок CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*50)
    print("🎮 BRAWL STARS DRAFT SYSTEM (UPDATED)")
    print("="*50)
    print(f"🔗 Наблюдатель: http://localhost:{port}/")
    print(f"🔵 Синяя команда: http://localhost:{port}/blue")
    print(f"🔴 Красная команда: http://localhost:{port}/red")
    print(f"⚡ Администратор: http://localhost:{port}/admin/{ADMIN_TOKEN}")
    print(f"📊 Тестовая страница: http://localhost:{port}/test")
    print("="*50)
    print(f"✅ Всего бравлеров: {len(BRWLERS)}")
    print(f"✅ Режимов карт: {len(MAPS_BY_MODE)}")
    if MAPS_BY_MODE:
        for mode, maps in MAPS_BY_MODE.items():
            print(f"   • {mode}: {len(maps)} карт")
    else:
        print("⚠️  Карты не загружены! Создайте папки в static/mappool/")
    print("="*50)
    print("🆕 ОБНОВЛЕНИЯ:")
    print("   • 40 секунд на все баны (одновременно)")
    print("   • 40 секунд на каждый пик")
    print("   • Автопики/автобаны при истечении времени")
    print("   • Исправлены ошибки соединения")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=True)
