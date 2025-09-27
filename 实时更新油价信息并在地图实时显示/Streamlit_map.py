# Import required packages
import json
import queue
import math
import ast
import streamlit as st
import folium
import paho.mqtt.client as mqtt
from streamlit_folium import st_folium
# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 1. Configure constants
SYDNEY_COORDS = (-33.8688, 151.2093)
SYDNEY_ZOOM = 12

MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "COMP5339/530446891"
# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 2. Streamlit page initialization
st.set_page_config(page_title="FuelCheck: New South Wales oil price inquiry", layout="wide")

# Store all the data and filter the information
state = st.session_state
state.setdefault("stations", {})
state.setdefault("filter_brand", "All")
state.setdefault("filter_fuel", "All")
# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 3. Build a brand & oil product screening menu bar
with st.sidebar.form("filter_form"):
    # Brand list
    brands = sorted(
        {rec.get("brand", "") for rec in state["stations"].values() if rec.get("brand")}
    )
    brands.insert(0, "All")
    selected_brand = st.selectbox(
        "Gas Station Brand", brands, index=brands.index(state["filter_brand"])
    )

    # List of oil products
    fuels = sorted({
        ft
        for rec in state["stations"].values()
        for ft in rec.get("fuels", {})
    })
    fuels.insert(0, "All")
    selected_fuel = st.selectbox(
        "Fuel Type (Default U91)", fuels, index=fuels.index(state["filter_fuel"])
    )

    if st.form_submit_button(" Confirm the screening "):
        state["filter_brand"] = selected_brand
        state["filter_fuel"] = selected_fuel

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 4. MOTT connection
@st.cache_resource
def get_msg_queue():
    return queue.Queue()

# Initialize the message queue
_msg_queue = get_msg_queue()


def on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    try:
        # Decode the message payload from JSON and put it into the message queue
        payload = json.loads(msg.payload.decode())
        _msg_queue.put(payload)
    except json.JSONDecodeError:
        # Ignore the message if it's not valid JSON
        pass

@st.cache_resource
def init_mqtt_client():
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client

# initialization of MQTT
init_mqtt_client()

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 5. Parse and update the state["stations"]
# When the information is received, it is temporarily stored in the rec
while not _msg_queue.empty():
    rec = _msg_queue.get()
    
    # It is included fuel_price, fuel_update_time in rec 
    fuels   = ast.literal_eval(rec["fuel_price"]) 
    updates = ast.literal_eval(rec["fuel_update_time"]) 
    
    rec["fuels"]    = fuels
    rec["update_time"] = updates
    code = rec.get("code")
    if code:
        # Add or update in station
        state["stations"][code] = rec

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 6. Filtered gas station
# Show how many gas stations meet the conditions under the current screening criteria
candidates = []
for rec in state["stations"].values():
    if state["filter_brand"] != "All" and rec.get("brand") != state["filter_brand"]:
        continue
    if state["filter_fuel"] != "All" and state["filter_fuel"] not in rec.get("fuels", {}):
        continue
    candidates.append(rec)

st.sidebar.write(f"A total of {len(candidates)} stations were found")

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 7. Build markers and maps, real-time update
# A pop-up table appears when clicking on a gas station
TABLE_HEADER = """
<thead>
  <tr style="background-color:#2E8BC0; color:white;">
    <th style="padding:4px;">Fuel Type</th>
    <th style="padding:4px;">Prices</th>
    <th style="padding:4px;">Last Update Time</th>
  </tr>
</thead>
"""

# default to U91.     Determine the oil type to be displayed: If the user selects a certain oil type, display it.
fuel_to_show = state["filter_fuel"] if state["filter_fuel"] != "All" else "U91"

fg = folium.FeatureGroup(name="markers")

for rec in candidates:
    lat, lon = float(rec["latitude"]), float(rec["longitude"])
    # Extract the fuel price to be displayed from rec["fuels"]
    price = rec["fuels"].get(fuel_to_show, "—")
    brand = rec.get("brand", "")

    # Represent the points as rectangles
    html_icon = f"""
    <div style="
        display:inline-block;
        border:1px solid #888;
        border-radius:4px;
        overflow:hidden;
        font-family:Arial,sans-serif;
        text-align:center;
        box-shadow:1px 1px 2px rgba(0,0,0,0.3);
    ">
      <div style="
          background:#2E8BC0;
          color:white;
          font-size:12px;
          font-weight:bold;
          padding:2px 6px;
      ">
        {price}
      </div>
      <div style="
          background:white;
          color:#333;
          font-size:10px;
          padding:2px 4px;
      ">
        {brand}
      </div>
    </div>
    """
    icon = folium.DivIcon(html=html_icon)

    # Build a pop-up window when clicked
    # Filter "price=0" or "None" to generate table rows
    valid_fuels = {ft: p for ft, p in rec["fuels"].items() if p}
    rows = []
    for idx, (ft, p) in enumerate(valid_fuels.items()):
        upd = rec["update_time"].get(ft, "N/A")
        bgcolor = "#F1F6F9" if idx % 2 == 0 else "#FFFFFF"
        rows.append(
            f"<tr style='background-color:{bgcolor};'>"
            f"<td style='padding:3px;'>{ft}</td>"
            f"<td style='padding:3px;'>{p}</td>"
            f"<td style='padding:3px;'>{upd}</td>"
            "</tr>"
        )
    table_body = "<tbody>" + "".join(rows) + "</tbody>"

    popup_html = (
        "<div style='font-size:12px; font-family:Arial;'>"
        "<table style='border-collapse:collapse; width:100%; margin-bottom:6px;'>"
        + TABLE_HEADER + table_body +
        "</table>"
        f"<div style='margin-top:4px;'><b>Station Brand：</b>{rec.get('brand','')}</div>"
        f"<div><b>Address：</b>{rec.get('address',rec.get('name',''))}</div>"
        "</div>"
    )
    popup = folium.Popup(popup_html, max_width=300)

    # add to FeatureGroup
    folium.Marker(
        location=[lat, lon],
        icon=icon,
        popup=popup
    ).add_to(fg)

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------
# 8. Render the map with the default Sydney perspective
map_obj = folium.Map(
    location=SYDNEY_COORDS,
    zoom_start=SYDNEY_ZOOM,
    tiles="OpenStreetMap"
)
st_folium(
    map_obj,
    feature_group_to_add=fg,
    key="fuel_map",
    width=1200,
    height=800
)