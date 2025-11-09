import httpx
import asyncio
import logging
import pandas as pd

logger = logging.getLogger(__name__)
from config import YANDEX_TOKEN
from geo import get_coordinates

from body_templates_api import yandex_delivery_api_templates as templates


class YandexCargoClient:
    def __init__(self, token, base_url="https://b2b.taxi.yandex.net/b2b/cargo/integration/v2/"):
        self.base_url = base_url

        self.templates = {}
        self.templates['price_estimation'] = templates.body_estimation.copy()


        #self.session = requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru"
        }
    

    async def get_tariffs(self, from_location):
        url = self.base_url + "tariffs"
        body = {
            "start_point": [30.3057, 59.9728],
            "fullname": from_location
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, json=body)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.exception(e)
                return None
        
    

    async def get_prices_for_delivery(self, item_row, to_location, from_location='Каменоостровский, 61, 1'):
        url = self.base_url + 'check-price'
        body = self.templates['price_estimation'].copy()

        to_location_processed = str(to_location).replace(', ',',').strip()
        to_location_list = str(to_location_processed).split(',')

        coordinates_full_location = 'Санкт-Петербург, ' + to_location_processed
        coor_2, coor_1 = get_coordinates(coordinates_full_location)
        coordinates_destination = [coor_1, coor_2]

        #print(coor_2, coor_1)

        ######CHANGE THE TEMPLATE VALUES TO ACTUAL VALUES
        body['items'][0]['weight'] = float(item_row['detail_weight (kg)'].iloc[0])

        #destination route point ([1])
        body['route_points'][1]['fullname'] = f'Санкт-Петербург, {to_location_list[0]}, {to_location_list[1]}'
        body['route_points'][1]['street'] = to_location_list[0]
        body['route_points'][1]['building'] = to_location_list[1]

        body['route_points'][1]['coordinates'] = coordinates_destination


        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, json=body)
                response.raise_for_status()
                data = response.json()
                price = data['price']
                return float(price), data
            except httpx.HTTPError as e:
                print("Response content:", response.text)
                logger.exception(e)
                return None




async def main():
    table = pd.read_csv('TEST_TABLE.csv', sep=',')
    table['model_index'] = table['Бренд'] + ' ' + table['Модель']
    row = table.query(f'model_index == "Пульсар ШЭ 150-1800Э"')

    x = YandexCargoClient(YANDEX_TOKEN)

    price, result = await x.get_prices_for_delivery(to_location='Сикейроса, 20, 19', item_row=row)
    print(result)



if __name__ == '__main__':
    asyncio.run(main())