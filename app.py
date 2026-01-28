import pygame
import os
import random
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import eventlet
import time
import threading

# Инициализация Flask и SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet')

# Папка с картинками
IMAGE_FOLDER = 'static/brawler_images'

# Получаем список бравлеров из папки
def get_brawlers_list():
    if not os.path.exists(IMAGE_FOLDER):
        print(f"Папка '{IMAGE_FOLDER}' не найдена!")
        return []
    
    brawlers = []
    for f in os.listdir(IMAGE_FOLDER):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            brawlers.append(f.rsplit('.', 1)[0])
    
    print(f"Найдено бравлеров: {len(brawlers)}")
    return sorted(brawlers)

# Глобальное состояние драфта
draft_state = {
    'blue_bans': [],
    'blue_picks': [],
    'red_bans': [],
    'red_picks': [],
    'all_selected': [],
    'phase': 'waiting',  # waiting, ban, pick, finished
    'picking_order': ['blue', 'red'],  # пример порядка
    'turn_index': 0,
    'last_action_time': None,
    'reset_timer': None
}

BRWLERS = get_brawlers_list()

# Таймер для сброса
def check_reset_timer():
    while True:
        time.sleep(1)
        if draft_state['phase'] == 'finished' and draft_state['last_action_time']:
            elapsed = time.time() - draft_state['last_action_time']
            if elapsed > 60:  # 60 секунд = 1 минута
                reset_draft()
        time.sleep(4)

def reset_draft():
    """Сброс драфта в начальное состояние"""
    draft_state.update({
        'blue_bans': [],
        'blue_picks': [],
        'red_bans': [],
        'red_picks': [],
        'all_selected': [],
        'phase': 'waiting',
        'turn_index': 0,
        'last_action_time': None
    })
    print("Драфт сброшен по таймеру (прошла 1 минута)")
    socketio.emit('update_draft', draft_state)
    socketio.emit('reset_timer')

# Запуск таймера в отдельном потоке
timer_thread = threading.Thread(target=check_reset_timer, daemon=True)
timer_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/brawler_images/<path:filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)

@socketio.on('connect')
def handle_connect():
    print(f'Клиент подключился')
    emit('brawlers_list', BRWLERS)
    emit('update_draft', draft_state)

@socketio.on('join')
def handle_join(data):
    team = data.get('team', 'spectator')
    print(f'Игрок присоединился к команде: {team}')
    emit('update_draft', draft_state)

@socketio.on('select_brawler')
def handle_select(data):
    brawler = data.get('brawler')
    team = data.get('team')
    
    if not brawler or not team:
        return
    
    if brawler in draft_state['all_selected']:
        print(f"Бравлер {brawler} уже выбран")
        return
    
    # Логика выбора (упрощенная версия)
    if team == 'blue':
        if len(draft_state['blue_bans']) < 3:
            draft_state['blue_bans'].append(brawler)
        elif len(draft_state['blue_picks']) < 3:
            draft_state['blue_picks'].append(brawler)
    elif team == 'red':
        if len(draft_state['red_bans']) < 3:
            draft_state['red_bans'].append(brawler)
        elif len(draft_state['red_picks']) < 3:
            draft_state['red_picks'].append(brawler)
    
    draft_state['all_selected'].append(brawler)
    draft_state['last_action_time'] = time.time()
    
    # Проверяем, завершен ли драфт
    if (len(draft_state['blue_picks']) == 3 and 
        len(draft_state['red_picks']) == 3):
        draft_state['phase'] = 'finished'
        draft_state['last_action_time'] = time.time()
    
    socketio.emit('update_draft', draft_state)

@socketio.on('reset_draft_manual')
def handle_reset():
    reset_draft()

if __name__ == '__main__':
    print(f"Сервер запущен. Доступно бравлеров: {len(BRWLERS)}")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
