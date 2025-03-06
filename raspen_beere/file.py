from datetime import datetime
from pathlib import Path

SENSOR_DIR = Path.cwd() / "data" / "sensor"
SENSOR_DIR.mkdir(parents=True, exist_ok=True)


def get_sensor_file(now: datetime | None = None) -> tuple[Path, Path]:
    if now is None:
        now = datetime.now()
    file_name = now.strftime("%Y-%m-%d")
    json_file = SENSOR_DIR / f"{file_name}.json"
    lock_file = SENSOR_DIR / f"{file_name}.lock"
    return json_file, lock_file
