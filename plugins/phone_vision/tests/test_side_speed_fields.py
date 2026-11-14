import json
import math

import pytest

from phone_vision.frames import FrameStore


def fixture(tmp_path):
  now = [10_000_000_000]
  store = FrameStore(tmp_path / 'observation.json', lambda: now[0])
  store.publish({'capture_mono_ns': now[0], 'frame_id': 1, 'jpeg_b64': 'fixture'})
  return store, now


def accept(store, left, right=None):
  packet = store.issue()
  return store.accept(dict(request_id=packet['request_id'], frame_id=packet['frame_id'], left=left, right=right))


def test_speed_fields_are_stored_beside_unchanged_occupancy(tmp_path):
  store, _ = fixture(tmp_path)
  stored = accept(store, {
    'hits': 4, 'confidence': 0.82, 'occupied': 0.82,
    'distance_m': 18.5, 'relative_speed_mps': -1.5, 'absolute_speed_mps': 12.0,
    'track_id': 7, 'track_hits': 6, 'track_confidence': 0.77, 'age_ms': 40,
    'unexpected': 1,
  })['left']
  assert stored['hits'] == 4 and stored['confidence'] == 0.82
  assert 'occupied' not in stored and 'unexpected' not in stored
  assert stored['distance_m'] == 18.5
  assert stored['relative_speed_mps'] == -1.5
  assert stored['absolute_speed_mps'] == 12.0
  assert stored['track_id'] == 7
  assert stored['track_hits'] == 6
  assert stored['track_confidence'] == 0.77
  assert stored['age_ms'] == 40
  persisted = json.loads(store.output.read_text())['left']
  assert persisted['hits'] == 4 and persisted['track_hits'] == 6 and 'occupied' not in persisted


def test_malformed_speed_metadata_is_dropped_without_rejecting_occupancy(tmp_path):
  store, _ = fixture(tmp_path)
  stored = accept(store, {
    'hits': 2, 'confidence': 0.4, 'occupied': 0.4, 'distance_m': 10,
    'track_hits': 'no', 'track_confidence': 2, 'age_ms': -1, 'track_id': True,
  })['left']
  assert stored['hits'] == 2 and stored['confidence'] == 0.4 and stored['distance_m'] == 10
  assert 'track_hits' not in stored and 'track_confidence' not in stored and 'age_ms' not in stored


def test_bad_distance_still_rejects_the_whole_frame(tmp_path):
  store, _ = fixture(tmp_path)
  packet = store.issue()
  body = dict(request_id=packet['request_id'], frame_id=packet['frame_id'],
              left={'hits': 3, 'confidence': 0.9, 'distance_m': 1}, right=None)
  with pytest.raises(ValueError, match='distance_out_of_bounds'):
    store.accept(body)
  packet = store.issue()
  body = dict(request_id=packet['request_id'], frame_id=packet['frame_id'],
              left={'hits': 3, 'confidence': 0.9, 'relative_speed_mps': math.nan}, right=None)
  with pytest.raises(ValueError, match='non_finite_metric'):
    store.accept(body)


def test_occupancy_without_speed_keeps_the_previous_null_metrics(tmp_path):
  store, _ = fixture(tmp_path)
  stored = accept(store, {'hits': 1, 'confidence': 0.1, 'occupied': 0.1})['left']
  assert stored['hits'] == 1 and stored['confidence'] == 0.1
  assert stored['distance_m'] is None and stored['relative_speed_mps'] is None
  assert stored['absolute_speed_mps'] is None and stored['track_id'] is None
  assert 'track_hits' not in stored and 'age_ms' not in stored
