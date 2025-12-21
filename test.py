import requests
import json
import sys
import os

# ==============================================================================
# HELPER: ISO-2 to ISO-3 CONVERSION
# ==============================================================================
def get_iso3(iso2):
    mapping = {
        'US': 'USA', 'PH': 'PHL', 'MA': 'MAR', 'FR': 'FRA', 
        'BD': 'BGD', 'SN': 'SEN', 'ES': 'ESP', 'IT': 'ITA',
        'GB': 'GBR', 'DE': 'DEU', 'CA': 'CAN', 'AU': 'AUS',
        'TR': 'TUR', 'VN': 'VNM', 'BE': 'BEL'
    }
    return mapping.get(iso2.upper(), iso2.upper())

# ==============================================================================
# 1. SENDWAVE
# ==============================================================================
def get_sendwave_quote(amount, send_curr, receive_curr, send_country, receive_country):
    base_url = "https://app.sendwave.com/v2/pricing-public"
    segment = 'standard'
    rc = receive_country.lower()
    if rc == 'ph': segment = 'ph_gcash'
    elif rc == 'bd': segment = 'bd_bkash'
    elif rc == 'ma': segment = 'ma_cashplus'
    elif rc == 'sn': segment = 'sn_orange'
    
    params = {
        'amountType': 'SEND', 'receiveCurrency': receive_curr, 'segmentName': segment,
        'amount': amount, 'sendCurrency': send_curr,
        'sendCountryIso2': send_country, 'receiveCountryIso2': receive_country
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "effectiveExchangeRate" in data:
                return {
                    "provider": "Sendwave",
                    "rate": float(data["effectiveExchangeRate"]),
                    "fee": float(data["effectiveFeeAmount"]),
                    "recipient_gets": float(data["receiveAmount"])
                }
    except: return None
    return None

# ==============================================================================
# 2. WESTERN UNION
# ==============================================================================
def get_westernunion_quote(amount, send_curr, receive_curr, send_country, receive_country):
    url = "https://www.westernunion.com/wuconnect/prices/catalog"
    payload = {
        "header_request": {"version": "0.5", "request_type": "PRICECATALOG"},
        "sender": {
            "client": "WUCOM", "channel": "WWEB", "funds_in": "*",
            "curr_iso3": send_curr.upper(), "cty_iso2_ext": send_country.upper(),
            "send_amount": str(amount)
        },
        "receiver": {
            "curr_iso3": receive_curr.upper(),
            "cty_iso2_ext": receive_country.upper(),
            "cty_iso2": receive_country.upper()
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://www.westernunion.com'
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            best_quote = None
            if "services_groups" in data and isinstance(data["services_groups"], list):
                for group in data["services_groups"]:
                    if "pay_groups" in group:
                        for pay in group["pay_groups"]:
                            try:
                                rec_amt = float(pay.get("receive_amount", 0))
                                if best_quote is None or rec_amt > best_quote["recipient_gets"]:
                                    best_quote = {
                                        "provider": "Western Union",
                                        "rate": float(pay.get("fx_rate", 0)),
                                        "fee": float(pay.get("base_fee", 0)),
                                        "recipient_gets": rec_amt
                                    }
                            except: continue
            return best_quote
    except: return None
    return None

# ==============================================================================
# 3. REMITLY
# ==============================================================================
def get_remitly_quote(amount, send_curr, receive_curr, send_country, receive_country):
    s_iso3, r_iso3 = get_iso3(send_country), get_iso3(receive_country)
    conduit = f"{s_iso3}:{send_curr.upper()}-{r_iso3}:{receive_curr.upper()}"
    url = "https://api.remitly.io/v3/calculator/estimate"
    params = {
        'conduit': conduit, 'anchor': 'SEND', 'amount': amount,
        'purpose': 'OTHER', 'customer_segment': 'UNRECOGNIZED', 'strict_promo': 'false'
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            best_opt = None
            if "pay_out_price_estimates" in data:
                for est in data["pay_out_price_estimates"].get("estimates", []):
                    try:
                        rec_amt = float(est.get("receive_amount", 0))
                        if best_opt is None or rec_amt > best_opt["recipient_gets"]:
                            exch = est.get("exchange_rate", {})
                            rate = float(exch.get("promotional_exchange_rate") or exch.get("base_rate"))
                            best_opt = {
                                "provider": "Remitly",
                                "rate": rate,
                                "fee": float(est.get("fee", {}).get("total_fee_amount", 0)),
                                "recipient_gets": rec_amt
                            }
                    except: continue
            return best_opt
    except: return None
    return None

# ==============================================================================
# 4. TAPTAP SEND
# ==============================================================================
TAPTAP_FEES = {
    "US": {"MA": 2.99, "PH": 2.99, "GT": 1.99},
    "CA": {"MA": 2.50, "PH": 3.49},
    "GB": {"MA": 2.99, "PH": 1.49},
    "FR": {"MA": 2.99, "PH": 2.49},
    "ES": {"MA": 2.50, "PH": 2.49},
    "IT": {"MA": 2.50, "PH": 2.49},
    "DE": {"MA": 2.50, "PH": 2.49}
}
def get_taptap_quote(amount, send_curr, receive_curr, send_country, receive_country):
    fee = TAPTAP_FEES.get(send_country.upper(), {}).get(receive_country.upper(), 0.0)
    rate = 0.0
    try:
        url = "https://api.taptapsend.com/api/fxRates"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "availableCountries" in data:
                for country in data["availableCountries"]:
                    if country.get("isoCountryCode") == send_country.upper():
                        for corridor in country.get("corridors", []):
                             if (corridor.get("isoCountryCode") == receive_country.upper() and 
                                 corridor.get("currency") == receive_curr.upper()):
                                 rate = float(corridor.get("fxRate", 0))
                                 break
    except: pass
    
    if rate == 0 and os.path.exists("taptap_data.json"):
        try:
            with open("taptap_data.json", "r") as f:
                data = json.load(f)
                for country in data["availableCountries"]:
                    if country.get("isoCountryCode") == send_country.upper():
                        for corridor in country.get("corridors", []):
                             if (corridor.get("isoCountryCode") == receive_country.upper() and 
                                 corridor.get("currency") == receive_curr.upper()):
                                 rate = float(corridor.get("fxRate", 0))
        except: pass

    if rate == 0:
        try:
             ref = requests.get(f"https://open.er-api.com/v6/latest/{send_curr}").json()
             rate = ref["rates"].get(receive_curr, 0)
        except: pass

    if rate > 0:
        return {"provider": "TapTap Send", "rate": rate, "fee": fee, "recipient_gets": amount * rate}
    return None

# ==============================================================================
# 5. WISE
# ==============================================================================
def get_wise_quote(amount, send_curr, receive_curr, send_country):
    url = "https://wise.com/gateway/v4/comparisons"
    params = {
        'sendAmount': amount,
        'sourceCurrency': send_curr,
        'targetCurrency': receive_curr,
        'sourceCountry': send_country,
        'filter': 'POPULAR',
        'includeWise': 'true',
        'payInMethod': 'DIRECT_DEBIT' 
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://wise.com',
        'Referer': 'https://wise.com/'
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "providers" in data:
                for provider in data["providers"]:
                    if provider.get("alias") == "wise":
                        if "quotes" in provider and len(provider["quotes"]) > 0:
                            quote = provider["quotes"][0]
                            return {
                                "provider": "Wise",
                                "rate": float(quote.get("rate", 0)),
                                "fee": float(quote.get("fee", 0)),
                                "recipient_gets": float(quote.get("receivedAmount", 0))
                            }
    except: return None
    return None

# ==============================================================================
# 6. WORLDREMIT (New!)
# ==============================================================================
def get_worldremit_quote(amount, send_curr, receive_curr, send_country, receive_country):
    url = "https://api.worldremit.com/graphql"
    
    # Try methods in order of likelihood for Morocco
    # CSH = Cash Pickup (Most common)
    # WLT = Mobile Wallet (Orange Money/Inwi)
    # BNK = Bank Transfer
    methods_to_try = ["CSH", "WLT", "BNK"]
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://www.worldremit.com'
    }

    query = """
    mutation createCalculation($amount: BigDecimal!, $type: CalculationType!, $sendCountryCode: CountryCode!, $sendCurrencyCode: CurrencyCode!, $receiveCountryCode: CountryCode!, $receiveCurrencyCode: CurrencyCode!, $payOutMethodCode: String, $correspondentId: String) {
      createCalculation(
        calculationInput: {amount: $amount, send: {country: $sendCountryCode, currency: $sendCurrencyCode}, type: $type, receive: {country: $receiveCountryCode, currency: $receiveCurrencyCode}, payOutMethodCode: $payOutMethodCode, correspondentId: $correspondentId}
      ) {
        calculation {
          id
          informativeSummary {
            fee {
              value {
                amount
                currency
              }
            }
          }
          receive {
            amount
            currency
          }
          exchangeRate {
            value
          }
        }
        errors {
          message
        }
      }
    }
    """

    for method in methods_to_try:
        variables = {
            "amount": amount,
            "type": "SEND",
            "sendCountryCode": send_country.upper(),
            "sendCurrencyCode": send_curr.upper(),
            "receiveCountryCode": receive_country.upper(),
            "receiveCurrencyCode": receive_curr.upper(),
            "payOutMethodCode": method,
            "correspondentId": None # Try null instead of empty string
        }

        try:
            response = requests.post(url, json={'query': query, 'variables': variables}, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for calculation data
                calc_result = data.get("data", {}).get("createCalculation", {})
                
                # If we have errors, try next method
                if not calc_result or calc_result.get("errors"):
                    continue

                calc = calc_result.get("calculation")
                if calc:
                    rec_amount = float(calc.get("receive", {}).get("amount", 0))
                    rate = float(calc.get("exchangeRate", {}).get("value", 0))
                    fee = float(calc.get("informativeSummary", {}).get("fee", {}).get("value", {}).get("amount", 0))
                    
                    return {
                        "provider": f"WorldRemit ({method})",
                        "rate": rate,
                        "fee": fee,
                        "recipient_gets": rec_amount
                    }
        except:
            continue
            
    return None

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    amt = 100
    S_CURR, R_CURR = "USD", "MAD"
    S_CTY, R_CTY = "US", "MA"

    print(f"\n--- COMPARISON: {S_CTY} ({S_CURR}) -> {R_CTY} ({R_CURR}) [Send: {amt}] ---")
    
    providers = [
        get_sendwave_quote(amt, S_CURR, R_CURR, S_CTY, R_CTY),
        get_westernunion_quote(amt, S_CURR, R_CURR, S_CTY, R_CTY),
        get_remitly_quote(amt, S_CURR, R_CURR, S_CTY, R_CTY),
        get_taptap_quote(amt, S_CURR, R_CURR, S_CTY, R_CTY),
        get_wise_quote(amt, S_CURR, R_CURR, S_CTY),
        get_worldremit_quote(amt, S_CURR, R_CURR, S_CTY, R_CTY)
    ]
    
    # Sort by Best Recipient Amount
    valid_quotes = [p for p in providers if p]
    valid_quotes.sort(key=lambda x: x['recipient_gets'], reverse=True)
    
    for q in valid_quotes:
        print(f"{q['provider']:<12}: {q['recipient_gets']:.2f} {R_CURR} (Rate: {q['rate']:.4f}, Fee: {q['fee']:.2f})")
