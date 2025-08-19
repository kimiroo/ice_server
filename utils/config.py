import json
import logging
from typing import List, Union

CONFIG_PATH = 'config.json'

log = logging.getLogger(__name__)

class Config:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port = 8080

        self.onvif_enabled: bool = False
        self.onvif_host: str = None
        self.onvif_port: int = None
        self.onvif_username: str = None
        self.onvif_password: str = None

        self.go2rtc_host: str = None
        self.go2rtc_src: str = None

        self.webhook_enabled: bool = False
        self.webhook_url: str = None
        self.webhook_method: str = None
        self.webhook_data: Union[str, dict] = None
        self.webhook_headers: dict = None
        self.webhook_on_ignored: bool = False
        self.webhook_on_event_type: List[str] = []
        self.webhook_on_event_source: List[str] = []

        config_data = {}

        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                log.info('Successfully loaded config file.')

        except Exception as e:
            log.critical(f'Failed to load config file: {e}')

        try:
            # Load Server Config
            self.host = config_data.get('host', '0.0.0.0')
            self.port = config_data.get('port', 8080)

            # Load ONVIF Config
            onvif_conf = config_data.get('onvif', {})
            self.onvif_host = onvif_conf.get('host', None)
            self.onvif_port = onvif_conf.get('port', 80)
            self.onvif_username = onvif_conf.get('username', '')
            self.onvif_password = onvif_conf.get('password', '')

            if isinstance(self.onvif_host, str) and self.onvif_host != '':
                self.onvif_enabled = True
            else:
                self.onvif_enabled = False

            # Load go2rtc Stream Config
            go2rtc_conf = config_data.get('go2rtc', {})
            self.go2rtc_host = go2rtc_conf.get('host', None)
            self.go2rtc_src = go2rtc_conf.get('src', None)

            # Load Webhook Config
            webhook_conf = config_data.get('webhook', {})
            self.webhook_url = webhook_conf.get('url', None)
            self.webhook_method = webhook_conf.get('method', 'GET')
            self.webhook_data = webhook_conf.get('data', None)
            self.webhook_headers = webhook_conf.get('headers', None)
            self.webhook_on_ignored = webhook_conf.get('onIgnored', False)
            self.webhook_on_event_type = webhook_conf.get('onEventType', [])
            self.webhook_on_event_source = webhook_conf.get('onEventSource', [])

            if isinstance(self.webhook_url, str) and self.webhook_url != '':
                self.webhook_enabled = True
            else:
                self.webhook_enabled = False

        except Exception as e:
            log.critical(f'Failed to parse config file: {e}')

CONFIG = Config()