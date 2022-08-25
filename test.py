import requests

url = "https://api.tomorrow.io/v4/timelines"

querystring = {
"location":"-26.6559759, -153.0918365",
"fields":["temperature"],
"units":"metric",
"timesteps":"1d",
"apikey":"VM5OHj1SWudXbY1U1OWELCO4Iyp5q6xR"}

response = requests.request("GET", url, params=querystring)
print(response.text)