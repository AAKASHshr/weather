import requests
import json
import schedule
import time

url = "https://api.tomorrow.io/v4/timelines"

querystring = {
"location":"-26.6559759, 153.0918365",         #lat long of sunshine coast 
"fields":["temperature","sunriseTime","sunsetTime","windSpeed","humidity"],
"units":"metric",                               #celcius    
"timesteps":"1h",   
"startTime":"now",
"endTime":"nowPlus1h",                             
"apikey":"VM5OHj1SWudXbY1U1OWELCO4Iyp5q6xR"}

def switch():
    #schedule.every().day.at("00:00").do(check)

    schedule.every(10).seconds.do(start)

    while True:
        schedule.run_pending()
        time.sleep(1)


def start():
    response = requests.request("GET", url, params=querystring)
    print(response.text)

    data = json.loads(response.text)
    with open('weather.json','w') as f:   #loggin the data into json file
        json.dump(data, f, indent=2)

if __name__=="__main__":
    switch()