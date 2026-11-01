import os
from flask import Flask, request
import hmac
import base64
import datetime
import requests
import threading

app = Flask(__name__)

API_KEY = os.environ.get("OKX_API_KEY")
SECRET_KEY = os.environ.get("OKX_SECRET_KEY")
PASSPHRASE = os.environ.get("OKX_PASSPHRASE")
IS_DEMO = True  # Zmień na False, gdy przejdziesz z konta Demo na prawdziwe środki!

# POPRAWKA: OKX używa tej samej domeny dla Live i Demo. O Demo decyduje nagłówek.
OKX_URL = "https://www.okx.com"

def get_timestamp():
    return datetime.datetime.utcnow().isoformat()[:-3] + "Z"

def generate_signature(timestamp, method, request_path, body=""):
    message = timestamp + method + request_path + body
    mac = hmac.new(bytes(SECRET_KEY, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    return base64.b64encode(mac.digest()).decode('utf-8')

def okx_request(method, path, data=None):
    timestamp = get_timestamp()
    body = str(data) if data else ""
    signature = generate_signature(timestamp, method, path, body)
    
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    if IS_DEMO:
        headers["x-simulated-trading"] = "1"
        
    url = OKX_URL + path
    
    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            response = requests.get(url, headers=headers)
            
        # Zabezpieczenie przed JSONDecodeError - sprawdzamy status odpowiedzi
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[OKX] Serwer zwrócił błąd HTTP {response.status_code}: {response.text}")
            return {"error": response.text}
            
    except Exception as e:
        print(f"[Błąd sieciowy]: {e}")
        return {"error": str(e)}

def process_trade_in_background(data):
    """Ta funkcja wykonuje się w osobnym wątku w tle. 
    TradingView nie musi na nią czekać."""
    print("Rozpoczynam przetwarzanie sygnału w tle...")
    
    # Przykładowe przygotowanie zlecenia rynkowego (Market Order) dla OKX
    # Ścieżka API OKX do składania zleceń to: /api/v5/trade/order
    # Alert z TradingView musi wysyłać odpowiedni format JSON
    path = "/api/v5/trade/order"
    
    # Przykładowy payload, dostosuj pod swoje zmienne z TradingView
    order_data = {
        "instId": data.get("ticker", "BTC-USDT"),
        "tdMode": "cash", # lub "cross" / "isolated" dla dźwigni
        "side": data.get("action", "buy"),
        "ordType": "market",
        "sz": str(data.get("size", "0.001"))
    }
    
    # Wysyłamy zapytanie do OKX
    result = okx_request("POST", path, order_data)
    print("Wynik zlecenia OKX:", result)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Otrzymano sygnał z TradingView:", data)
    
    # Uruchamiamy proces zawierający zapytania do OKX w osobnym wątku (w tle)
    threading.Thread(target=process_trade_in_background, args=(data,)).start()
    
    # Natychmiast zwracamy odpowiedź do TradingView, zapobiegając timeoutom
    return "Sygnał przekazany do realizacji", 200

@app.route('/', methods=['GET'])
def health_check():
    """Dodatkowy endpoint do utrzymywania serwera Render przy życiu"""
    return "Serwer działa", 200

    action = data.get("action", "")
    
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
        return jsonify({"status": "Otwarte automatycznie", "okx_response": result})
        
    # 3. Awaryjne automatyczne zamknięcie (jeśli nie zamkniesz ręcznie)
    elif action == "EXIT_LONG":
        close_data = {
            "instId": "BTC-USD-SWAP",
            "mgnMode": "isolated"
        }
        result = okx_request("POST", "/trade/close-position", close_data)
        return jsonify({"status": "Zamknięte automatycznie", "okx_response": result})
        
    return jsonify({"status": "error", "message": "Nieznana akcja"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
