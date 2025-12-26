import json

def parse_xoom_api_response(json_data):
    """
    Parses the exact JSON response format from Xoom's 'remittance' API 
    (the one you intercepted with the mutation query).
    """
    print("--- Parsing Xoom API JSON ---")
    
    try:
        # 1. Navigate to the Remittance Quote
        # Structure based on your provided query:
        # data -> remittance -> quote -> pricing
        remittance = json_data.get('data', {}).get('remittance', {})
        pricing_list = remittance.get('quote', {}).get('pricing', [])
        
        if not pricing_list:
            print("Error: No pricing data found in JSON.")
            return []
            
        results = []
        
        # 2. Iterate through pricing options
        for option in pricing_list:
            # Extract Disbursement Type (Bank, Cash, etc.)
            disbursement = option.get('disbursementType', 'UNKNOWN')
            
            # Extract Payment Method (Debit Card, Bank Account, etc.)
            payment_type = option.get('paymentType', {}).get('type', 'UNKNOWN')
            
            # Extract Rate
            fx_rate = option.get('fxRate', {}).get('rate')
            
            # Extract Fee
            fee = option.get('feeAmount', {}).get('rawValue')
            
            if fx_rate is not None:
                results.append({
                    "provider": "Xoom",
                    "category": disbursement,
                    "method": payment_type,
                    "rate": float(fx_rate),
                    "fee": float(fee) if fee else 0.0,
                    "recipient_gets": float(fx_rate) * 100 # Example
                })
                
        return results

    except Exception as e:
        print(f"Parsing Error: {e}")
        return []

# --- TEST DATA (Based on your successful intercept) ---
# Replace this with the ACTUAL full JSON response you got
mock_response = {
  "data": {
    "remittance": {
      "id": "61257f68-...",
      "quote": {
        "pricing": [
          {
            "disbursementType": "DEPOSIT",
            "paymentType": { "type": "DEBITCARD" },
            "fxRate": { "rate": 16.6299, "comparisonString": "1 USD = ..." },
            "feeAmount": { "rawValue": 0.19, "formattedValue": "0.19" }
          },
          {
            "disbursementType": "DEPOSIT",
            "paymentType": { "type": "ACH" },
            "fxRate": { "rate": 16.6299, "comparisonString": "..." },
            "feeAmount": { "rawValue": 0.00, "formattedValue": "0.00" }
          }
        ]
      }
    }
  }
}

if __name__ == "__main__":
    quotes = parse_xoom_api_response(mock_response)
    
    for q in quotes:
        print(f"Type: {q['category']} | Method: {q['method']} | Rate: {q['rate']} | Fee: {q['fee']}")
