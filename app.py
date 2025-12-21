from flask import Flask, request, jsonify, send_from_directory
from quotes import (
    get_sendwave_quote,
    get_westernunion_quote,
    get_worldremit_quote,
    get_remitly_quote,
    get_taptap_quote,
    get_wise_quote,
)

app = Flask(__name__, static_folder=".", static_url_path="")

# Serve the frontend
@app.get("/")
def index():
    return send_from_directory(".", "index.html")

# JSON API
@app.get("/api/quotes")
def api_quotes():
    amount = float(request.args.get("amount", 100))
    send_curr = request.args.get("sendCurr", "USD")
    recv_curr = request.args.get("recvCurr", "MAD")
    send_cty = request.args.get("sendCty", "US")
    recv_cty = request.args.get("recvCty", "MA")

    quotes = []

    for p in [get_remitly_quote, get_taptap_quote, get_wise_quote]:
        res = (
            p(amount, send_curr, recv_curr, send_cty, recv_cty)
            if p != get_wise_quote
            else p(amount, send_curr, recv_curr, send_cty)
        )
        if res:
            quotes.append(res)

    for p_multi in [get_westernunion_quote, get_worldremit_quote, get_sendwave_quote]:
        res_list = p_multi(amount, send_curr, recv_curr, send_cty, recv_cty)
        if res_list:
            quotes.extend(res_list)

    return jsonify(quotes)

if __name__ == "__main__":
    app.run(debug=True)
