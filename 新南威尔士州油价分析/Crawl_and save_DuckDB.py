#--------------------------------------------------------------------------------------------------------------------------
# 1. Import the required packages
#--------------------------------------------------------------------------------------------------------------------------
import duckdb
import pandas as pd
import requests
from lxml import etree
from bs4 import BeautifulSoup
import time

#--------------------------------------------------------------------------------------------------------------------------
# 2. Get NSW fuel data
#--------------------------------------------------------------------------------------------------------------------------
print("Getting data Now! ")
response = requests.get("https://data.nsw.gov.au/data/dataset/fuel-check","html5lib").text
# Extract the URLs of each dataset from the homepage
tree = etree.HTML(response)
# Since there are data for 15 months, take the last 15 files
li_list = tree.xpath("//section[@id='dataset-resources']/ul/li")[-15:]
print(len(li_list))
# Create an empty DataFrame to store the data
final_data = pd.DataFrame()
for url in li_list:
    data_url = f"https://data.nsw.gov.au{url.xpath('./a/@href')[0]}"
    time.sleep(2)
    data_response = requests.get(data_url,"html5lib")
    soup = BeautifulSoup(data_response.text, "html5lib")
    # Parse the HTML using BeautifulSoup
    title = soup.find("h1","page-heading")
    real_data_url = soup.find("a","resource-url-analytics")["href"]
    print(f"{title.text}:{real_data_url}")
    try:
        tem_data = pd.read_excel(real_data_url)
    except ValueError as e:
        tem_data = pd.read_csv(real_data_url)
    final_data = pd.concat([final_data,tem_data],axis=0)
final_data = final_data.reset_index(drop=True)
# Save the combined data as a CSV file
final_data.to_csv("combine_total.csv",index=False)

#--------------------------------------------------------------------------------------------------------------------------
# 2.1 Use incremental data to obtain the city names corresponding to each suburb
#--------------------------------------------------------------------------------------------------------------------------
'''
Obtain city names based on postcode, so that from the postcodes we can determine the city,
and the city’s fuel price information can be derived from its gas station data.
'''
city_data = final_data.copy()
# Get all unique postcodes
unique_postcode = city_data['Postcode'].unique().tolist()
print("lenght:",len(unique_postcode))

data_postcode = pd.read_csv('postcode.txt', sep='\t', header=None, names=[
    'Country_code', 'postcode', 'Suburb', 'State', 'StateCode', 'city', 'LGACode', 'AdminName3', 'AdminCode3', 'Latitude', 'Longitude', 'Accuracy'
])
data_postcode.drop(columns=['Country_code','Suburb', 'State', 'StateCode','LGACode','AdminName3','AdminCode3', 'Accuracy'],inplace=True)
data_postcode_unique = data_postcode.drop_duplicates(subset=['postcode'])

data_fuel = final_data.copy()
used_postcodes = data_fuel['Postcode'].unique()
data_geo_filtered = data_postcode_unique[data_postcode_unique['postcode'].isin(used_postcodes)]
data_geo_filtered = data_geo_filtered[['postcode', 'city', 'Latitude', 'Longitude']]

#--------------------------------------------------------------------------------------------------------------------------
# 3. Clean and split the data, create five tables to store the data, and store them in DuckDB
#--------------------------------------------------------------------------------------------------------------------------
'''
We need to create five tables in a snowflake schema, splitting the combined data table that we crawled from New South Wales into five separate tables for storage:
	1.	FuelPriceFact table:
This fact table records fuel price information and is linked to the ServiceStation and FuelType tables via foreign keys. It records the time of price updates and the price.
Columns: {record_id (primary key), station_id, fuel_id, price_updated_time, price}
Constraints:
	•	FOREIGN KEY (station_id) REFERENCES ServiceStation(station_id)
	•	FOREIGN KEY (fuel_code) REFERENCES FuelType(fuel_code)
	2.	ServiceStation table:
This table stores the basic information of the service station, including the name, address, and associated location (postcode) as well as brand (brand_id). The association with the Location and StationBrand tables is maintained through foreign keys. geographic information about ServiceStation.
Columns: {station_id (primary key, uniquely identifies the service station), name, address, postcode, brand_id,latitude, longitude}
Constraints:
	•	FOREIGN KEY (postcode) REFERENCES Location(postcode)
	•	FOREIGN KEY (brand_id) REFERENCES StationBrand(brand_id)
	3.	Location table:
This table stores the geographic information, including the postcode, suburb, city, latitude, and longitude.Columns: {postcode, suburb, city, latitude, longitude}
	4.	FuelType table:
This table stores the different fuel types. It uses fuel_id as the primary key along with the fuel_code.
Columns: {fuel_id (primary key), fuel_code}
	5.	StationBrand table:
This table stores the service station brand information. Each brand uses brand_id as the primary key, and the brand_name is unique and cannot be null.
Columns: {brand_id INTEGER PRIMARY KEY, brand_name TEXT UNIQUE NOT NULL}
'''

