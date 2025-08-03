import json
import logging
from typing import Union

CONFIG_PATH = 'config.json'
CONFIG = None

log = logging.getLogger(__name__)

class Config:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port = 8080

        self.onvif_host: str = None
        self.onvif_port: int = None
        self.onvif_username: str = None
        self.onvif_password: str = None

        self.webhook_enabled: bool = False
        self.webhook_url: str = None
        self.webhook_method: str = None
        self.webhook_data: Union[str, dict] = None
        self.webhook_headers: dict = None

        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

                # Load Server Config
                self.host = config_data.get('host', '0.0.0.0')
                self.port = config_data.get('port', 8080)

                # Load ONVIF Config
                onvif_conf = config_data.get('onvif', {})
                self.onvif_host = onvif_conf.get('host', None)
                self.onvif_port = onvif_conf.get('port', 80)
                self.onvif_username = onvif_conf.get('username', '')
                self.onvif_password = onvif_conf.get('password', '')

                # Load Webhook Config
                webhook_conf = config_data.get('webhook', {})
                self.webhook_url = webhook_conf.get('url', None)
                self.webhook_method = webhook_conf.get('method', 'GET')
                self.webhook_data = webhook_conf.get('data', None)
                self.webhook_headers = webhook_conf.get('headers', None)

                if isinstance(self.webhook_url, str) and self.webhook_url != '':
                    self.webhook_enabled = True
                else:
                    self.webhook_enabled = False

                log.info('Successfully loaded config file.')

        except Exception as e:
            log.critical(f'Failed to load config file: {e}')

CONFIG = Config()