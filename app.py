import os
import random
import time
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, send_from_directory

app = Flask(__name__)
app.secret_key = 'draft-secret-key-2024-brawl-stars'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Конфигурация
ADMIN_SECRET = 'BS-DRAFT-ADMIN-2024-SUPER-SECRET-KEY'
IMAGE_FOLDER = os.path.join(app.static_folder, 'brawler_images')
MAPPOOL_FOLDER = os.path.join(app.static_folder, 'mappool')
MODES_FOLDER = os.path.join(app.static_folder, 'modes')

# Глобальное состояние драфта (в продакшене используйте Redis или базу данных)
draft_state = {
    'blue_bans': [],
    'red_bans': [],
    'blue_picks': [],
    'red_picks': [],
    'all_selected': [],
    'phase': 'waiting',  # waiting, ban_blue, ban_red, pick, finished
    'current_turn': None,
    'picking_team': None,
    'pick_order': [],
    'current_pick_index': 0,
    'blue_ready': False,
    'red_ready': False,
    'selected_map': None,
    'selected_mode': None,
    'start_time': None,
    'finished_at': None,
    'admin_connected': False
}

# Блокировка для потокобезопасности (в продакшене используйте более надежное решение)
import threading
state_lock = threading.Lock()

def get_brawlers_list():
    """Получаем список бравлеров из папки"""
    if not os.path.exists(IMAGE_FOLDER):
        return []
    
    brawlers = []
    for filename in os.listdir(IMAGE_FOLDER):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            name = os.path.splitext(filename)[0]
            brawlers.append(name)
    
    return sorted(brawlers, key=lambda x: x.lower())

def get_maps_list():
    """Получаем список всех карт из mappool"""
    maps = {}
    
    if os.path.exists(MAPPOOL_FOLDER):
        for mode_folder in os.listdir(MAPPOOL_FOLDER):
            mode_path = os.path.join(MAPPOOL_FOLDER, mode_folder)
            if os.path.isdir(mode_path):
                mode_maps = []
                for map_file in os.listdir(mode_path):
                    if map_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        map_name = os.path.splitext(map_file)[0]
                        mode_maps.append({
                            'name': map_name,
                            'filename': map_file,
                            'mode': mode_folder
                        })
                
                if mode_maps:
                    maps[mode_folder] = sorted(mode_maps, key=lambda x: x['name'])
    
    return maps

def get_modes_list():
    """Получаем список режимов"""
    modes = []
    
    if os.path.exists(MODES_FOLDER):
        for mode_file in os.listdir(MODES_FOLDER):
            if mode_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                mode_name = os.path.splitext(mode_file)[0]
                modes.append({
                    'name': mode_name,
                    'filename': mode_file
                })
    
    return sorted(modes, key=lambda x: x['name'])

BRWLERS = get_brawlers_list()
MAPS = get_maps_list()
MODES = get_modes_list()

def reset_draft_state():
    """Сброс состояния драфта"""
    with state_lock:
        draft_state.update({
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
            'blue_ready': False,
            'red_ready': False,
            'start_time': None,
            'finished_at': None
            # Не сбрасываем selected_map и selected_mode
        })

def check_auto_reset():
    """Проверка автоматического сброса"""
    with state_lock:
        if draft_state['phase'] == 'finished' and draft_state['finished_at']:
            elapsed = time.time() - draft_state['finished_at']
            return elapsed > 60  # 1 минута
    return False

def get_client_state(team=None):
    """Получаем состояние для клиента"""
    with state_lock:
        client_state = draft_state.copy()
        
        # Скрываем баны противника во время фазы банов
        if 'ban' in client_state['phase'] and team in ['blue', 'red']:
            if team == 'blue':
                client_state['red_bans'] = ['hidden'] * len(draft_state['red_bans'])
            else:
                client_state['blue_bans'] = ['hidden'] * len(draft_state['blue_bans'])
        
        # Рассчитываем время до автосброса
        if client_state['phase'] == 'finished' and client_state['finished_at']:
            elapsed = time.time() - client_state['finished_at']
            client_state['reset_in'] = max(0, 60 - int(elapsed))
        else:
            client_state['reset_in'] = None
        
        # Проверяем готовность к началу
        client_state['can_start'] = (
            draft_state['blue_ready'] and 
            draft_state['red_ready'] and
            draft_state['selected_map'] is not None
        )
        
        # Проверяем автосброс
        if check_auto_reset():
            reset_draft_state()
            client_state.update(draft_state.copy())
        
        return client_state

