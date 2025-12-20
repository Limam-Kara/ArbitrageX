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
# 1. SENDWAVE (Advanced: Dynamic "bestPricedSegmentName")
# ==============================================================================
def get_sendwave_quote(amount, send_curr, receive_curr, send_country, receive_country):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.sendwave.com/',
        'Origin': 'https://www.sendwave.com',
        'Accept': 'application/json'
    }

    # 1. Request Segments Info
    segments_url = "https://app.sendwave.com/v2/pricing-segments"
    params_seg = {
        'sendCountryIso2': send_country.lower(),
        'sendCurrency': send_curr,
        'receiveCountryIso2': receive_country.lower(),
        'receiveCurrency': receive_curr
    }
    
    results = []
    
    try:
        resp_seg = requests.get(segments_url, params=params_seg, headers=headers, timeout=10)
        
        if resp_seg.status_code == 200:
            data = resp_seg.json()
            
            # 2. Extract bestPricedSegmentName from payoutMethodsAndPrices
            # We look for "Cash Pickup" and "Bank Account" labels
            payout_methods = data.get("payoutMethodsAndPrices", [])
            
            segments_to_check = []
            
            for method in payout_methods:
                label = method.get("label", "")
                best_segment = method.get("bestPricedSegmentName")
                
                if not best_segment: continue

                if "Cash Pickup" in label:
                    segments_to_check.append({"segment": best_segment, "cat": "Retrait en Espèces"})
                elif "Bank Account" in label:
                    segments_to_check.append({"segment": best_segment, "cat": "Dépôt Bancaire"})
                elif "Wallet" in label or "Mobile" in label:
                    segments_to_check.append({"segment": best_segment, "cat": "Retrait en Espèces"}) # Wallet -> Cash group

            # 3. Fetch Pricing for these specific segments
            pricing_url = "https://app.sendwave.com/v2/pricing-public"
            
            for item in segments_to_check:
                params_quote = {
                    'amountType': 'SEND',
                    'receiveCurrency': receive_curr,
                    'segmentName': item['segment'],
                    'amount': amount,
                    'sendCurrency': send_curr,
                    'sendCountryIso2': send_country.lower(),
                    'receiveCountryIso2': receive_country.lower()
                }
                
                try:
                    resp_quote = requests.get(pricing_url, params=params_quote, headers=headers, timeout=5)
                    if resp_quote.status_code == 200:
                        q_data = resp_quote.json()
                        if "effectiveExchangeRate" in q_data:
                            results.append({
                                "provider": "Sendwave",
                                "category": item['cat'],
                                "rate": float(q_data["effectiveExchangeRate"]),
                                "fee": float(q_data["effectiveFeeAmount"]),
                                "recipient_gets": float(q_data["receiveAmount"])
                            })
                except: continue

            # Filter: Best quote per category
            final_quotes = []
            for cat in ["Dépôt Bancaire", "Retrait en Espèces"]:
                cat_options = [q for q in results if q['category'] == cat]
                if cat_options:
                    best = max(cat_options, key=lambda x: x['recipient_gets'])
                    final_quotes.append(best)
            
            return final_quotes if final_quotes else None

    except: return None
    return None

# ==============================================================================
# 2. WESTERN UNION (Robust Service Name Categorization)
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
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    
    results = []
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            if "services_groups" in data and isinstance(data["services_groups"], list):
                for group in data["services_groups"]:
                    service_name = group.get("service_name", "").upper()
                    
                    category = "Autre"
                    if "BANK" in service_name or "DIRECT" in service_name:
                        category = "Dépôt Bancaire"
                    elif "MINUTES" in service_name or "CASH" in service_name:
                        category = "Retrait en Espèces"
                    elif "MOBILE" in service_name:
                        category = "Retrait en Espèces"
                    else:
                        continue 

                    if "pay_groups" in group:
                        for pay in group["pay_groups"]:
                            try:
                                rec_amt = float(pay.get("receive_amount", 0))
                                results.append({
                                    "provider": "Western Union",
                                    "category": category,
                                    "rate": float(pay.get("fx_rate", 0)),
                                    "fee": float(pay.get("base_fee", 0)),
                                    "recipient_gets": rec_amt
                                })
                            except: continue
            
            final_quotes = []
            for cat in ["Dépôt Bancaire", "Retrait en Espèces"]:
                cat_options = [q for q in results if q['category'] == cat]
                if cat_options:
                    best = max(cat_options, key=lambda x: x['recipient_gets'])
                    final_quotes.append(best)
            
            return final_quotes if final_quotes else None

    except: return None
    return None

