import os
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
            if filename.lower().endswith('.png'):
                name = os.path.splitext(filename)[0]
                brawlers.append(name)
    
    return sorted(brawlers)

BRWLERS = get_brawlers_list()
print(f"✅ Найдено бравлеров: {len(BRWLERS)}")

# Простое состояние драфта
draft_state = {
    'blue_bans': [], 'blue_picks': [],
    'red_bans': [], 'red_picks': [],
    'all_selected': [], 'phase': 'waiting'
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/brawlers')
def api_brawlers():
    return jsonify(BRWLERS)

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'brawlers': len(BRWLERS)})

@socketio.on('connect')
def handle_connect():
    print('Клиент подключился')
    emit('brawlers_list', BRWLERS)
    emit('update_draft', draft_state)

@socketio.on('select_brawler')
def handle_select(data):
    brawler = data.get('brawler')
    team = data.get('team')
    
    if not brawler or not team:
        return
    
    if brawler in draft_state['all_selected']:
        return
    
    # Простая логика выбора
    if team == 'blue':
        if len(draft_state['blue_bans']) < 3:
            draft_state['blue_bans'].append(brawler)
        elif len(draft_state['blue_picks']) < 3:
            draft_state['blue_picks'].append(brawler)
    else:
        if len(draft_state['red_bans']) < 3:
            draft_state['red_bans'].append(brawler)
        elif len(draft_state['red_picks']) < 3:
            draft_state['red_picks'].append(brawler)
    
    draft_state['all_selected'].append(brawler)
    
    # Если обе команды выбрали по 3 пика - драфт завершен
    if len(draft_state['blue_picks']) == 3 and len(draft_state['red_picks']) == 3:
        draft_state['phase'] = 'finished'
    
    emit('update_draft', draft_state, broadcast=True)

@socketio.on('reset_draft')
def handle_reset():
    global draft_state
    draft_state = {
        'blue_bans': [], 'blue_picks': [],
        'red_bans': [], 'red_picks': [],
        'all_selected': [], 'phase': 'waiting'
    }
    emit('draft_reset', broadcast=True)
    emit('update_draft', draft_state, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
