import requests
import json

url = "https://api.tomorrow.io/v4/timelines"

querystring = {
"location":"-26.6559759, 153.0918365",         #lat long of sunshine coast 
"fields":["temperature","windSpeed","humidity"],
"units":"metric",                               #celcius    
"timesteps":"current",                               
"apikey":"VM5OHj1SWudXbY1U1OWELCO4Iyp5q6xR"}


response = requests.request("GET", url, params=querystring)
print(response.text)

data = json.loads(response.text)
with open('weather.json','w') as f:   #loggin the data into json file
    json.dump(data, f, indent=2)