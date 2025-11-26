from flask import Flask, request, jsonify,render_template
from flask_cors import CORS
import requests
import json
from datetime import datetime
import math
from bs4 import BeautifulSoup


ORS_API_KEY="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjUzNmEzNWQxODNhMjQ4ZGZiZDRlZmJiZTMxZDkwMDU3IiwiaCI6Im11cm11cjY0In0="
Base_url="https://api.openrouteservice.org"


app=Flask(__name__)

APSRTC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Authorization": "Bearer abhibus",
    "Content-Type": "application/json",
    "Origin": "https://apsrtclivetrack.com",
    "Referer": "https://apsrtclivetrack.com/",
    "x-api-key": "53693855434468454E714A596D44457A586975414F573833334833596A584D3333735938444A69357131303D"}
try:
    with open('place_id.json', 'r') as f:
        APSRTC_DATA = json.load(f)
        print(f"Loaded {len(APSRTC_DATA)} stops.")
except Exception as e:
    print(f"Error loading JSON: {e}")
    APSRTC_DATA = []


def sunposition(lat,lon,timestamp):

	lat_rad=math.radians(lat)
	long_rad=math.radians(lon)
	day_of_year=timestamp.timetuple().tm_yday
	hour=timestamp.hour+timestamp.minute/60.0
	declination=23.45 *math.sin(math.radians(360 * (day_of_year)/365)) # yes that is 23.45 since day is not like 24 hours rather 1/4 less 24
	dec_rad=math.radians(declination)
	hour_angle=15*(hour-12) # 15 degree per hour 

	ha_rad=math.radians(hour_angle)

	sun_altitude=(math.sin(lat_rad)*math.sin(dec_rad)+ math.cos(lat_rad)*math.cos(dec_rad)*math.cos(ha_rad))
	altitude = math.degrees(math.asin(sun_altitude))

	cos_azimuth=((math.sin(dec_rad)-math.sin(lat_rad)*sun_altitude)/(math.cos(lat_rad)*math.cos(math.asin(sun_altitude))))
	cos_azimuth = max(-1,min(1,cos_azimuth))
	azimuth=math.degrees(math.acos(cos_azimuth))

	if hour >12:
		azimuth=360-azimuth

	return azimuth,altitude

def bearing_calculation(lat1,long1,lat2,long2):

	lat1,long1,lat2,long2=map(math.radians,[lat1,long1,lat2,long2])

	dlong=long2-long1

	x=math.sin(dlong) * math.cos(lat2)
	y=(math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlong))

	bearing= math.atan2(x,y)
	bearing=math.degrees(bearing)
	bearing = (bearing + 360) % 360


	return bearing


def shade_finder(coordinates,start_time_str,duration_min):

	hour,minute=map(int,start_time_str.split(':'))

	start_time=datetime.now().replace(hour=hour,minute=minute,second=0,microsecond=0)

	shade_data=[]

	total_segments=len(coordinates)-1

	left_side_time=0
	right_side_time=0
	print(hour)
	if hour >= 18 or hour <6:
		return{
		'preferred_side': 'N/A',
            'preferred_window': 'Night journey - shade analysis not applicable',
            'left_shade_minutes': 0,
            'right_shade_minutes': 0,
            'shade_percentage': 0,
            'total_duration': duration_min,
            'is_night': True,
            'segments': []
		}

	for i in range(total_segments):

		lat1,long1=coordinates[i][1],coordinates[i][0]
		lat2,long2=coordinates[i+1][1],coordinates[i+1][0]

		segment_time=start_time.timestamp() + (duration_min * 60 * i/total_segments)
		current_time=datetime.fromtimestamp(segment_time)

		bearing= bearing_calculation(lat1,long1,lat2,long2)

		sun_azimuth,sun_altitude=sunposition(lat1,long1,current_time)

		if sun_altitude <0:
			continue
		relative_angle=(sun_azimuth - bearing + 360) % 360

		if 90 <= relative_angle <=270:
			shade_side="LEFT"
			left_side_time +=(duration_min/total_segments)
		else:
			shade_side="Right"
			right_side_time+=(duration_min/total_segments)
		shade_data.append({
			'segment':i,
			'bearing':round(bearing,2),
			'sun_azimuth': round(sun_azimuth,2),
			'sun_altitude':round(sun_altitude,2),
			'shade_side':shade_side,
			'time':current_time.strftime('%H:%M')

			})	
	if left_side_time > right_side_time:
		preferred_side="LEFT"
		preferred_window="Windows on the left side"
		shade_percentage=round((left_side_time/duration_min)*100,1)
	else:
		preferred_side="Right"
		preferred_window="Windows on the Right"
		shade_percentage=round((right_side_time/duration_min)*100,1)
	return {
        'preferred_side': preferred_side,
        'preferred_window': preferred_window,
        'left_shade_minutes': round(left_side_time, 1),
        'right_shade_minutes': round(right_side_time, 1),
        'shade_percentage': shade_percentage,
        'total_duration': duration_min,
        'segments': shade_data[:5]
    }