# ==============================================================================
# 3. REMITLY (Dynamic Category)
# ==============================================================================
def get_remitly_quote(amount, send_curr, receive_curr, send_country, receive_country):
    s_iso3, r_iso3 = get_iso3(send_country), get_iso3(receive_country)
    conduit = f"{s_iso3}:{send_curr.upper()}-{r_iso3}:{receive_curr.upper()}"
    url = "https://api.remitly.io/v3/calculator/estimate"
    params = {'conduit': conduit, 'anchor': 'SEND', 'amount': amount, 'purpose': 'OTHER', 'customer_segment': 'UNRECOGNIZED', 'strict_promo': 'false'}
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
                                "category": "Retrait en Espèces", 
                                "rate": rate,
                                "fee": float(est.get("fee", {}).get("total_fee_amount", 0)),
                                "recipient_gets": rec_amt
                            }
                    except: continue
            return best_opt
    except: return None
    return None

# ==============================================================================
# 4. TAPTAP SEND (Category: Retrait Espèces)
# ==============================================================================
TAPTAP_FEES = {"US": {"MA": 2.99, "PH": 2.99}, "CA": {"MA": 2.50}, "FR": {"MA": 2.99}}
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
                             if (corridor.get("isoCountryCode") == receive_country.upper() and corridor.get("currency") == receive_curr.upper()):
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
                             if (corridor.get("isoCountryCode") == receive_country.upper() and corridor.get("currency") == receive_curr.upper()):
                                 rate = float(corridor.get("fxRate", 0))
        except: pass
    
    if rate == 0:
        try:
             ref = requests.get(f"https://open.er-api.com/v6/latest/{send_curr}").json()
             rate = ref["rates"].get(receive_curr, 0)
        except: pass

    if rate > 0:
        return {"provider": "TapTap Send", "category": "Retrait en Espèces", "rate": rate, "fee": fee, "recipient_gets": amount * rate}
    return None

# ==============================================================================
# 5. WISE (Category: Dépôt Bancaire)
# ==============================================================================
def get_wise_quote(amount, send_curr, receive_curr, send_country):
    url = "https://wise.com/gateway/v4/comparisons"
    params = {
        'sendAmount': amount, 'sourceCurrency': send_curr, 'targetCurrency': receive_curr,
        'sourceCountry': send_country, 'filter': 'POPULAR', 'includeWise': 'true', 'payInMethod': 'DIRECT_DEBIT' 
    }
    headers = {'User-Agent': 'Mozilla/5.0', 'Origin': 'https://wise.com'}
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
                                "category": "Dépôt Bancaire",
                                "rate": float(quote.get("rate", 0)),
                                "fee": float(quote.get("fee", 0)),
                                "recipient_gets": float(quote.get("receivedAmount", 0))
                            }
    except: return None
    return None

