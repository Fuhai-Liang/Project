'''
Note: This code is used to crawl incremental files and does not guarantee successful operation
'''

'''
1. Obtain the name of the city based on the postal code
'''

import pandas as pd
import requests
from lxml import etree
from bs4 import BeautifulSoup
import time

data = pd.read_csv("combine_total.csv")
# Get all unique postcodes
unique_postcode = data['Postcode'].unique().tolist()
print("length:", len(unique_postcode))

# Visit external website based on postcode to retrieve the corresponding city name
city_name = []
for code in unique_postcode:
    time.sleep(1)
    response = requests.get(f"https://www.geonames.org/postalcode-search.html?q={code}&country=AU").text
    tree = etree.HTML(response)
    city = tree.xpath("//table[@class='restable']//tr/td[6]/text()")[0]
    print(city)
    city_name.append(city)

# Save postcode and corresponding city into the same table
city_code_name = pd.DataFrame()
city_code_name['postcode'] = unique_postcode
city_code_name['city'] = city_name
city_code_name.to_csv("./city.csv", index=False)


'''
2. Obtain the latitude and longitude coordinates of the gas station
'''
import pandas as pd
import requests
import time
import os

API_KEY = ''
INPUT_FILE = 'combine_total.csv'
OUTPUT_FILE = 'station_location.txt'

# incremental updates
if os.path.exists(OUTPUT_FILE):
    result_df = pd.read_csv(OUTPUT_FILE)
    done_addresses = set(result_df['Address'])
else:
    result_df = pd.DataFrame(columns=['Address', 'Latitude', 'Longitude'])
    done_addresses = set()

# read addresses and remove duplicates
df = pd.read_csv(INPUT_FILE).drop_duplicates(subset=['Address'])

URL = "https://maps.googleapis.com/maps/api/geocode/json"

def geocode_address(address):
    params = {'address': address, 'key': API_KEY}
    response = requests.get(URL, params=params, timeout=10)
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'OK':
            location = result['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            print(f"{address} No results!!")
    else:
        print(f"Error: {response.status_code}")
    return None, None

# main process
try:
    for idx, row in df.iterrows():
        address = row['Address']
        if address in done_addresses:
            print(f"Skipped: {address}")
            continue

        print(f"Finding: {address}")
        lat, lng = geocode_address(address)
        columns = ['Address', 'Latitude', 'Longitude']
        new_row = pd.DataFrame([{'Address': address, 'Latitude': lat, 'Longitude': lng}], columns=columns)
        result_df = pd.concat([result_df, new_row], ignore_index=True)

        time.sleep(0.2)

except Exception as e:
    print(f"An exception occurred: {e}")
finally:
    # save data
    result_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Data saved")