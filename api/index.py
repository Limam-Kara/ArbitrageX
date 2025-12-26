from flask import Flask, request, jsonify
from flask_cors import CORS  # Imported
from .quotes import (
    get_sendwave_quote,
    get_westernunion_quote,
    get_worldremit_quote,
    get_remitly_quote,
    get_taptap_quote,
    get_wise_quote,
)

app = Flask(__name__)
CORS(app)  # <--- CRITICAL: This line was missing! Enables access from frontend.

# Serve the frontend (or just status check)
@app.route("/")
def index():
    return "API is running!"

# JSON API
@app.route("/api/quotes")  # Changed to @app.route (safer generic decorator)
def api_quotes():
    try:
        amount = float(request.args.get("amount", 100))
        send_curr = request.args.get("sendCurr", "USD")
        recv_curr = request.args.get("recvCurr", "MAD")
        send_cty = request.args.get("sendCty", "US")
        recv_cty = request.args.get("recvCty", "MA")

        quotes = []

        # Single-result providers
        for p in [get_remitly_quote, get_taptap_quote, get_wise_quote]:
            try:
                res = (
                    p(amount, send_curr, recv_curr, send_cty, recv_cty)
                    if p != get_wise_quote
                    else p(amount, send_curr, recv_curr, send_cty)
                )
                if res:
                    quotes.append(res)
            except Exception as e:
                print(f"Error fetching from provider: {e}")
                continue

        # Multi-result providers
        for p_multi in [get_westernunion_quote, get_worldremit_quote, get_sendwave_quote]:
            try:
                res_list = p_multi(amount, send_curr, recv_curr, send_cty, recv_cty)
                if res_list:
                    quotes.extend(res_list)
            except Exception as e:
                print(f"Error fetching from multi-provider: {e}")
                continue

        return jsonify(quotes)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Vercel ignores this block, but good for local testing
if __name__ == "__main__":
    app.run(debug=True)
