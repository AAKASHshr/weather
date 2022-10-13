<<<<<<< HEAD
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
import json


# returns JSON object as
# a dictionary

app_version = 1.30
with open('weather.json', 'r') as file:
    json_data = json.load(file)

token = "whcBdFBOMnUYN4cg7awyH-k8xGNmpxFgiFop6eX4OT68RTgcmd-Vt-B5L3XgNf2S58-I93DH7pFeoKPYCqZjCQ=="
org = "Aakash.shrestha@ui.city"
bucket = "weather"

with InfluxDBClient(url="http://localhost:8086", token=token, org=org, default_tags={'appversion': str(app_version)}, debug=False) as client:
    def flatten_interval(interval):
        values = interval['values']
        values['startTime'] = interval['startTime']
        return values


    # get timelines
    timelines = json_data['data']['timelines']
    # get intervals
    intervals = list(map(lambda timeline: timeline['intervals'], timelines))
    # flatten intervals
    intervals = [flatten_interval(interval) for sublist in intervals for interval in sublist]
    
    # write data
    client.write_api(write_options=SYNCHRONOUS).write(bucket=bucket,
                                                      record=intervals,
                                                      record_measurement_name="weather",
                                                      record_time_key="startTime",
                                                      record_field_keys=["humidity", "temperature", "windSpeed"])
=======
import json
import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

token = os.environ.get("INFLUXDB_TOKEN")
org = "aakash.shrestha@ui.city"
url = "https://ap-southeast-2-1.aws.cloud2.influxdata.com"

client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)

bucket="weather"

with open('weather.json', 'r') as file:
    json_data = json.load(file)

write_api = client.write_api(write_options=SYNCHRONOUS)
   
for value in range(5):
  point = (
    Point("measurement")
    .tag("tagname1", "tagvalue1")
    .field(json_data, value)
  )
  write_api.write(bucket=bucket, org="aakash.shrestha@ui.city", record=point)
  time.sleep(1) # separate points by 1 second

>>>>>>> b99c2b0 (adding database)
