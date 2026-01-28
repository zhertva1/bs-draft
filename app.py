import os
import random
import time
from flask import Flask, render_template, jsonify, request, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

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

# Глобальное состояние драфта (в реальном приложении нужно использовать базу данных)
draft_states = {}

def get_or_create_state():
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(time.time()) + str(random.random())
        session['session_id'] = session_id
    
    if session_id not in draft_states:
        draft_states[session_id] = {
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
            'finished_at': None
        }
    
    return session_id, draft_states[session_id]

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
        return False, 'Драфт еще не начат'
    
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def start_draft():
    session_id, state = get_or_create_state()
    
    state.update({
        'blue_bans': [],
        'red_bans': [],
        'blue_picks': [],
        'red_picks': [],
        'all_selected': [],
        'phase': 'ban_blue',
        'current_turn': 'blue',
        'picking_team': None,
        'pick_order': [],
        'current_pick_index': 0,
        'last_action': time.time(),
        'finished_at': None
    })
    
    return jsonify({'success': True, 'state': get_client_state(state, 'spectator')})

@app.route('/api/reset', methods=['POST'])
def reset_draft():
    session_id, state = get_or_create_state()
    
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
        'finished_at': None
    })
    
    return jsonify({'success': True, 'state': get_client_state(state, 'spectator')})

@app.route('/api/select', methods=['POST'])
def select_brawler():
    data = request.json
    brawler = data.get('brawler', '').strip()
    team = data.get('team', '')
    
    if not brawler or not team or team not in ['blue', 'red']:
        return jsonify({'success': False, 'error': 'Неверные данные'})
    
    if brawler not in BRWLERS:
        return jsonify({'success': False, 'error': 'Бравлер не найден'})
    
    session_id, state = get_or_create_state()
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_draft()
        return jsonify({'success': False, 'error': 'Драфт был сброшен по таймеру', 'auto_reset': True})
    
    success, message = update_state(state, team, brawler, 'select')
    
    if success:
        return jsonify({
            'success': True,
            'message': message,
            'state': get_client_state(state, team)
        })
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/api/state')
def get_state():
    team = request.args.get('team', 'spectator')
    session_id, state = get_or_create_state()
    
    # Проверяем автосброс
    if check_auto_reset(state):
        reset_draft()
        session_id, state = get_or_create_state()
    
    return jsonify({
        'success': True,
        'state': get_client_state(state, team),
        'brawlers': BRWLERS
    })

@app.route('/api/brawlers')
def get_brawlers():
    return jsonify({'brawlers': BRWLERS})

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
