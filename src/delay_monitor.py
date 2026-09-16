import pandas as pd
from datetime import datetime

def get_delayed_shipments(df):
    if df.empty:
        return df
    
    df_work = df.copy()
    
    # Parse booking date safely supporting both DD-MM-YYYY and DD/MM/YYYY
    df_work['booking_dt'] = pd.to_datetime(df_work['booking_date'], errors='coerce', dayfirst=True)
    today = pd.to_datetime(datetime.now().date())
    
    # Calculate transit duration in days
    df_work['days_in_transit'] = (today - df_work['booking_dt']).dt.days
    
    # Filter for active consignments delayed beyond 21 days
    condition = (df_work['status'] == 'In Transit') & (df_work['days_in_transit'] > 21)
    delayed_df = df_work[condition].copy()
    
    # Sort with the oldest bookings first
    return delayed_df.sort_values(by='days_in_transit', ascending=False)