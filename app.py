from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Состояние
draft_data = {
    "phase": "waiting", # waiting, ban, pick, finished
    "captains": {"blue": False, "red": False},
    "temp_bans": {"blue": [], "red": []},
    "blue_bans": [None, None, None],
    "red_bans": [None, None, None],
    "blue_picks": [None, None, None],
    "red_picks": [None, None, None],
    "picking_order": [],
    "turn_index": 0,
    "all_selected": []
}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('join')
def on_join(data):
    team = data.get('team')
    if team in ['blue', 'red']:
        draft_data['captains'][team] = True
        print(f"Капитан {team} зашел")
    
    # Если оба зашли — начинаем баны
    if draft_data['captains']['blue'] and draft_data['captains']['red'] and draft_data['phase'] == "waiting":
        draft_data['phase'] = "ban"
    
    emit('update_draft', draft_data, broadcast=True)

@socketio.on('select_brawler')
def handle_selection(data):
    global draft_data
    brawler = data['brawler']
    team = data['team']
    
    if draft_data['phase'] == "waiting" or brawler in draft_data['all_selected']:
        return

    # Фаза банов
    if draft_data['phase'] == "ban":
        if len(draft_data['temp_bans'][team]) < 3:
            if brawler not in draft_data['temp_bans'][team]:
                draft_data['temp_bans'][team].append(brawler)
                emit('my_temp_bans', draft_data['temp_bans'][team])

        if len(draft_data['temp_bans']['blue']) == 3 and len(draft_data['temp_bans']['red']) == 3:
            draft_data['blue_bans'] = draft_data['temp_bans']['blue']
            draft_data['red_bans'] = draft_data['temp_bans']['red']
            draft_data['all_selected'] = draft_data['blue_bans'] + draft_data['red_bans']
            draft_data['phase'] = "pick"
            first = random.choice(["blue", "red"])
            second = "red" if first == "blue" else "blue"
            draft_data['picking_order'] = [first, second, second, first, first, second]
            emit('update_draft', draft_data, broadcast=True)

    # Фаза пиков
    elif draft_data['phase'] == "pick":
        current_turn_team = draft_data['picking_order'][draft_data['turn_index']]
        if team == current_turn_team:
            # Ищем первый пустой слот в пиках
            picks = draft_data[f"{team}_picks"]
            for i in range(3):
                if picks[i] is None:
                    picks[i] = brawler
                    break
            
            draft_data['all_selected'].append(brawler)
            draft_data['turn_index'] += 1
            if draft_data['turn_index'] >= 6:
                draft_data['phase'] = "finished"
            emit('update_draft', draft_data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
