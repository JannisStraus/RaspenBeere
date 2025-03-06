import time
from typing import Callable

import adafruit_dht
import board


class DHT22:
    def __init__(self) -> None:
        self.dht_device = adafruit_dht.DHT22(board.D4)

    def get_temperature(self) -> float:
        return self._try_get(self._get_temperature)

    def get_humidity(self) -> float:
        return self._try_get(self._get_humidity)

    def _try_get(self, func: Callable[[], float]) -> float:
        for _ in range(15):
            try:
                value = func()
                return value
            except RuntimeError:
                time.sleep(2)
                continue
        raise TimeoutError("There is a problem with the DHT22 Sensor.")

    def _get_temperature(self) -> float:
        temperature = self.dht_device.temperature
        return float(temperature)

    def _get_humidity(self) -> float:
        humidity = self.dht_device.humidity
        return float(humidity)
