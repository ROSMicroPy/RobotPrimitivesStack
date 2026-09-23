"""Async station connection using persisted environment credentials."""
from rpstack.execution_engine import asyncio


class WifiService:
    def __init__(self, node, ssid_env="WIFI_SSID", password_env="WIFI_PASSWORD", timeout_s=30):
        self.ssid_env, self.password_env, self.timeout_s = ssid_env, password_env, timeout_s
        self.wlan = None

    async def start(self):
        import network
        from rpstack.env.envstore import getEnv
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        if not self.wlan.isconnected():
            ssid = getEnv(self.ssid_env)
            if not ssid:
                raise ValueError("missing environment variable " + self.ssid_env)
            self.wlan.connect(ssid, getEnv(self.password_env) or "")
            async def connected():
                while not self.wlan.isconnected():
                    await asyncio.sleep(0.1)
            await asyncio.wait_for(connected(), self.timeout_s)

    async def run(self):
        while True:
            if not self.wlan.isconnected():
                raise RuntimeError("WiFi connection lost")
            await asyncio.sleep(1)

    def stop(self):
        if self.wlan:
            self.wlan.disconnect()