# ==============================================================================
# 6. WORLDREMIT (Split Category)
# ==============================================================================
def get_worldremit_quote(amount, send_curr, receive_curr, send_country, receive_country):
    url = "https://api.worldremit.com/graphql"
    methods = ["CSH", "BNK"] 
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.worldremit.com'}
    query = """mutation createCalculation($amount: BigDecimal!, $type: CalculationType!, $sendCountryCode: CountryCode!, $sendCurrencyCode: CurrencyCode!, $receiveCountryCode: CountryCode!, $receiveCurrencyCode: CurrencyCode!, $payOutMethodCode: String, $correspondentId: String) { createCalculation(calculationInput: {amount: $amount, send: {country: $sendCountryCode, currency: $sendCurrencyCode}, type: $type, receive: {country: $receiveCountryCode, currency: $receiveCurrencyCode}, payOutMethodCode: $payOutMethodCode, correspondentId: $correspondentId}) { calculation { id informativeSummary { fee { value { amount currency } } } receive { amount currency } exchangeRate { value } } errors { message } } }"""
    
    results = []
    for method in methods:
        variables = {"amount": amount, "type": "SEND", "sendCountryCode": send_country.upper(), "sendCurrencyCode": send_curr.upper(), "receiveCountryCode": receive_country.upper(), "receiveCurrencyCode": receive_curr.upper(), "payOutMethodCode": method, "correspondentId": None}
        try:
            response = requests.post(url, json={'query': query, 'variables': variables}, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                errors = data.get("data", {}).get("createCalculation", {}).get("errors", [])
                if errors:
                    continue

                calc = data.get("data", {}).get("createCalculation", {}).get("calculation")
                if calc:
                    # Determine Category
                    cat = "Dépôt Bancaire" if method == "BNK" else "Retrait en Espèces"
                    results.append({
                        "provider": f"WorldRemit ({method})",
                        "category": cat,
                        "rate": float(calc.get("exchangeRate", {}).get("value", 0)),
                        "fee": float(calc.get("informativeSummary", {}).get("fee", {}).get("value", {}).get("amount", 0)),
                        "recipient_gets": float(calc.get("receive", {}).get("amount", 0))
                    })
        except: continue
    return results if results else None

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    amt = 100
    S_CURR, R_CURR = "USD", "MAD"
    S_CTY, R_CTY = "US", "MA"

    print(f"\n--- ARBITRAGEX COMPARISON: {S_CTY} ({S_CURR}) -> {R_CTY} ({R_CURR}) [Send: {amt}] ---\n")
    
    # Fetch Data
    quotes = []
    
    # 1. Single Quote Providers (Remitly, TapTap, Wise)
    for p in [get_remitly_quote, get_taptap_quote, get_wise_quote]:
        res = p(amt, S_CURR, R_CURR, S_CTY, R_CTY) if p != get_wise_quote else p(amt, S_CURR, R_CURR, S_CTY)
        if res: quotes.append(res)
            
    # 2. Multi Quote Providers (Western Union + WorldRemit + Sendwave)
    for p_multi in [get_westernunion_quote, get_worldremit_quote, get_sendwave_quote]:
        res_list = p_multi(amt, S_CURR, R_CURR, S_CTY, R_CTY)
        if res_list:
            quotes.extend(res_list)

    # Separate into Categories
    bank_quotes = [q for q in quotes if q['category'] == "Dépôt Bancaire"]
    cash_quotes = [q for q in quotes if q['category'] == "Retrait en Espèces"]
    
    # Sort
    bank_quotes.sort(key=lambda x: x['recipient_gets'], reverse=True)
    cash_quotes.sort(key=lambda x: x['recipient_gets'], reverse=True)

    # DISPLAY FUNCTION
    def print_table(title, data):
        print(f"\n=== {title} ===")
        print("-" * 85)
        print(f"{'Provider':<25} | {'Taux de change':<15} | {'Frais de transfert':<20} | {'Le destinataire reçoit':<20}")
        print("-" * 85)
        if not data:
            print("Aucune offre disponible.")
        for q in data:
            rate_str = f"{q['rate']:.4f}"
            fee_str = "GRATUIT" if q['fee'] == 0 else f"{q['fee']:.2f} {S_CURR}"
            recv_str = f"{q['recipient_gets']:.2f} {R_CURR}"
            print(f"{q['provider']:<25} | {rate_str:<15} | {fee_str:<20} | {recv_str:<20}")
        print("-" * 85)

    # Print Both Tables
    print_table("DEPOT BANCAIRE", bank_quotes)
    print_table("RETRAIT EN ESPECES", cash_quotes)
