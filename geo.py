import requests
from config import GEOCODER_API_KEY


def get_coordinates(address: str):
    url = "https://geocode-maps.yandex.ru/v1"
    params = {
        "apikey": GEOCODER_API_KEY,
        "format": "json",
        "geocode": address
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()


    try:
        pos = (
            data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        )
        lon, lat = pos.split(" ")
        return float(lat), float(lon)  # (lat, lon) order
    except (KeyError, IndexError):
        return None

