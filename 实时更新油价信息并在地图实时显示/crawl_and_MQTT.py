# Import required packages
import pandas as pd
import time
import datetime
import os
import json
import requests
import paho.mqtt.client as mqtt
import warnings
warnings.filterwarnings("ignore")

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 1. Configure constants
# Only need to update API_KEY and AUTHORIZATION

API_KEY = "*************************************"
AUTHORIZATION = "Basic OG1BNklCQ1hVT2JLcHBkeXBIVmJvaUd5U0liOUlFUWw6WUZjUHBuMXhjY2d0UmxEVg=="

GRANT_TYPE = "client_credentials"
CONTENT_TYPE = "application/json; charset=utf-8"
TRANSACTIONID = "202505061824"
TIMESTAMP = "08/05/2025 06:15:00 PM"
CSV_PATH = "data.csv"       # overwrite this file
MQTT_BROKER = "172.17.34.107"
MQTT_PORT   = 1883
MQTT_TOPIC  = "COMP5339/530446891"

# MQTT client setup
mqtt_client = mqtt.Client()
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 2. Define the functions for obtaining data and merging data
def crawl_data_from_api():
    # obtaining access token
    token_url = "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken"
    # Use the get method to obtain the json file
    resp = requests.get(token_url,
                        headers={'content-type': CONTENT_TYPE, 'authorization': AUTHORIZATION},
                        params={'grant_type': GRANT_TYPE})
    access_token = "Bearer " + resp.json()['access_token']
    print(f"[{datetime.datetime.now()}] Got token: {access_token}")

    #  Get information about gas stations and the prices of oil products
    station_url = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1/fuel/prices"
    # Set the header file
    headers = {
        'content-type': CONTENT_TYPE,
        'authorization': access_token,
        'apikey': API_KEY,
        'transactionid': TRANSACTIONID,
        'requesttimestamp': TIMESTAMP
    }
    r = requests.get(station_url, headers=headers)
    data = r.json()

    # Obtain the information of oil stations through the stations field in the json file
    rows = []
    for s in data.get("stations", []):
        rows.append({
            "brandid": s.get("brandid"),
            "stationid": s.get("stationid"),
            "brand":    s.get("brand"),
            "code":     s.get("code"),
            "name":     s.get("name"),
            "address":  s.get("address"),
            "latitude": s.get("location", {}).get("latitude"),
            "longitude":s.get("location", {}).get("longitude"),
            "isAdBlueAvailable": s.get("isAdBlueAvailable")
        })
    df_stations = pd.DataFrame(rows)

    # Obtain the fuel price
    df_prices = pd.DataFrame(data.get("prices", []))
    # Package the "price" and "lastupdated" of the same gas station into dictionaries respectively
    df_prices = (
             df_prices
            .groupby('stationcode')
            .apply(lambda g: pd.Series({
            'fuel_price': dict(zip(g['fueltype'], g['price'])),
            'fuel_update_time': dict(zip(g['fueltype'], g['lastupdated']))
               }))
            .reset_index()
            )
    # Boolean index: Delete the row that contains only {'EV':0.0} oil
    mask = df_prices["fuel_price"].apply(lambda d: not (len(d) == 1 and d.get("EV") == 0.0))
    df_prices = df_prices[mask].reset_index(drop=True)

    # Merge the information of gas stations and oil prices through internal connections
    df = pd.merge(df_stations,
                  df_prices,
                  left_on='code', right_on='stationcode',
                  how='inner').drop(columns=['stationcode'])
    print(f"[{datetime.datetime.now()}] Data merged: {len(df)} rows")
    return df
# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 3. Program entry and publish data
if __name__ == "__main__":
    while True:
        # crawl and save CSV
        df = crawl_data_from_api()
        df.to_csv(CSV_PATH, index=False)
        print(f"[{datetime.datetime.now()}] Saved to {CSV_PATH}")

        # Read the csv file and publish the information line by line
        df2 = pd.read_csv(CSV_PATH)
        for _, row in df2.iterrows():
            payload = row.to_json()
            mqtt_client.publish(MQTT_TOPIC, payload)
            print(f"[{datetime.datetime.now()}] Published station {row.get('code','?')}")
            time.sleep(0.1)

        # This round of release is complete. Wait for 60 seconds before the next round
        print(f"[{datetime.datetime.now()}] Batch complete, sleeping 60 seconds\n")
        time.sleep(60)
