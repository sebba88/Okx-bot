import os
from flask import Flask, request, jsonify
import hmac
import base64
import datetime
import requests
import json  # Potrzebne do prawidłowego formatowania JSON dla OKX
import threading

app = Flask(__name__)

API_KEY = os.environ.get("OKX_API_KEY")
SECRET_KEY = os.environ.get("OKX_SECRET_KEY")
PASSPHRASE = os.environ.get("OKX_PASSPHRASE")

# PRZEŁĄCZONE NA LIVE
IS_DEMO = False  

# Adres URL dla prawdziwych środków
OKX_URL = "https://eea.okx.com"

def get_timestamp():
    return datetime.datetime.utcnow().isoformat()[:-3] + "Z"

def generate_signature(timestamp, method, request_path, body=""):
    message = timestamp + method + request_path + body
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    return base64.b64encode(mac.digest()).decode('utf-8')

def okx_request(method, path, data=None):
    timestamp = get_timestamp()
    
    # Prawidłowe kodowanie JSON z podwójnymi cudzysłowami dla OKX
    body = json.dumps(data) if data else ""
    
    signature = generate_signature(timestamp, method, path, body)
    
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    # Nagłówek x-simulated-trading został usunięty, ponieważ przechodzimy na LIVE
        
    url = OKX_URL + path
    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            response = requests.get(url, headers=headers)
            
        # Bezpieczne dekodowanie odpowiedzi, zapobiega crashom bota
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
    print(f"[LIVE-TŁO] Rozpoczynam przetwarzanie akcji: {action}")
    
    # 1. Ustawienie dźwigni 5x na izolowanym depozycie
    leverage_data = {
        "instId": "BTC-USD-SWAP",
        "lever": "5",
        "mgnMode": "isolated"
    }
    okx_request("POST", "/account/set-leverage", leverage_data)
    
    # 2. Reakcja na sygnał wejścia
    if action == "ENTER_LONG":
        order_data = {
            "instId": "BTC-USD-SWAP",
            "tdMode": "isolated",
            "side": "buy",
            "ordType": "market",
            "sz": "1"  # 1 kontrakt = 100 USD wartości pozycji
        }
        result = okx_request("POST", "/trade/order", order_data)
        print("[LIVE-TŁO] Wynik otwarcia pozycji:", result)
        
    # 3. Awaryjne automatyczne zamknięcie
    elif action == "EXIT_LONG":
        close_data = {
            "instId": "BTC-USD-SWAP",
            "mgnMode": "isolated"
        }
        result = okx_request("POST", "/trade/close-position", close_data)
        print("[LIVE-TŁO] Wynik zamknięcia pozycji:", result)

@app.route('/webhook', methods=['POST'])
def webhook():
    # Pobranie danych i natychmiastowe logowanie
    data = request.json
    print("Otrzymano sygnał z TradingView:", data)
    
    if not data:
        return jsonify({"status": "error", "message": "Pusty payload JSON"}), 400

    # URUCHOMIENIE W TLE: Przekazujemy robotę do osobnego wątku
    threading.Thread(target=execute_trade_in_background, args=(data,)).start()
    
    # NATYCHMIASTOWA ODPOWIEDŹ: TradingView dostaje odpowiedź w < 10 ms i nie zgłasza timeoutu
    return jsonify({"status": "Sygnał przyjęty do realizacji w tle na koncie LIVE"}), 200

@app.route('/', methods=['GET'])
def health_check():
    """Prosty endpoint do sprawdzania czy bot żyje (np. dla UptimeRobot)"""
    return "Bot LIVE is alive", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