# Use these two datasets to split into five tables
data_combine = final_data.copy()
data_city = data_geo_filtered.copy()


#--------------------------------------------------------------------------------------------------------------------------
# 3.1.1 Build StationBrand Table Data (Gas Station Brands)
#--------------------------------------------------------------------------------------------------------------------------
data_brand = data_combine[['Brand']].drop_duplicates().reset_index(drop=True)
# Generate primary keys as the unique identifiers for each brand
data_brand['brand_id'] = data_brand.index + 1
data_brand = data_brand.rename(columns={'Brand': 'brand_name'})
data_brand = data_brand[['brand_id', 'brand_name']]
# Output the StationBrand data

#--------------------------------------------------------------------------------------------------------------------------
# 3.1.2 Build FuelType Table Data (Fuel Types)
#--------------------------------------------------------------------------------------------------------------------------
# Build FuelType table data (fuel type dimension)
data_fuel = data_combine[['FuelCode']].drop_duplicates().reset_index(drop=True)
data_fuel['fuel_id'] = data_fuel.index + 1
data_fuel = data_fuel.rename(columns={'FuelCode': 'fuel_code'})
data_fuel = data_fuel[['fuel_id', 'fuel_code']]

#--------------------------------------------------------------------------------------------------------------------------
# 3.1.3 Build ServiceStation Table Data (Gas Station)
#--------------------------------------------------------------------------------------------------------------------------
# Read the supplementary station location data from station_location.txt
geo_data = pd.read_csv(
    "station_location.txt", 
    sep=",",
    engine="python",
    names=["Address", "Latitude", "Longitude"],
    quotechar='"'
)

# Extract station-related information: name, address, suburb, postcode, and brand
# from the combined data, then drop duplicates and reset the index
data_station = data_combine[['ServiceStationName', 'Address', 'Suburb', 'Postcode', 'Brand']].drop_duplicates().reset_index(drop=True)

# Convert brand name to brand_id using the previously created data_brand table
data_station = data_station.merge(data_brand, left_on='Brand', right_on='brand_name', how='left')

# Auto-generate station_id
data_station['station_id'] = data_station.index + 1

# Rename fields to match the table schema; ServiceStation only stores name, address, postcode, and brand_id
data_station = data_station.rename(columns={
    'ServiceStationName': 'name',
    'Address': 'address',
    'Postcode': 'postcode'
})
data_station = data_station[['station_id', 'name', 'address', 'postcode', 'brand_id']]

# Merge data_station with geo_data based on the address fields
data_station = data_station.merge(
    geo_data,
    left_on="address",
    right_on="Address",
    how="left"  # Left join to retain all records from data_station
)

# Rename latitude and longitude columns to lowercase
data_station = data_station.rename(columns={
    "Latitude": "latitude",
    "Longitude": "longitude"
})

# Drop the duplicate 'Address' column from geo_data and reorder the columns
data_station.drop(columns=["Address"], inplace=True)
data_station = data_station[[
    "station_id", 
    "name", 
    "address", 
    "postcode", 
    "brand_id", 
    "latitude", 
    "longitude"
]]


#--------------------------------------------------------------------------------------------------------------------------
# 3.1.4 Build Location Table Data (City Geographic Dimension)
#--------------------------------------------------------------------------------------------------------------------------
# Get the postcode and suburb information from combine_total.csv (data_combine)
data_location_temp = data_combine[['Postcode', 'Suburb']].drop_duplicates().reset_index(drop=True)
# Merge the suburb data from combine_total.csv with the city, latitude, and longitude data from city.csv (data_city)
data_location = pd.merge(data_location_temp, data_city, left_on='Postcode', right_on='postcode', how='left')
# Drop the duplicate 'postcode' column from city.csv and rename fields
data_location.drop(columns=['postcode'], inplace=True)
data_location = data_location.rename(columns={
    'Postcode': 'postcode',
    'Suburb': 'suburb',
    'city': 'city',
    'Latitude': 'latitude',
    'Longitude': 'longitude'
})
# Remove duplicate records based on the 'postcode' field
data_location = data_location.drop_duplicates(subset=['postcode']).reset_index(drop=True)

