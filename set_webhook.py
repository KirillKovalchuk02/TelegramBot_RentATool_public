import requests

from config import TOKEN, NGROK_TUNNEL_URL

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
#WEBHOOK_PATH = f'/bot/{TOKEN}'
#WEBHOOK_URL = f'{NGROK_TUNNEL_URL}{WEBHOOK_PATH}'
endpoint_name = 'webhook'

response = requests.get(f"{TELEGRAM_API}/setWebhook?url={NGROK_TUNNEL_URL}/{endpoint_name}")
print(TELEGRAM_API)
print(response.text)
