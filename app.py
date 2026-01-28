from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Начальное состояние
def get_initial_state():
    return {
        "phase": "ban",
        "turn_index": 0,
        "picking_order": [],
        "temp_bans": {"blue": [], "red": []},
        "blue_bans": [],
        "red_bans": [],
        "blue_picks": [],
        "red_picks": [],
        "all_selected": []
    }

draft_data = get_initial_state()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # При подключении сразу отправляем текущие данные
    emit('update_draft', draft_data)

@socketio.on('reset_draft')
def handle_reset():
    global draft_data
    draft_data = get_initial_state()
    emit('update_draft', draft_data, broadcast=True)
    print("Драфт сброшен")

@socketio.on('select_brawler')
def handle_selection(data):
    global draft_data
    brawler = data['brawler']
    team = data['team']
    print(f"Попытка выбора: {team} -> {brawler}")

    if brawler in draft_data['all_selected']:
        return

    if draft_data['phase'] == "ban":
        if len(draft_data['temp_bans'][team]) < 3:
            if brawler not in draft_data['temp_bans'][team]:
                draft_data['temp_bans'][team].append(brawler)
                emit('my_temp_bans', draft_data['temp_bans'][team])
                print(f"Бан принят: {team} ({len(draft_data['temp_bans'][team])}/3)")

        if len(draft_data['temp_bans']['blue']) == 3 and len(draft_data['temp_bans']['red']) == 3:
            draft_data['blue_bans'] = draft_data['temp_bans']['blue']
            draft_data['red_bans'] = draft_data['temp_bans']['red']
            draft_data['all_selected'] = draft_data['blue_bans'] + draft_data['red_bans']
            draft_data['phase'] = "pick"
            
            first = random.choice(["blue", "red"])
            second = "red" if first == "blue" else "blue"
            draft_data['picking_order'] = [first, second, second, first, first, second]
            draft_data['turn_index'] = 0
            emit('update_draft', draft_data, broadcast=True)

    elif draft_data['phase'] == "pick":
        current_turn_team = draft_data['picking_order'][draft_data['turn_index']]
        if team == current_turn_team:
            draft_data[f"{team}_picks"].append(brawler)
            draft_data['all_selected'].append(brawler)
            draft_data['turn_index'] += 1
            if draft_data['turn_index'] >= len(draft_data['picking_order']):
                draft_data['phase'] = "finished"
            emit('update_draft', draft_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, port=5000, debug=True)