#--------------------------------------------------------------------------------------------------------------------------
# 3.1.5 Build FuelPriceFact Table Data (Price Fact Table)
#--------------------------------------------------------------------------------------------------------------------------
# Treat each row in combine_total.csv as a fuel price record,
# and obtain station_id based on station information (name, address, postcode)
data_fact = pd.merge(
    data_combine,
    data_station,
    left_on=['ServiceStationName', 'Address', 'Postcode'],
    right_on=['name', 'address', 'postcode'],
    how='left'
)
# Auto-generate record_id
data_fact['record_id'] = data_fact.index + 1
# Rename fields to align with the FuelPriceFact table schema
data_fact = data_fact.rename(columns={
    'FuelCode': 'fuel_code',
    'PriceUpdatedDate': 'price_updated_time',
    'Price': 'price'
})

# Build a mapping dictionary: keys are fuel_code and values are fuel_id
fuel_map = dict(zip(data_fuel['fuel_code'], data_fuel['fuel_id']))
# Use map to convert fuel_code in data_fact to fuel_id
data_fact['fuel_id'] = data_fact['fuel_code'].map(fuel_map)

data_fact = data_fact[['record_id', 'station_id', 'fuel_id', 'price_updated_time', 'price']]

#--------------------------------------------------------------------------------------------------------------------------
# 3.2 Create five tables using DuckDB
#--------------------------------------------------------------------------------------------------------------------------
try:
    con = duckdb.connect("NSW_FuelData.duckdb")
    # Print the connection object to check output
    print("Connected successfully, connection object:", con)
except Exception as e:
    print("Connection failed")

con.sql("""
CREATE TABLE IF NOT EXISTS StationBrand (
    brand_id INTEGER PRIMARY KEY,
    brand_name TEXT UNIQUE NOT NULL
);
""")

con.sql("""
CREATE TABLE IF NOT EXISTS FuelType (
    fuel_id INTEGER PRIMARY KEY,
    fuel_code TEXT NOT NULL
);
""")

con.sql("""
CREATE TABLE IF NOT EXISTS Location (
    postcode INTEGER PRIMARY KEY,
    suburb TEXT NOT NULL,
    city TEXT,
    latitude DOUBLE,
    longitude DOUBLE
);
""")

con.sql("""
CREATE TABLE IF NOT EXISTS ServiceStation (
    station_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    postcode INTEGER NOT NULL,
    brand_id INTEGER NOT NULL,
    latitude DOUBLE,
    longitude DOUBLE,
    FOREIGN KEY (brand_id) REFERENCES StationBrand(brand_id)
);
""")

con.sql("""
CREATE TABLE IF NOT EXISTS FuelPriceFact (
    record_id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL,
    fuel_id INTEGER NOT NULL,
    price_updated_time TIMESTAMP NOT NULL,
    price DOUBLE NOT NULL,
    FOREIGN KEY (station_id) REFERENCES ServiceStation(station_id),
    FOREIGN KEY (fuel_id) REFERENCES FuelType(fuel_id)
);
""")

#--------------------------------------------------------------------------------------------------------------------------
# 3.3 Insert Data into Respective Tables
#--------------------------------------------------------------------------------------------------------------------------
# Create temporary tables to facilitate inserting data into the tables
con.register('data_brand', data_brand)
con.sql("INSERT INTO StationBrand SELECT * FROM data_brand")
# ------------------------------------------------------------------
con.register('data_fuel', data_fuel)
con.sql("INSERT INTO FuelType SELECT * FROM data_fuel")
# ------------------------------------------------------------------
con.register('data_location', data_location)
con.sql("INSERT INTO Location SELECT * FROM data_location")
# ------------------------------------------------------------------
con.register('data_station', data_station)
con.sql("INSERT INTO ServiceStation SELECT * FROM data_station")
# ------------------------------------------------------------------
con.register('data_fact', data_fact)
con.sql("INSERT INTO FuelPriceFact SELECT * FROM data_fact")

