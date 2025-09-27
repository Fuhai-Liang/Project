import streamlit as st
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import seaborn as sns
import plotly.express as px
from pandas.api.types import CategoricalDtype

# ===== 1. Load Data from DuckDB =====
# Connect to the database file
con = duckdb.connect("NSW_FuelData.duckdb")

# Load data from the DayResult table (assumed fields: city, fuelcode, date_only, price)
day_result_df = con.sql("SELECT * FROM DayResult").fetchdf()

# Load data from the MonthResult table (assumed fields: city, fuelcode, date_month, avg_month_price)
month_result_df = con.sql("SELECT * FROM MonthResult").fetchdf()

# Close the connection (the data is now loaded into DataFrames)
con.close()

# ===== 2. Daily Average Fuel Price Trend (Matplotlib Line Chart) =====
st.title("Daily Average Fuel Price Trend")
st.write("Please select a city and fuel type to view the daily fuel price trend.")

# Convert the date field
df_day = day_result_df.copy()
df_day['Date'] = pd.to_datetime(df_day['date_only'], errors='coerce')

# Get options for the dropdown menus
cities_day = sorted(df_day['city'].dropna().unique())
fuel_types_day = sorted(df_day['fuelcode'].dropna().unique())

# Sidebar controls (note: sidebars for each section can be shared or separated; here they are unified)
st.sidebar.header("[Daily Trend] Select Parameters")
selected_city_day = st.sidebar.selectbox("Select City (Daily Data)", cities_day, key="day_city")
selected_fuel_day = st.sidebar.selectbox("Select Fuel Type (Daily Data)", fuel_types_day, key="day_fuel")

# Filter data based on selections
filtered_day = df_day[(df_day['city'] == selected_city_day) & (df_day['fuelcode'] == selected_fuel_day)]
if filtered_day.empty:
    st.warning(f"No data for {selected_fuel_day} in {selected_city_day}.")
else:
    avg_day = filtered_day.sort_values('Date')
    fig_day, ax_day = plt.subplots(figsize=(18, 6))
    ax_day.plot(avg_day['Date'], avg_day['price'], label=f"{selected_fuel_day} in {selected_city_day}")
    ax_day.set_title(f"{selected_fuel_day} Prices in {selected_city_day}", fontsize=20)
    ax_day.set_xlabel("Date", fontsize=16)
    ax_day.set_ylabel("Average Price (Australian cents)", fontsize=16)
    ax_day.legend()
    ax_day.grid(True)
    ax_day.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1))
    ax_day.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=90)
    st.pyplot(fig_day)
    st.subheader("Daily Data Preview")
    st.dataframe(filtered_day.head())

# ===== 3. Fuel Price Distribution Box Plot by City (Seaborn) =====
st.title("Fuel Price Distribution by City")
# Filter for main fuel types
main_fuel_types = ['E10', 'P98', 'PDL', 'U91', 'P95']
df_box = df_day[df_day['fuelcode'].isin(main_fuel_types)]

# Get list of all cities and add "None" (indicating no selection)
cities_box = sorted(df_box['city'].dropna().unique().tolist())
dropdown_options = ['None'] + cities_box

st.sidebar.header("[Box Plot] Select City")
# Create 5 dropdown selectors for selecting multiple cities
city1 = st.sidebar.selectbox("City 1:", options=dropdown_options, index=0, key="box_city1")
city2 = st.sidebar.selectbox("City 2:", options=dropdown_options, index=0, key="box_city2")
city3 = st.sidebar.selectbox("City 3:", options=dropdown_options, index=0, key="box_city3")
city4 = st.sidebar.selectbox("City 4:", options=dropdown_options, index=0, key="box_city4")
city5 = st.sidebar.selectbox("City 5:", options=dropdown_options, index=0, key="box_city5")

selected_list = [city1, city2, city3, city4, city5]
city_group = [c for c in selected_list if c != 'None']

if not city_group:
    st.warning("Please select at least one city for the box plot.")
