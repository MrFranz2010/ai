"""Meteo e località tramite Open-Meteo (nessuna chiave API).

Open-Meteo è gratuito e senza registrazione: il dock chiede le coordinate alla
geocoding API solo la prima volta che si imposta una città, poi salva i valori
nella configurazione.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Codici WMO usati da Open-Meteo.
WMO_CODES = {
    0: ("Sereno", "sun"),
    1: ("Quasi sereno", "sun"),
    2: ("Parzialmente nuvoloso", "cloud"),
    3: ("Nuvoloso", "cloud"),
    45: ("Nebbia", "fog"),
    48: ("Nebbia gelata", "fog"),
    51: ("Pioviggine leggera", "rain"),
    53: ("Pioviggine", "rain"),
    55: ("Pioviggine forte", "rain"),
    56: ("Pioviggine gelata", "rain"),
    57: ("Pioviggine gelata", "rain"),
    61: ("Pioggia leggera", "rain"),
    63: ("Pioggia", "rain"),
    65: ("Pioggia forte", "rain"),
    66: ("Pioggia gelata", "rain"),
    67: ("Pioggia gelata", "rain"),
    71: ("Neve leggera", "snow"),
    73: ("Neve", "snow"),
    75: ("Neve abbondante", "snow"),
    77: ("Granelli di neve", "snow"),
    80: ("Rovesci leggeri", "rain"),
    81: ("Rovesci", "rain"),
    82: ("Rovesci violenti", "rain"),
    85: ("Rovesci di neve", "snow"),
    86: ("Rovesci di neve", "snow"),
    95: ("Temporale", "storm"),
    96: ("Temporale con grandine", "storm"),
    99: ("Temporale con grandine", "storm"),
}

METRIC_UNITS = {"temperature": "°C", "wind": "km/h"}
IMPERIAL_UNITS = {"temperature": "°F", "wind": "mph"}


@dataclass(frozen=True)
class WeatherNow:
    city: str = ""
    temperature: float = 0.0
    apparent: float = 0.0
    code: int = 0
    label: str = "—"
    icon: str = "cloud"
    is_day: bool = True
    minimum: float | None = None
    maximum: float | None = None
    wind: float | None = None
    units: str = "metric"
    updated_at: float = 0.0
    error: str = ""

    @property
    def unit_symbol(self) -> str:
        return (IMPERIAL_UNITS if self.units == "imperial" else METRIC_UNITS)["temperature"]

    @property
    def wind_symbol(self) -> str:
        return (IMPERIAL_UNITS if self.units == "imperial" else METRIC_UNITS)["wind"]

    @property
    def temperature_text(self) -> str:
        return f"{round(self.temperature)}{self.unit_symbol}"

    @property
    def range_text(self) -> str:
        if self.minimum is None or self.maximum is None:
            return ""
        return f"min {round(self.minimum)}° · max {round(self.maximum)}°"


def describe(code, is_day=True):
    """Etichetta e icona per un codice WMO."""
    label, icon = WMO_CODES.get(int(code or 0), ("—", "cloud"))
    if icon == "sun" and not is_day:
        return label, "moon"
    return label, icon


def geocode_url(city: str) -> str:
    query = urllib.parse.urlencode({
        "name": city.strip(),
        "count": 1,
        "language": "it",
        "format": "json",
    })
    return f"{GEOCODE_URL}?{query}"


def forecast_url(latitude, longitude, units="metric") -> str:
    params = {
        "latitude": f"{float(latitude):.4f}",
        "longitude": f"{float(longitude):.4f}",
        "current": "temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 1,
    }
    if units == "imperial":
        params["temperature_unit"] = "fahrenheit"
        params["wind_speed_unit"] = "mph"
    return f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"


def _first_float(values):
    if isinstance(values, list) and values:
        try:
            return float(values[0])
        except (TypeError, ValueError):
            return None
    return None


def parse_geocode(payload):
    """Restituisce (nome, latitudine, longitudine) del primo risultato."""
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    try:
        latitude = float(first["latitude"])
        longitude = float(first["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(first.get("name") or "").strip()
    country = str(first.get("country_code") or first.get("country") or "").strip()
    label = f"{name}, {country}" if name and country and len(country) <= 3 else name
    return label or "Località", latitude, longitude


def parse_forecast(payload, units="metric", city="") -> WeatherNow:
    """Costruisce lo stato meteo dalla risposta di Open-Meteo."""
    if not isinstance(payload, dict):
        return WeatherNow(units=units, city=city, error="Risposta meteo non valida.")
    current = payload.get("current") or {}
    if not isinstance(current, dict):
        current = {}
    daily = payload.get("daily") or {}
    if not isinstance(daily, dict):
        daily = {}
    try:
        temperature = float(current.get("temperature_2m"))
    except (TypeError, ValueError):
        return WeatherNow(units=units, city=city, error="Meteo non disponibile.")
    try:
        apparent = float(current.get("apparent_temperature"))
    except (TypeError, ValueError):
        apparent = temperature
    try:
        code = int(current.get("weather_code") or 0)
    except (TypeError, ValueError):
        code = 0
    is_day = bool(current.get("is_day", 1))
    label, icon = describe(code, is_day)
    try:
        wind = float(current.get("wind_speed_10m"))
    except (TypeError, ValueError):
        wind = None
    return WeatherNow(
        city=city,
        temperature=temperature,
        apparent=apparent,
        code=code,
        label=label,
        icon=icon,
        is_day=is_day,
        minimum=_first_float(daily.get("temperature_2m_min")),
        maximum=_first_float(daily.get("temperature_2m_max")),
        wind=wind,
        units=units,
        updated_at=time.time(),
    )


def http_json(url, timeout=12):
    request = urllib.request.Request(
        url, headers={"User-Agent": "nokk-dock/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class WeatherService:
    """Aggiorna il meteo in un thread e conserva l'ultimo valore valido."""

    def __init__(self, config, fetcher=None, resolver=None):
        self.config = dict(config or {})
        self.fetcher = fetcher or http_json
        self.resolver = resolver or http_json
        self.lock = threading.Lock()
        self.state = WeatherNow(units=self.config.get("units", "metric"))
        self.coordinates = None
        self.stop_event = threading.Event()
        self.thread = None

    def _resolve(self, city):
        try:
            payload = self.resolver(geocode_url(city))
        except Exception as error:  # noqa: BLE001 - rete non disponibile
            return None, str(error)
        resolved = parse_geocode(payload)
        if resolved is None:
            return None, f"Località «{city}» non trovata."
        return resolved, ""

    def refresh(self) -> WeatherNow:
        city = (self.config.get("city") or "").strip()
        latitude = self.config.get("latitude")
        longitude = self.config.get("longitude")
        name = city
        if latitude is None or longitude is None:
            if not city:
                state = WeatherNow(
                    units=self.config.get("units", "metric"),
                    error="Imposta la tua città nelle impostazioni del dock.",
                )
                with self.lock:
                    self.state = state
                return state
            resolved, error = self._resolve(city)
            if resolved is None:
                state = WeatherNow(
                    units=self.config.get("units", "metric"), city=city, error=error
                )
                with self.lock:
                    self.state = state
                return state
            name, latitude, longitude = resolved
            with self.lock:
                self.coordinates = (name, latitude, longitude)
        units = self.config.get("units", "metric")
        try:
            payload = self.fetcher(forecast_url(latitude, longitude, units))
        except Exception as error:  # noqa: BLE001 - rete non disponibile
            with self.lock:
                previous = self.state
            if previous.updated_at:
                return previous
            state = WeatherNow(units=units, city=name, error=f"Meteo non raggiungibile ({error}).")
            with self.lock:
                self.state = state
            return state
        state = parse_forecast(payload, units=units, city=name)
        with self.lock:
            self.state = state
        return state

    def get(self) -> WeatherNow:
        with self.lock:
            return self.state

    def start(self, on_update, interval_minutes=20):
        """Avvia il refresh periodico; `on_update` è chiamato dal thread."""
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()

        def loop():
            while not self.stop_event.is_set():
                state = self.refresh()
                try:
                    on_update(state)
                except Exception:  # noqa: BLE001 - l'interfaccia non deve fermare il loop
                    pass
                self.stop_event.wait(max(60, int(interval_minutes) * 60))

        self.thread = threading.Thread(target=loop, name="nokk-dock-weather", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