#--------------------------------------------------------------------------------------------------------------------------
# 3.4 View the Stored Data
#--------------------------------------------------------------------------------------------------------------------------
print("--"*50)
print("StationBrand Data:")
con.table("StationBrand").show()
print("--"*50)
# ------------------------------------------------------------------
print("--"*50)
print("FuelType Data:")
con.table("FuelType").show()
print("--"*50)
# ------------------------------------------------------------------
print("--"*50)
print("Location Data:")
con.table("Location").show()
print("--"*50)
# ------------------------------------------------------------------
print("--"*50)
print("ServiceStation Data:")
con.table("ServiceStation").show()
print("--"*50)
# ------------------------------------------------------------------
print("--"*50)
print("FuelPriceFact Data:")
con.table("FuelPriceFact").show()
print("--"*50)

#--------------------------------------------------------------------------------------------------------------------------
# 4. Merge Data for Plotting and Save into DuckDB for Visualization Preparation
#--------------------------------------------------------------------------------------------------------------------------
# 4.1 Preliminary Analysis
'''
Preliminary analysis shows that only five fuel types have complete data.
The remaining fuel types have too many missing records to be used for visualization.
Therefore, we need to filter and organize the data in steps:
1. First, based on fuel type, select these five fuels: 'E10', 'P95', 'P98', 'PDL', 'U91'.
2. Since each gas station does not record data daily, compute the daily average fuel price for all stations within the same city to represent that city's price for that day.
3. By merging the fuel prices, we can obtain the daily fuel price for each fuel type in every city; however, this data still contains missing values because some days have no records.
4. Therefore, aggregate the daily data into monthly data for each fuel type in each city to derive the monthly average fuel price. 
   At the same time, since some cities may have one or two months of missing data, filter out the cities with fewer than 15 months of records, 
   yielding the final dataset with complete monthly records for each city.
'''

#--------------------------------------------------------------------------------------------------------------------------
# 4.2 Filter the Data to Obtain the Daily Prices of Different Fuels for Each City
#--------------------------------------------------------------------------------------------------------------------------
# Execute the SQL statement to create the DayResult table [each record represents one day for a given city and fuel type]
con.sql("""
CREATE TABLE IF NOT EXISTS DayResult AS
SELECT 
    l.city,
    t3.fuel_code AS fuelcode,
    CAST(t1.price_updated_time AS DATE) AS date_only,
    ROUND(AVG(t1.price), 1) AS price
FROM FuelPriceFact t1
JOIN ServiceStation t2
    ON t1.station_id = t2.station_id
JOIN Location l
    ON t2.postcode = l.postcode
JOIN FuelType t3
    ON t1.fuel_id = t3.fuel_id
WHERE t3.fuel_code IN ('E10', 'P95', 'P98', 'PDL', 'U91')
GROUP BY l.city, t3.fuel_code, CAST(t1.price_updated_time AS DATE)
ORDER BY l.city, CAST(t1.price_updated_time AS DATE);
""")

# Query and display the first 10 records of the DayResult table
print("--"*50)
print("DayResult Data:")
con.table("DayResult").show()
print("--"*50)

#--------------------------------------------------------------------------------------------------------------------------
# 4.3 Filter Data to Obtain the Monthly Average Fuel Prices for Different Fuels in Each City
# Merge daily data into monthly data to create a monthly price table for each fuel type in each city
#--------------------------------------------------------------------------------------------------------------------------
# Execute the SQL statement to create the MonthResult table
con.sql("""
CREATE TABLE IF NOT EXISTS MonthResult AS
WITH month AS (
    SELECT 
        city,
        fuelcode,
        STRFTIME('%Y-%m', CAST(date_only AS DATE)) AS date_month,
        ROUND(AVG(price), 1) AS avg_month_price
    FROM DayResult
    GROUP BY 
        city, 
        fuelcode, 
        STRFTIME('%Y-%m', CAST(date_only AS DATE))
),
counts AS (
    SELECT 
        city, 
        fuelcode, 
        COUNT(*) AS cnt
    FROM month
    GROUP BY city, fuelcode
)
SELECT 
    m.city, 
    m.fuelcode,
    m.date_month,
    m.avg_month_price
FROM month m
JOIN counts c
    ON m.city = c.city AND m.fuelcode = c.fuelcode
WHERE c.cnt = 15
ORDER BY m.city, m.fuelcode, m.date_month;
""")
# cnt=15 means we only select cities with complete data for 15 months

# Query and display the first 10 records of the MonthResult table
print("--"*50)
print("MonthResult Data:")
con.table("MonthResult").show()
print("--"*50)

#--------------------------------------------------------------------------------------------------------------------------
# Close the DuckDB connection
#--------------------------------------------------------------------------------------------------------------------------
con.close()
print("DuckDB connection has been closed")
