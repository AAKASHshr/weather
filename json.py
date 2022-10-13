import json
from textwrap import indent

with open('weather.json', 'r') as f:
    data = json.load(f)

print(data['data']['timelines']['intervals'])