else:
    # Retain original order and remove duplicates
    seen = set()
    unique_cities = []
    for c in city_group:
        if c not in seen:
            unique_cities.append(c)
            seen.add(c)

    selected_df_box = df_box[df_box['city'].isin(unique_cities)].copy()
    city_order = CategoricalDtype(categories=unique_cities, ordered=True)
    selected_df_box['city'] = selected_df_box['city'].astype(city_order)

    st.subheader("Box Plot: Fuel Price Distribution by City")
    plt.figure(figsize=(16, 10))
    sns.set(style="whitegrid", context='talk')
    ax_box = sns.boxplot(data=selected_df_box, x='city', y='price', hue='fuelcode', palette='Set2', showfliers=False)
    plt.title("Fuel Price Distribution (Selected Cities)", fontsize=16)
    plt.xlabel("City", fontsize=14)
    plt.ylabel("Price", fontsize=14)
    plt.xticks(rotation=30)
    plt.yticks(np.arange(140, 261, 20))
    plt.legend(title="Fuel Type", loc='upper right', fontsize=10, title_fontsize=12)
    plt.tight_layout()
    st.pyplot(plt.gcf())
    st.subheader("Box Plot Data Preview")
    st.dataframe(selected_df_box.head())

# ===== 4. Weekly Trend (Matplotlib Line Chart) =====
st.title("Weekly Fuel Price Trend")
df_week = df_day.copy()
df_week.dropna(subset=['Date'], inplace=True)
# Create a column representing the start date of the week (default week starts on Monday)
df_week['Week'] = df_week['Date'].dt.to_period('W').apply(lambda r: r.start_time)
weeks = sorted(df_week['Week'].dropna().astype(str).unique())

st.sidebar.header("[Weekly Trend] Select Parameters")
selected_city_week = st.sidebar.selectbox("Select City (Weekly Data)", sorted(df_week['city'].dropna().unique()),
                                          key="week_city")
selected_week_str = st.sidebar.selectbox("Select Week Start Date", weeks, index=0, key="week_date")
selected_week = pd.to_datetime(selected_week_str)
st.write(f"### Data for {selected_city_week} in the week starting on {selected_week.date()}")

filtered_week = df_week[(df_week['city'] == selected_city_week) & (df_week['Week'] == selected_week)].copy()
if filtered_week.empty:
    st.warning(f"No data for {selected_city_week} in the week starting on {selected_week.date()}.")
else:
    avg_week = (
        filtered_week.groupby(['Date', 'fuelcode'])['price']
        .mean()
        .reset_index()
    )
    avg_week = avg_week.sort_values('Date')
    fig_week, ax_week = plt.subplots(figsize=(12, 6))
    for f in avg_week['fuelcode'].unique():
        subset = avg_week[avg_week['fuelcode'] == f]
        ax_week.plot(subset['Date'], subset['price'], marker='o', label=f)
    ax_week.set_title(f"{selected_city_week} Each Fuel Price (Week Start: {selected_week.date()})", fontsize=16)
    ax_week.set_xlabel("Date", fontsize=14)
    ax_week.set_ylabel("Average Price (cents/L)", fontsize=14)
    ax_week.legend(title="Fuel Type", loc='upper right', fontsize=10, title_fontsize=12)
    ax_week.grid(True)
    ax_week.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig_week)
    st.subheader("Weekly Price Data Preview")
    st.dataframe(filtered_week.head())

# ===== 5. Monthly Average Fuel Price Trend (Plotly Line Chart) =====
st.title("Interactive Monthly Fuel Price Trend")
month_df = month_result_df.copy()
month_df.sort_values(by='date_month', inplace=True)

cities_month = month_df['city'].dropna().unique().tolist()
fuel_types_month = month_df['fuelcode'].dropna().unique().tolist()

st.sidebar.header("[Monthly Trend] Select Parameters")
selected_city_month = st.sidebar.selectbox("Select City (Monthly Data)", cities_month, key="month_city")
selected_fuel_month = st.sidebar.selectbox("Select Fuel Type (Monthly Data)", fuel_types_month, key="month_fuel")

df_month_filtered = month_df[
    (month_df['city'] == selected_city_month) &
    (month_df['fuelcode'] == selected_fuel_month)
    ].copy()

if df_month_filtered.empty:
    st.warning(f"No data for {selected_fuel_month} in {selected_city_month}.")
else:
    fig_month = px.line(
        df_month_filtered,
        x='date_month',
        y='avg_month_price',
        title=f'{selected_city_month} - {selected_fuel_month} Average Price Trend',
        markers=True
    )
    fig_month.update_layout(
        xaxis_title='Month (Year-Month)',
        yaxis_title='Average Price (Avg Price)',
        xaxis=dict(tickformat='%Y-%m')
    )
    st.plotly_chart(fig_month)
    st.subheader("Monthly Data Preview")
    st.dataframe(df_month_filtered)