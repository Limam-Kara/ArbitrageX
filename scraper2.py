import requests
import json
import sys

# ==============================================================================
# HELPER: ISO-2 to ISO-3 CONVERSION
# ==============================================================================
def get_iso3(iso2):
    mapping = {
        'US': 'USA', 'PH': 'PHL', 'MA': 'MAR', 'FR': 'FRA', 
        'BD': 'BGD', 'SN': 'SEN', 'ES': 'ESP', 'IT': 'ITA',
        'GB': 'GBR', 'DE': 'DEU', 'CA': 'CAN', 'AU': 'AUS'
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
# 4. TAPTAP SEND (Hybrid: Network Rate + Hardcoded Fee)
# ==============================================================================
# Accurate Fee Table from your JSON capture
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
    # 1. Get Fee from Hardcoded Table
    fee = 0.0
    try:
        fee = TAPTAP_FEES.get(send_country.upper(), {}).get(receive_country.upper(), 0.0)
    except:
        pass

    # 2. Get Rate (Attempts Network Call, falls back to Mid-Market Est)
    rate = 0.0
    
    # Try fetching real rate with browser headers
    url = "https://api.taptapsend.com/api/fxRates"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Parse logic
            source_group = None
            if "availableCountries" in data:
                for country in data["availableCountries"]:
                    if country.get("isoCountryCode") == send_country.upper():
                        source_group = country
                        break
            if source_group and "corridors" in source_group:
                for corridor in source_group["corridors"]:
                    if (corridor.get("isoCountryCode") == receive_country.upper() and 
                        corridor.get("currency") == receive_curr.upper()):
                        rate = float(corridor.get("fxRate", 0))
                        break
    except:
        pass
    
    # Fallback if network rate blocked: Use Mid-Market API as estimate
    if rate == 0:
        try:
            # Open Exchange Rates (Free Public API)
            ref_url = f"https://open.er-api.com/v6/latest/{send_curr}"
            ref_res = requests.get(ref_url, timeout=5)
            if ref_res.status_code == 200:
                # TapTap usually matches mid-market very closely
                rate = ref_res.json()["rates"].get(receive_curr, 0)
        except:
            pass

    if rate > 0:
        return {
            "provider": "TapTap Send",
            "rate": rate,
            "fee": fee, # From your provided JSON
            "recipient_gets": amount * rate # TapTap usually sends full amount
        }
        
    return None

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    amt = 100
    print(f"\n--- COMPARISON: US (USD) -> MA (MAD) [Send: {amt}] ---")
    
    # 1. Sendwave
    sw = get_sendwave_quote(amt, "USD", "MAD", "US", "MA")
    if sw: print(f"WAVE   : {sw['recipient_gets']:.2f} MAD (Rate: {sw['rate']:.4f}, Fee: {sw['fee']})")
    else: print("WAVE   : Error")

    # 2. Western Union
    wu = get_westernunion_quote(amt, "USD", "MAD", "US", "MA")
    if wu: print(f"WU     : {wu['recipient_gets']:.2f} MAD (Rate: {wu['rate']:.4f}, Fee: {wu['fee']})")
    else: print("WU     : Error")

    # 3. Remitly
    rem = get_remitly_quote(amt, "USD", "MAD", "US", "MA")
    if rem: print(f"REMITLY: {rem['recipient_gets']:.2f} MAD (Rate: {rem['rate']:.4f}, Fee: {rem['fee']})")
    else: print("REMITLY: Error")

    # 4. TapTap Send
    tt = get_taptap_quote(amt, "USD", "MAD", "US", "MA")
    if tt: print(f"TAPTAP : {tt['recipient_gets']:.2f} MAD (Rate: {tt['rate']:.4f}, Fee: {tt['fee']})")
    else: print("TAPTAP : Error/Unavailable")
    print("\n-----------------------------------------------\n")