def scrape_fare_only(from_id, to_id):
    
    today_str = datetime.now().strftime("%d/%m/%Y")
    web_url = "https://www.apsrtconline.in/oprs-web/forward/booking/avail/services.do"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.apsrtconline.in/oprs-web/",
    }
    
    params = {
        "txtJourneyDate": today_str,
        "startPlaceId": from_id,
        "endPlaceId": to_id,
        "txtLinkJourneyDate": today_str,
        "ajaxAction": "fw",
        "qryType": "0"
    }
    
    try:
        response = requests.get(web_url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            fare_map = {}
            
            # Find all bus services
            services = soup.find_all('div', class_='rSetForward')
            
            for service in services:
                try:
                    # Get bus number
                    bus_no_tag = service.find('div', class_='srvceNO')
                    bus_no = bus_no_tag.get_text(strip=True) if bus_no_tag else None
                    
                    # Get fare (THIS IS THE KEY PART)
                    fare_tag = service.find('span', class_='TickRate')
                    fare = fare_tag.get_text(strip=True) if fare_tag else "N/A"
                    
                    if bus_no:
                        fare_map[bus_no] = fare
                        
                except Exception as e:
                    continue
            
            return fare_map
        else:
            return {}
            
    except Exception as e:
        print(f"Fare scraping error: {e}")
        return {}


@app.route('/get_route', methods=['POST'])
def get_route():
    req_data = request.get_json()
    if not req_data:
        return jsonify({"error": "No data received"}), 400

    start_coords = req_data.get('start', [77.2090, 28.6139])
    end_coords = req_data.get('end', [78.0081, 27.1767]) 

    url = f"{Base_url}/v2/directions/driving-hgv/geojson"
    params = {
        "coordinates": [start_coords, end_coords]
    }
    
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": 'application/json'
    }
    response = requests.post(url, json=params, headers=headers)

    if response.status_code != 200:
        print("API Error:", response.text)
        return jsonify({"error": "ERROR HAI BHAI!! ERROS"}), 400

    data = response.json()

    try:
        r_coordinate = data['features'][0]['geometry']['coordinates']
        summary = data['features'][0]['properties']['summary']
        dist_km=round(summary['distance']/1000,1)
        duration_sec=summary['duration']
        duration_minutes = int(duration_sec / 60)
        hours=int(duration_sec//3600)
        current_time_str = datetime.now().strftime("%H:%M")
        shade_info = shade_finder(r_coordinate, current_time_str, duration_minutes)
        print('here')
        minutes=int((duration_sec %3600)//60)
        duration_str=f"{hours}h {minutes}min" if hours>0 else f"{minutes}min"
        
        leafly = [[coord[1], coord[0]] for coord in r_coordinate]
        print(duration_str)

        return jsonify({
            'path': leafly,
            'start_point': [start_coords[1], start_coords[0]],
            'end_point': [end_coords[1], end_coords[0]],
            'distance': f"{dist_km} km",
            'duration': duration_str,
            'shade_analysis': shade_info
        })
    except (KeyError, IndexError) as e:
        return jsonify({"error": "Could not parse route data"}), 500
@app.route('/api/search',methods=['GET'])
def api_search():
	query=request.args.get('q','')

	if len(query)<3:
		return jsonify([])
	url=f'{Base_url}/geocode/search'

	param={
	"api_key":ORS_API_KEY,
	"text":query,
	"size":5,
	"boundary.country":"IN"
	}
	try:
		response=requests.get(url,params=param)

		if response.status_code ==200:
			data=response.json()
			suggestions=[]

			for feature in data.get('features',[]):
				suggestions.append({
					"label":feature['properties']['label'],
					"coords":feature['geometry']['coordinates']
					})
			return jsonify(suggestions)
	except Exception as e:
		print(f"Geocode error:{e}")

	return jsonify([])

@app.route('/api/resolve-apsrtc-id',methods=['POST'])
def get_place_id():
	req_data=request.get_json()

	if not req_data or 'address' not in req_data:
		return jsonify({"error":"YEH SAHI BHAT NAHI HAI.. I got not place to give ID for"}),400
	search_string = req_data.get('address','').upper()
	for depot in APSRTC_DATA:
		stop_name = depot.get('value','').upper()
		if stop_name and stop_name in search_string:
			return jsonify({
				"id":depot['id'],
				"match":depot['value']
				})
	return jsonify({ "id":None})

@app.route('/api/find-buses',methods=['POST'])
def findbus():
	req_data = request.get_json()
	from_id = req_data.get('fromId')
	to_id = req_data.get('toId')
	if not from_id or not to_id:
		return jsonify({"error": "Missing Start or End IDs"}), 400
	url = "https://utsappapicached01.apsrtconline.in/uts-vts-api/services/all"
	try:
		payload = {
            "sourceLinkId": int(from_id),
            "destinationLinkId": int(to_id),
            "sourcePlaceId": int(from_id),
            "destinationPlaceId": int(to_id),
            "userId": "1363789069449", 
            "versionCode": "2020254",
            "apiVersion": 1
        }
	except ValueError:
		return jsonify({"error": "IDs must be numeric"}), 400
	try:
		response = requests.post(url, headers=APSRTC_HEADERS, json=payload)
		if response.status_code == 200:
			data = response.json()
			fare_data=scrape_fare_only(from_id,to_id)
			fare_map=fare_data
			fare_value=[]
			for fare in fare_map.values():
				try:
					fare_value.append(int(fare))
				except:
					pass
			avg_fare = round(sum(fare_value) / len(fare_value)) if fare_value else None
			if data.get('data') and isinstance(data['data'],list):
				for bus in data['data']:
					bus_no=bus.get('oprsNo','').strip()
					bus['fare']=fare_map.get(bus_no,'N/A')
					print(bus['fare'])
				data['averageFare'] = avg_fare
				print(data['averageFare'])
			return jsonify(data)
		else:
			print(f"APSRTC Error: {response.status_code} - {response.text}")
			return jsonify({"error": "External API Failed", "details": response.text}), 500

	except Exception as e:
		print(f"Request Error: {e}")
		return jsonify({"error": str(e)}), 500

@app.route('/api/find-buses2', methods=['POST'])
def findbus2():
    req_data = request.get_json()
    from_id = req_data.get('fromId')
    to_id = req_data.get('toId')

    if not from_id or not to_id:
        return jsonify({"error": "Missing Start or End IDs"}), 400

    today_str = datetime.now().strftime("%d/%m/%Y")
    
    web_url = "https://www.apsrtconline.in/oprs-web/forward/booking/avail/services.do"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.apsrtconline.in/oprs-web/",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    params = {
        "txtJourneyDate": today_str,
        "startPlaceId": from_id,
        "endPlaceId": to_id,
        "txtLinkJourneyDate": today_str,
        "ajaxAction": "fw",
        "covidBkgEnable": "",
        "qryType": "0"
    }

    try:
        print(f"Web: {from_id} -> {to_id} on {today_str}")
        response = requests.get(web_url, headers=headers, params=params)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            bus_list = []
            services = soup.find_all('div', class_='result-grid-box')
            if not services:
                services = soup.select('.srvceNO') 
            results = soup.find_all('div', class_='search-result-item') 
            if not results:
                 results = soup.find_all('div', class_='rSet')

            for service in results:
                try:

                    type_tag = service.find('h3') or service.find('div', class_='srvceName')
                    srv_type = type_tag.get_text(strip=True) if type_tag else "BUS"


                    no_tag = service.find('div', class_='srvceNO')
                    oprs_no = no_tag.get_text(strip=True) if no_tag else "N/A"

                    start_tag = service.find('span', class_='startTime')
                    end_tag = service.find('span', class_='endTime')
                    
                    start_time = start_tag.get_text(strip=True) if start_tag else "00:00"
                    end_time = end_tag.get_text(strip=True) if end_tag else "00:00"
                    bus_obj = {
                        "oprsNo": oprs_no,
                        "serviceType": srv_type,
                        "serviceStartTime": start_time,
                        "serviceEndTime": end_time,
                        "depotName": "APSRTC", # Web results often hide depot name
                        "journeyDate": today_str
                    }
                    bus_list.append(bus_obj)
                except Exception as p_err:
                    print(f"Skipped a row due to error: {p_err}")
                    continue

            print(f"Parsed {len(bus_list)} buses from HTML.")
            return jsonify(bus_list)
            
        else:
            print(f"Web Error: {response.status_code}")
            return jsonify({"error": "Web Failed"}), 500

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-bus-stops', methods=['POST'])
def get_bus_stops():
    req_data = request.get_json()
    doc_id = req_data.get('docId')
    
    if not doc_id:
        return jsonify({"error": "Missing docId"}), 400

    url = "https://utsappapicached01.apsrtconline.in/uts-vts-api/servicewaypointdetails/bydocid"
    
    # Using the headers you provided
    payload = {"docId": doc_id}
    
    try:
        response = requests.post(url, headers=APSRTC_HEADERS, json=payload)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": "Failed to fetch stops", "details": response.text}), response.status_code
    except Exception as e:
        print(f"Stops API Error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/')
def index():
    return render_template('index.html')


if __name__ =="__main__":

    app.run(debug=True)