@app.route('/')
def index():
    """Главная страница"""
    # Определяем роль пользователя по параметрам URL
    team = request.args.get('team', '').lower()
    admin_key = request.args.get('admin', '')
    
    is_admin = (admin_key == ADMIN_SECRET)
    
    # Если указана команда, проверяем корректность
    if team not in ['blue', 'red']:
        team = None
    
    return render_template('index.html', team=team, is_admin=is_admin)

@app.route('/api/ready', methods=['POST'])
def set_ready():
    """Установка готовности команды"""
    data = request.json
    team = data.get('team')
    
    if team not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Invalid team'})
    
    with state_lock:
        if team == 'blue':
            draft_state['blue_ready'] = True
        else:
            draft_state['red_ready'] = True
        
        # Если обе команды готовы и карта выбрана, начинаем драфт
        if (draft_state['blue_ready'] and 
            draft_state['red_ready'] and 
            draft_state['selected_map'] is not None and
            draft_state['phase'] == 'waiting'):
            
            draft_state['phase'] = 'ban_blue'
            draft_state['current_turn'] = 'blue'
            draft_state['start_time'] = time.time()
    
    return jsonify({'success': True, 'state': get_client_state(team)})

@app.route('/api/unready', methods=['POST'])
def set_unready():
    """Сброс готовности команды"""
    data = request.json
    team = data.get('team')
    
    if team not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Invalid team'})
    
    with state_lock:
        if team == 'blue':
            draft_state['blue_ready'] = False
        else:
            draft_state['red_ready'] = False
        
        # Если драфт еще не начался, сбрасываем все
        if draft_state['phase'] == 'waiting':
            reset_draft_state()
    
    return jsonify({'success': True, 'state': get_client_state(team)})

@app.route('/api/select-map', methods=['POST'])
def select_map():
    """Выбор карты (только для админа)"""
    data = request.json
    admin_key = data.get('admin_key')
    map_name = data.get('map_name')
    map_mode = data.get('map_mode')
    
    if admin_key != ADMIN_SECRET:
        return jsonify({'success': False, 'error': 'Access denied'})
    
    # Проверяем существование карты
    map_found = False
    if map_mode in MAPS:
        for map_info in MAPS[map_mode]:
            if map_info['name'] == map_name:
                map_found = True
                break
    
    if not map_found:
        return jsonify({'success': False, 'error': 'Map not found'})
    
    with state_lock:
        draft_state['selected_map'] = {
            'name': map_name,
            'mode': map_mode,
            'filename': f"{map_name}.png"
        }
        draft_state['selected_mode'] = map_mode
    
    return jsonify({'success': True, 'state': get_client_state()})

