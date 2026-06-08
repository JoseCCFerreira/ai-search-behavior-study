"""Offline importer for Strava account export zip files."""

from __future__ import annotations

import json
import logging
import math
import gzip
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zipfile import ZipFile

import pandas as pd

try:
    from fitparse import FitFile
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    FitFile = None

from src.coach import PerformanceCoach
from src.database.create_database import DatabaseInitializer
from src.database.db_connection import DatabaseConnection, get_direct_connection
from src.metrics import PerformanceAnalytics

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Summary of a Strava export import."""

    athlete_id: int
    rows_seen: int
    activities_loaded: int
    activities_failed: int
    metrics_rows: int
    recommendations_created: int
    stream_points_loaded: int = 0
    activities_with_streams: int = 0


class StravaExportImporter:
    """Import Strava's GDPR/account export into the local DuckDB schema."""

    ACTIVITY_TYPE_MAP = {
        "Volta de bicicleta": "Ride",
        "Bicicleta": "Ride",
        "Corrida": "Run",
        "Caminhada": "Walk",
        "Passeio": "Walk",
        "Trilho": "Run",
        "Natação": "Swim",
        "Caminhada pedestre": "Hike",
        "Hike": "Hike",
        "Run": "Run",
        "Ride": "Ride",
        "Walk": "Walk",
        "Swim": "Swim",
        "Workout": "Workout",
        "Treino": "Workout",
        "Treino com peso": "Workout",
        "Elítica": "Workout",
        "Crossfit": "Workout",
        "Futebol": "Workout",
    }

    MONTHS_PT = {
        "jan.": 1,
        "fev.": 2,
        "mar.": 3,
        "abr.": 4,
        "mai.": 5,
        "jun.": 6,
        "jul.": 7,
        "ago.": 8,
        "set.": 9,
        "out.": 10,
        "nov.": 11,
        "dez.": 12,
    }

    def __init__(
        self,
        zip_path: str | Path,
        db: Optional[DatabaseConnection] = None,
        database_path: Optional[str] = None,
    ):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Strava export not found: {self.zip_path}")

        if database_path and db is None:
            DatabaseInitializer(database_path).initialize(with_mock_data=False)
            self.db = get_direct_connection(database_path)
        else:
            self.db = db or get_direct_connection()
        self._owns_db = db is None
        self._zip: Optional[ZipFile] = None

    def import_export(self, refresh_outputs: bool = True) -> ImportResult:
        """Import activities.csv and refresh analytics/coach outputs."""
        profile = self._read_profile()
        athlete_id = profile["athlete_id"]
        self._upsert_athlete_profile(profile)

        df = self._read_activities()
        loaded = 0
        failed = 0
        stream_points_loaded = 0
        activities_with_streams = 0

        with ZipFile(self.zip_path) as z:
            self._zip = z
            for _, row in df.iterrows():
                try:
                    activity = self._normalize_activity_row(row, athlete_id)
                    streams_loaded = self._save_activity(activity)
                    stream_points_loaded += streams_loaded
                    if streams_loaded:
                        activities_with_streams += 1
                    loaded += 1
                except Exception as exc:
                    failed += 1
                    logger.exception(
                        "Failed to import Strava activity row %s: %s",
                        row.get("ID da atividade"),
                        exc,
                    )
            self._zip = None

        metrics_rows = 0
        recommendations_created = 0
        if refresh_outputs and loaded:
            metrics_rows = PerformanceAnalytics(self.db).refresh_all(athlete_id).metrics_rows
            recommendations_created = PerformanceCoach(self.db).generate_recommendations(
                athlete_id
            ).recommendations_created

        self._record_import_history(len(df), loaded, failed)
        return ImportResult(
            athlete_id=athlete_id,
            rows_seen=len(df),
            activities_loaded=loaded,
            activities_failed=failed,
            metrics_rows=metrics_rows,
            recommendations_created=recommendations_created,
            stream_points_loaded=stream_points_loaded,
            activities_with_streams=activities_with_streams,
        )

    def _read_activities(self) -> pd.DataFrame:
        with ZipFile(self.zip_path) as z:
            with z.open("activities.csv") as f:
                return pd.read_csv(f, encoding="utf-8-sig")

    def _read_profile(self) -> Dict[str, Any]:
        with ZipFile(self.zip_path) as z:
            with z.open("profile.csv") as f:
                profile = pd.read_csv(f, encoding="utf-8-sig").iloc[0]

        first_name = self._clean_value(profile.get("Nome próprio")) or ""
        last_name = self._clean_value(profile.get("Apelido")) or ""
        athlete_name = f"{first_name} {last_name}".strip() or "Strava Athlete"

        return {
            "athlete_id": int(profile["ID do atleta"]),
            "athlete_name": athlete_name,
            "profile_picture_url": None,
            "city": self._clean_value(profile.get("Cidade")),
            "state": self._clean_value(profile.get("Estado")),
            "country": self._clean_value(profile.get("País")),
            "sex": self._clean_value(profile.get("Sexo")),
            "premium": False,
        }

    def _upsert_athlete_profile(self, profile: Dict[str, Any]) -> None:
        self.db.execute(
            "DELETE FROM athlete_profile WHERE athlete_id = ?",
            (profile["athlete_id"],),
        )
        self.db.insert_records("athlete_profile", [profile])

    def _normalize_activity_row(self, row: pd.Series, athlete_id: int) -> Dict[str, Any]:
        activity_id = int(row["ID da atividade"])
        activity_datetime = self._parse_strava_datetime(str(row["Data da atividade"]))
        activity_type = self._map_activity_type(row.get("Tipo de atividade"))
        distance_meters = self._number(row.get("Distância.1"))
        if distance_meters is None:
            distance_km = self._number(row.get("Distância"))
            distance_meters = (distance_km or 0) * 1000

        moving_time = self._number(row.get("Tempo em movimento")) or self._number(
            row.get("Tempo decorrido.1")
        )
        elapsed_time = self._number(row.get("Tempo decorrido.1")) or self._number(
            row.get("Tempo decorrido")
        )

        raw_payload = {
            key: self._clean_value(value)
            for key, value in row.to_dict().items()
        }

        return {
            "activity_id": activity_id,
            "athlete_id": athlete_id,
            "activity_name": self._clean_value(row.get("Nome da atividade"))
            or f"Activity {activity_id}",
            "activity_type": activity_type,
            "activity_date": activity_datetime.date(),
            "distance_meters": int(round(distance_meters or 0)),
            "moving_time_seconds": int(round(moving_time or 0)),
            "elapsed_time_seconds": int(round(elapsed_time or moving_time or 0)),
            "average_speed_mps": self._number(row.get("Velocidade média")),
            "max_speed_mps": self._number(row.get("Velocidade máx.")),
            "average_heartrate": self._int_number(row.get("Frequência cardíaca média")),
            "max_heartrate": self._int_number(row.get("Frequência cardíaca máxima.1"))
            or self._int_number(row.get("Frequência cardíaca máxima")),
            "total_elevation_gain": self._number(row.get("Ganho de elevação")),
            "total_elevation_loss": self._number(row.get("Perda de elevação")),
            "kudos_count": 0,
            "comment_count": 0,
            "photo_count": len(
                str(self._clean_value(row.get("Multimédia")) or "").split("|")
            )
            if self._clean_value(row.get("Multimédia"))
            else 0,
            "trainer": False,
            "commute": self._bool(row.get("Viagem diária"))
            or self._bool(row.get("Viagem diária.1")),
            "manual": False,
            "private": False,
            "flagged": self._bool(row.get("Sinalizado")),
            "source_activity_id": activity_id,
            "source_file": self._clean_value(row.get("Nome do ficheiro")),
            "raw_payload": raw_payload,
        }

    def _save_activity(self, activity: Dict[str, Any]) -> int:
        raw_payload = json.dumps(activity["raw_payload"], default=str, ensure_ascii=False)
        self.db.execute(
            "DELETE FROM raw_strava_activities WHERE source_activity_id = ?",
            (activity["source_activity_id"],),
        )
        self.db.execute(
            """
            INSERT INTO raw_strava_activities (
                source_activity_id, athlete_id, raw_payload, updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                activity["source_activity_id"],
                activity["athlete_id"],
                raw_payload,
            ),
        )

        self.db.execute(
            "DELETE FROM fct_activity_metrics WHERE activity_id = ?",
            (activity["activity_id"],),
        )
        self.db.execute(
            "DELETE FROM stg_activities WHERE activity_id = ?",
            (activity["activity_id"],),
        )
        self.db.execute(
            """
            INSERT INTO stg_activities (
                activity_id, athlete_id, activity_name, activity_type, activity_date,
                distance_meters, moving_time_seconds, elapsed_time_seconds,
                average_speed_mps, max_speed_mps, average_heartrate, max_heartrate,
                total_elevation_gain, total_elevation_loss, kudos_count,
                comment_count, photo_count, trainer, commute, manual, private,
                flagged, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                activity["activity_id"],
                activity["athlete_id"],
                activity["activity_name"],
                activity["activity_type"],
                activity["activity_date"],
                activity["distance_meters"],
                activity["moving_time_seconds"],
                activity["elapsed_time_seconds"],
                activity["average_speed_mps"],
                activity["max_speed_mps"],
                activity["average_heartrate"],
                activity["max_heartrate"],
                activity["total_elevation_gain"],
                activity["total_elevation_loss"],
                activity["kudos_count"],
                activity["comment_count"],
                activity["photo_count"],
                activity["trainer"],
                activity["commute"],
                activity["manual"],
                activity["private"],
                activity["flagged"],
            ),
        )
        return self._save_activity_streams(activity)

    def _save_activity_streams(self, activity: Dict[str, Any]) -> int:
        self.db.execute(
            "DELETE FROM activity_streams WHERE activity_id = ?",
            (activity["activity_id"],),
        )

        points = self._load_activity_stream_points(
            activity["activity_id"],
            activity.get("source_file"),
        )
        if not points:
            return 0

        batch_size = 5000
        inserted = 0
        for start in range(0, len(points), batch_size):
            inserted += self.db.insert_records(
                "activity_streams",
                points[start : start + batch_size],
            )
        return inserted

    def _load_activity_stream_points(
        self,
        activity_id: int,
        source_file: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not source_file or not self._zip:
            return []

        zip_name = self._find_zip_member(source_file)
        if not zip_name:
            return []

        lower_name = zip_name.lower()
        payload = self._zip.read(zip_name)
        if lower_name.endswith(".gz"):
            payload = gzip.decompress(payload)

        if lower_name.endswith((".fit", ".fit.gz")):
            return self._parse_fit_points(activity_id, payload, zip_name)

        try:
            if lower_name.endswith((".gpx", ".gpx.gz")):
                return self._parse_gpx_points(activity_id, payload, zip_name)
            if lower_name.endswith((".tcx", ".tcx.gz")):
                return self._parse_tcx_points(activity_id, payload, zip_name)
        except ET.ParseError as exc:
            logger.warning("Skipping malformed stream file %s: %s", zip_name, exc)
            return []
        return []

    def _find_zip_member(self, source_file: str) -> Optional[str]:
        assert self._zip is not None
        names = set(self._zip.namelist())
        candidates = [
            source_file,
            source_file.lstrip("/"),
            f"activities/{Path(source_file).name}",
        ]
        for candidate in candidates:
            if candidate in names:
                return candidate
        return None

    @classmethod
    def _parse_gpx_points(
        cls,
        activity_id: int,
        payload: bytes,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        root = ET.fromstring(cls._clean_xml_payload(payload))
        records: List[Dict[str, Any]] = []
        cumulative_distance = 0.0
        previous: Optional[Dict[str, Any]] = None

        for point in root.findall(".//{*}trkpt"):
            latitude = cls._number(point.attrib.get("lat"))
            longitude = cls._number(point.attrib.get("lon"))
            if latitude is None or longitude is None:
                continue

            point_time = cls._parse_stream_time(cls._xml_text(point, ".//{*}time"))
            elevation = cls._number(cls._xml_text(point, ".//{*}ele"))
            heartrate = cls._int_number(cls._xml_text(point, ".//{*}hr"))

            speed_mps = None
            if previous:
                delta_m = cls._haversine_meters(
                    previous["latitude"],
                    previous["longitude"],
                    latitude,
                    longitude,
                )
                cumulative_distance += delta_m
                if point_time and previous["point_time"]:
                    delta_seconds = (point_time - previous["point_time"]).total_seconds()
                    if delta_seconds > 0:
                        speed_mps = delta_m / delta_seconds

            record = cls._stream_record(
                activity_id=activity_id,
                point_index=len(records),
                point_time=point_time,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation,
                distance_m=cumulative_distance,
                speed_mps=speed_mps,
                heartrate=heartrate,
                source_file=source_file,
            )
            records.append(record)
            previous = record

        return records

    @classmethod
    def _parse_tcx_points(
        cls,
        activity_id: int,
        payload: bytes,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        root = ET.fromstring(cls._clean_xml_payload(payload))
        records: List[Dict[str, Any]] = []
        previous: Optional[Dict[str, Any]] = None
        cumulative_distance = 0.0

        for point in root.findall(".//{*}Trackpoint"):
            latitude = cls._number(cls._xml_text(point, ".//{*}LatitudeDegrees"))
            longitude = cls._number(cls._xml_text(point, ".//{*}LongitudeDegrees"))
            if latitude is None or longitude is None:
                continue

            point_time = cls._parse_stream_time(cls._xml_text(point, ".//{*}Time"))
            elevation = cls._number(cls._xml_text(point, ".//{*}AltitudeMeters"))
            distance_m = cls._number(cls._xml_text(point, ".//{*}DistanceMeters"))
            heartrate = cls._int_number(cls._xml_text(point, ".//{*}HeartRateBpm/{*}Value"))
            if distance_m is None:
                distance_m = cumulative_distance

            speed_mps = None
            if previous:
                delta_m = max(0.0, distance_m - (previous["distance_m"] or 0.0))
                if delta_m == 0.0:
                    delta_m = cls._haversine_meters(
                        previous["latitude"],
                        previous["longitude"],
                        latitude,
                        longitude,
                    )
                    distance_m = (previous["distance_m"] or 0.0) + delta_m
                if point_time and previous["point_time"]:
                    delta_seconds = (point_time - previous["point_time"]).total_seconds()
                    if delta_seconds > 0:
                        speed_mps = delta_m / delta_seconds

            cumulative_distance = distance_m
            record = cls._stream_record(
                activity_id=activity_id,
                point_index=len(records),
                point_time=point_time,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation,
                distance_m=distance_m,
                speed_mps=speed_mps,
                heartrate=heartrate,
                source_file=source_file,
            )
            records.append(record)
            previous = record

        return records

    @classmethod
    def _parse_fit_points(
        cls,
        activity_id: int,
        payload: bytes,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        if FitFile is None:
            logger.warning("Skipping FIT stream %s because fitparse is not installed", source_file)
            return []

        records: List[Dict[str, Any]] = []
        previous: Optional[Dict[str, Any]] = None
        cumulative_distance = 0.0

        fit_file = FitFile(io.BytesIO(payload))
        for message in fit_file.get_messages("record"):
            values = {field.name: field.value for field in message}
            latitude = cls._fit_semicircles_to_degrees(values.get("position_lat"))
            longitude = cls._fit_semicircles_to_degrees(values.get("position_long"))
            if latitude is None or longitude is None:
                continue

            point_time = values.get("timestamp")
            if not isinstance(point_time, datetime):
                point_time = None
            elevation = cls._number(
                values.get("enhanced_altitude")
                if values.get("enhanced_altitude") is not None
                else values.get("altitude")
            )
            distance_m = cls._number(values.get("distance"))
            if distance_m is None:
                distance_m = cumulative_distance
            heartrate = cls._int_number(values.get("heart_rate"))
            speed_mps = cls._number(
                values.get("enhanced_speed")
                if values.get("enhanced_speed") is not None
                else values.get("speed")
            )

            if previous:
                delta_m = max(0.0, distance_m - (previous["distance_m"] or 0.0))
                if delta_m == 0.0:
                    delta_m = cls._haversine_meters(
                        previous["latitude"],
                        previous["longitude"],
                        latitude,
                        longitude,
                    )
                    distance_m = (previous["distance_m"] or 0.0) + delta_m
                if speed_mps is None and point_time and previous["point_time"]:
                    delta_seconds = (point_time - previous["point_time"]).total_seconds()
                    if delta_seconds > 0:
                        speed_mps = delta_m / delta_seconds

            cumulative_distance = distance_m
            record = cls._stream_record(
                activity_id=activity_id,
                point_index=len(records),
                point_time=point_time,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation,
                distance_m=distance_m,
                speed_mps=speed_mps,
                heartrate=heartrate,
                source_file=source_file,
            )
            records.append(record)
            previous = record

        return records

    @staticmethod
    def _stream_record(
        activity_id: int,
        point_index: int,
        point_time: Optional[datetime],
        latitude: float,
        longitude: float,
        elevation_m: Optional[float],
        distance_m: Optional[float],
        speed_mps: Optional[float],
        heartrate: Optional[int],
        source_file: str,
    ) -> Dict[str, Any]:
        pace_min_km = (1000.0 / speed_mps / 60.0) if speed_mps and speed_mps > 0 else None
        return {
            "activity_id": activity_id,
            "point_index": point_index,
            "point_time": point_time,
            "latitude": latitude,
            "longitude": longitude,
            "elevation_m": elevation_m,
            "distance_m": distance_m,
            "speed_mps": speed_mps,
            "heartrate": heartrate,
            "pace_min_km": pace_min_km,
            "source_file": source_file,
        }

    @staticmethod
    def _xml_text(element: ET.Element, path: str) -> Optional[str]:
        found = element.find(path)
        return found.text if found is not None else None

    @staticmethod
    def _clean_xml_payload(payload: bytes) -> bytes:
        cleaned = payload.strip()
        xml_start = cleaned.find(b"<?xml")
        if xml_start > 0:
            return cleaned[xml_start:]
        tag_start = cleaned.find(b"<")
        if tag_start > 0:
            return cleaned[tag_start:]
        return cleaned

    @staticmethod
    def _parse_stream_time(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
            return parsed.replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _haversine_meters(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        earth_radius_m = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1)
            * math.cos(phi2)
            * math.sin(delta_lambda / 2) ** 2
        )
        return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _fit_semicircles_to_degrees(value: Any) -> Optional[float]:
        number = StravaExportImporter._number(value)
        if number is None:
            return None
        return number * (180.0 / 2**31)

    def _record_import_history(self, rows_seen: int, loaded: int, failed: int) -> None:
        self.db.execute(
            """
            INSERT INTO data_load_history (
                load_type, load_start, load_end, num_records_loaded,
                num_records_failed, status, error_message
            )
            VALUES (
                'strava_export_import',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                loaded,
                failed,
                "completed" if failed == 0 else "completed_with_errors",
                None if failed == 0 else f"{failed} of {rows_seen} rows failed",
            ),
        )

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @classmethod
    def _parse_strava_datetime(cls, value: str) -> datetime:
        cleaned = value.strip().lower()
        date_part, time_part = cleaned.split(",", 1)
        day_text, month_text, year_text = [
            part.strip()
            for part in date_part.replace(" de ", "|").split("|")
        ]
        return datetime.strptime(
            f"{int(day_text)}-{cls.MONTHS_PT[month_text]}-{int(year_text)} {time_part.strip()}",
            "%d-%m-%Y %H:%M:%S",
        )

    @classmethod
    def _map_activity_type(cls, value: Any) -> str:
        cleaned = cls._clean_value(value)
        return cls.ACTIVITY_TYPE_MAP.get(cleaned, cleaned or "Workout")

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        value = StravaExportImporter._clean_value(value)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", ".")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _int_number(cls, value: Any) -> Optional[int]:
        number = cls._number(value)
        return None if number is None else int(round(number))

    @staticmethod
    def _bool(value: Any) -> bool:
        value = StravaExportImporter._clean_value(value)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value == 1
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "sim"}
        return False

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
