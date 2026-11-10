import os
from flask import Flask, request, jsonify
import hmac
import base64
import datetime
import requests
import json  
import threading

app = Flask(__name__)

API_KEY = os.environ.get("OKX_API_KEY")
SECRET_KEY = os.environ.get("OKX_SECRET_KEY")
PASSPHRASE = os.environ.get("OKX_PASSPHRASE")

# PRZEŁĄCZONE NA LIVE
IS_DEMO = False  

# Prawidłowy adres bazowy dla Europy
OKX_URL = "https://eea.okx.com"

def get_timestamp():
    return datetime.datetime.utcnow().isoformat()[:-3] + "Z"

def generate_signature(timestamp, method, request_path, body=""):
    message = timestamp + method + request_path + body
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    return base64.b64encode(mac.digest()).decode('utf-8')

def okx_request(method, path, data=None):
    timestamp = get_timestamp()
    
    # OKX wymaga pełnej ścieżki zaczynającej się od /api/v5/
    full_path = f"/api/v5{path}"
    
    # Prawidłowe kodowanie JSON dla metody POST
    body = json.dumps(data) if (data and method == "POST") else ""
    
    # Dla metody GET parametry przekazuje się w URL, body musi być puste
    signature = generate_signature(timestamp, method, full_path, body)
    
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
        
    url = OKX_URL + full_path
    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            # Dla GET dodajemy ewentualne parametry do urla
            response = requests.get(url, params=data, headers=headers)
            
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[OKX LIVE BŁĄD HTTP {response.status_code}]: {response.text}")
            return {"error": response.text}
    except Exception as e:
        print(f"[BŁĄD SIECIOWY OKX LIVE]: {str(e)}")
        return {"error": str(e)}

def execute_trade_in_background(data):
    """Ta funkcja wykonuje się w tle. TradingView już o niej nie wie i nie czeka."""
    action = data.get("action", "")
    inst_id = "BTC-USD_UM_XPERP-040431"
    print(f"[LIVE-TŁO] Rozpoczynam przetwarzanie akcji: {action}")
    
    # 1. Ustawienie dźwigni 5x na izolowanym depozycie
    leverage_data = {
        "instId": inst_id,
        "lever": "8",
        "mgnMode": "isolated"
    }
    okx_request("POST", "/account/set-leverage", leverage_data)
    
    # 2. Reakcja na sygnał wejścia
    if action == "ENTER_LONG":
        order_data = {
            "instId": inst_id,
            "tdMode": "isolated",
            "side": "buy",
            "ordType": "market",
            "sz": "2"  # 1 kontrakt = 100 USD wartości pozycji
        }
        result = okx_request("POST", "/trade/order", order_data)
        print("[LIVE-TŁO] Wynik otwarcia pozycji:", result)
        
    # 3. Zabezpieczone automatyczne zamknięcie
    elif action == "EXIT_LONG":
        print("[LIVE-TŁO] Sprawdzam, czy pozycja istnieje przed zamknięciem...")
        
        # Pobieramy aktualne pozycje z giełdy (Metoda GET)
        pos_check = okx_request("GET", "/account/positions", {"instId": inst_id})
        
        # Filtrujemy dane w poszukiwaniu aktywnej pozycji
        active_positions = pos_check.get("data", []) if isinstance(pos_check, dict) else []
        
        # Jeśli lista pozycji jest pusta lub rozmiar wynosi 0
        has_position = False
        for pos in active_positions:
            if pos.get("instId") == inst_id and float(pos.get("pos", 0)) > 0:
                has_position = True
                break
                
        if not has_position:
            print(f"[LIVE-TŁO] Brak otwartej pozycji dla {inst_id} na giełdzie. Ignoruję powtórny sygnał EXIT z TradingView.")
            return

        # Jeśli pozycja istnieje, bezpiecznie ją zamykamy
        close_data = {
            "instId": inst_id,
            "mgnMode": "isolated"
        }
        result = okx_request("POST", "/trade/close-position", close_data)
        print("[LIVE-TŁO] Wynik zamknięcia pozycji:", result)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Otrzymano sygnał z TradingView:", data)
    
    if not data:
        return jsonify({"status": "error", "message": "Pusty payload JSON"}), 400

    threading.Thread(target=execute_trade_in_background, args=(data,)).start()
    return jsonify({"status": "Sygnał przyjęty do realizacji w tle na koncie LIVE"}), 200

@app.route('/', methods=['GET'])
def health_check():
    return "Bot LIVE is alive", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
