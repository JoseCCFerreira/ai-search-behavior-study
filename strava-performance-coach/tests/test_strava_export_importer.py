"""Tests for offline Strava export importer helpers."""

from src.processing.strava_export_importer import StravaExportImporter


def test_parse_portuguese_strava_datetime():
    parsed = StravaExportImporter._parse_strava_datetime(
        "1 de jun. de 2026, 10:07:52"
    )
    assert parsed.year == 2026
    assert parsed.month == 6
    assert parsed.day == 1
    assert parsed.hour == 10


def test_number_parses_decimal_comma():
    assert StravaExportImporter._number("50,30") == 50.30
    assert StravaExportImporter._number("50305.1") == 50305.1


def test_activity_type_mapping():
    assert StravaExportImporter._map_activity_type("Volta de bicicleta") == "Ride"
    assert StravaExportImporter._map_activity_type("Corrida") == "Run"


def test_fit_semicircles_to_degrees():
    assert StravaExportImporter._fit_semicircles_to_degrees(0) == 0
    assert round(StravaExportImporter._fit_semicircles_to_degrees(1073741824), 2) == 90.00


def test_parse_gpx_points_with_elevation_speed_and_heart_rate():
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <gpx xmlns="http://www.topografix.com/GPX/1/1"
         xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
      <trk><trkseg>
        <trkpt lat="38.7000" lon="-9.1000">
          <ele>10.0</ele>
          <time>2026-06-01T10:00:00Z</time>
          <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>140</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions>
        </trkpt>
        <trkpt lat="38.7009" lon="-9.1000">
          <ele>12.0</ele>
          <time>2026-06-01T10:01:00Z</time>
          <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>145</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions>
        </trkpt>
      </trkseg></trk>
    </gpx>"""

    points = StravaExportImporter._parse_gpx_points(123, payload, "activities/test.gpx")

    assert len(points) == 2
    assert points[0]["heartrate"] == 140
    assert points[1]["distance_m"] > 90
    assert points[1]["speed_mps"] > 1
    assert points[1]["pace_min_km"] is not None


def test_parse_tcx_points_with_distance_and_heart_rate():
    payload = b"""garbage   <?xml version="1.0" encoding="UTF-8"?>
    <TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
      <Activities><Activity Sport="Running"><Lap><Track>
        <Trackpoint>
          <Time>2026-06-01T10:00:00Z</Time>
          <Position><LatitudeDegrees>38.7000</LatitudeDegrees><LongitudeDegrees>-9.1000</LongitudeDegrees></Position>
          <AltitudeMeters>10.0</AltitudeMeters>
          <DistanceMeters>0.0</DistanceMeters>
          <HeartRateBpm><Value>130</Value></HeartRateBpm>
        </Trackpoint>
        <Trackpoint>
          <Time>2026-06-01T10:01:00Z</Time>
          <Position><LatitudeDegrees>38.7009</LatitudeDegrees><LongitudeDegrees>-9.1000</LongitudeDegrees></Position>
          <AltitudeMeters>14.0</AltitudeMeters>
          <DistanceMeters>100.0</DistanceMeters>
          <HeartRateBpm><Value>135</Value></HeartRateBpm>
        </Trackpoint>
      </Track></Lap></Activity></Activities>
    </TrainingCenterDatabase>"""

    points = StravaExportImporter._parse_tcx_points(123, payload, "activities/test.tcx")

    assert len(points) == 2
    assert points[1]["distance_m"] == 100.0
    assert points[1]["heartrate"] == 135
    assert round(points[1]["speed_mps"], 2) == 1.67
