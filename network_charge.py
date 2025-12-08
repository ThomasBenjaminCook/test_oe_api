import datetime as dt

# Local price calculation for Ausgrid's EA025 schedule (2025-2026)
# https://www.ausgrid.com.au/-/media/Documents/Regulation/Pricing/PList/Ausgrid-Network-Price-List-2025-26.pdf?rev=d03e3b238a144e8abf3325bcc92eed08
def calculate_local_price(datetime: dt.datetime):
    PEAK_CHARGE = 32.1695 # c/kWh
    OFFPEAK_CHARGE = 5.6688 # c/kWh
    
    PEAK_CHARGE = PEAK_CHARGE * 10 # convert to $/MWh
    OFFPEAK_CHARGE = OFFPEAK_CHARGE * 10 # convert to $/MWh
    
    # Peak is applied from 3-9pm each day during Summer (November to March) and Winter (June to August) months
    
    month = datetime.month
    hour = datetime.hour
    
    if (month in [11, 12, 1, 2, 3]) or (month in [6, 7, 8]):
        # Summer or Winter months
        if hour >= 15 and hour < 21:
            return PEAK_CHARGE
        else:
            return OFFPEAK_CHARGE
