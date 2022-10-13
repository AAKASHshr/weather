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

