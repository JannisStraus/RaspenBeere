import adafruit_dht
import board


class DHT22:
    def __init__(self) -> None:
        self.dht_device = adafruit_dht.DHT22(board.D4)

    async def get_temperature(self) -> float | None:
        try:
            temperature = self.dht_device.temperature
        except RuntimeError:
            return None
        return float(temperature)

    async def get_humidity(self) -> float | None:
        try:
            humidity = self.dht_device.humidity
            return float(humidity)
        except RuntimeError:
            return None

    # async def get_temperature(self) -> float:
    #     # Führt den blockierenden Aufruf in einem separaten Thread aus
    #     return await asyncio.to_thread(self._try_get, self._get_temperature)

    # async def get_humidity(self) -> float:
    #     return await asyncio.to_thread(self._try_get, self._get_humidity)

    # def _try_get(self, func: Callable[[], float]) -> float:
    #     for _ in range(5):
    #         try:
    #             value = func()
    #             return value
    #         except RuntimeError:
    #             time.sleep(0.5)  # blockierender Aufruf - wird im Thread ausgeführt
    #             continue
    #     raise TimeoutError("There is a problem with the DHT22 Sensor.")

    # def _get_temperature(self) -> float:
    #     temperature = self.dht_device.temperature
    #     return float(temperature)

    # def _get_humidity(self) -> float:
    #     humidity = self.dht_device.humidity
    #     return float(humidity)