@app.route('/api/select-brawler', methods=['POST'])
def select_brawler():
    """Выбор бравлера"""
    data = request.json
    brawler = data.get('brawler', '').strip()
    team = data.get('team')
    
    if team not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Invalid team'})
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Brawler not found'})
    
    with state_lock:
        # Проверяем автосброс
        if check_auto_reset():
            reset_draft_state()
            return jsonify({'success': False, 'error': 'Draft was auto-reset', 'auto_reset': True})
        
        # Проверяем, можно ли выбрать бравлера
        if brawler in draft_state['all_selected']:
            return jsonify({'success': False, 'error': 'Brawler already selected'})
        
        # Проверяем фазу драфта
        if draft_state['phase'] == 'waiting':
            return jsonify({'success': False, 'error': 'Draft not started yet'})
        
        if draft_state['phase'] == 'finished':
            return jsonify({'success': False, 'error': 'Draft already finished'})
        
        # Фаза банов
        if 'ban' in draft_state['phase']:
            # Проверяем очередь
            if draft_state['current_turn'] != team:
                return jsonify({'success': False, 'error': 'Not your turn'})
            
            # Добавляем бан
            if team == 'blue' and len(draft_state['blue_bans']) < 3:
                draft_state['blue_bans'].append(brawler)
            elif team == 'red' and len(draft_state['red_bans']) < 3:
                draft_state['red_bans'].append(brawler)
            else:
                return jsonify({'success': False, 'error': 'All bans already made'})
            
            draft_state['all_selected'].append(brawler)
            
            # Проверяем завершение банов
            blue_bans_done = len(draft_state['blue_bans']) == 3
            red_bans_done = len(draft_state['red_bans']) == 3
            
            if blue_bans_done and red_bans_done:
                # Все баны сделаны, переходим к пикам
                draft_state['picking_team'] = random.choice(['blue', 'red'])
                
                # Устанавливаем порядок пиков
                if draft_state['picking_team'] == 'blue':
                    draft_state['pick_order'] = ['blue', 'red', 'red', 'blue', 'blue', 'red']
                else:
                    draft_state['pick_order'] = ['red', 'blue', 'blue', 'red', 'red', 'blue']
                
                draft_state['phase'] = 'pick'
                draft_state['current_turn'] = draft_state['pick_order'][0]
                draft_state['current_pick_index'] = 0
            
            elif draft_state['phase'] == 'ban_blue' and blue_bans_done:
                draft_state['phase'] = 'ban_red'
                draft_state['current_turn'] = 'red'
            
            elif draft_state['phase'] == 'ban_red' and red_bans_done:
                draft_state['phase'] = 'ban_blue'
                draft_state['current_turn'] = 'blue'
        
        # Фаза пиков
        elif draft_state['phase'] == 'pick':
            # Проверяем очередь
            if draft_state['current_turn'] != team:
                return jsonify({'success': False, 'error': 'Not your turn'})
            
            # Добавляем пик
            if team == 'blue' and len(draft_state['blue_picks']) < 3:
                draft_state['blue_picks'].append(brawler)
            elif team == 'red' and len(draft_state['red_picks']) < 3:
                draft_state['red_picks'].append(brawler)
            else:
                return jsonify({'success': False, 'error': 'All picks already made'})
            
            draft_state['all_selected'].append(brawler)
            
            # Переходим к следующему пику
            draft_state['current_pick_index'] += 1
            
            # Проверяем завершение драфта
            if len(draft_state['blue_picks']) == 3 and len(draft_state['red_picks']) == 3:
                draft_state['phase'] = 'finished'
                draft_state['finished_at'] = time.time()
            elif draft_state['current_pick_index'] < len(draft_state['pick_order']):
                draft_state['current_turn'] = draft_state['pick_order'][draft_state['current_pick_index']]
            else:
                draft_state['phase'] = 'finished'
                draft_state['finished_at'] = time.time()
    
    return jsonify({'success': True, 'state': get_client_state(team)})

@app.route('/api/reset', methods=['POST'])
def reset_draft():
    """Полный сброс драфта"""
    data = request.json
    admin_key = data.get('admin_key', '')
    
    # Только админ может сбросить драфт
    if admin_key != ADMIN_SECRET:
        return jsonify({'success': False, 'error': 'Access denied'})
    
    reset_draft_state()
    
    return jsonify({'success': True, 'state': get_client_state()})

@app.route('/api/state')
def get_state():
    """Получение текущего состояния"""
    team = request.args.get('team', '').lower()
    
    if team not in ['blue', 'red']:
        team = None
    
    return jsonify({
        'success': True,
        'state': get_client_state(team),
        'brawlers': BRWLERS,
        'maps': MAPS,
        'modes': MODES
    })

@app.route('/api/auto-reset-check')
def auto_reset_check():
    """Проверка автосброса"""
    if check_auto_reset():
        reset_draft_state()
        return jsonify({'auto_reset': True, 'state': get_client_state()})
    
    return jsonify({'auto_reset': False})

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Сервис статических файлов"""
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Сервер запущен на порту {port}")
    print(f"✅ Бравлеров: {len(BRWLERS)}")
    print(f"🗺️  Режимов карт: {len(MAPS)}")
    print(f"🔑 Админская ссылка: http://localhost:{port}/?admin={ADMIN_SECRET}")
    print(f"🔵 Синяя команда: http://localhost:{port}/?team=blue")
    print(f"🔴 Красная команда: http://localhost:{port}/?team=red")
    app.run(host='0.0.0.0', port=port, debug=False)
