import json

from navassist.phone import MAX_AGE_NS, PhoneBlindspotAssist, PhoneSideSpeed, read_side_speeds


NOW = 10_000_000_000


def write(path, **sides):
  packet = {
    'version': 1, 'source': 'tesnav-phone', 'valid': True, 'control_eligible': False,
    'stream_id': 'a' * 16, 'updated_mono_ns': NOW,
  }
  packet.update(sides)
  path.write_text(json.dumps(packet))


def speed(**extra):
  fields = dict(distance_m=18.5, relative_speed_mps=-1.5, absolute_speed_mps=12.0,
                track_id=7, track_hits=6, track_confidence=0.77, age_ms=40)
  fields.update(extra)
  return fields


def test_speed_does_not_change_blindspot_blocking(tmp_path):
  path = tmp_path / 'phone.json'
  occupied = {'hits': 5, 'confidence': 0.9, 'occupied': 0.9}
  clear = {'hits': 1, 'confidence': 0.1, 'occupied': 0.1}
  write(path, left=occupied, right=clear)
  without = PhoneBlindspotAssist(mode='assist', path=path).read(NOW)
  write(path, left={**occupied, **speed()}, right={**clear, **speed(distance_m=6.0, absolute_speed_mps=30.0)})
  with_speed = PhoneBlindspotAssist(mode='assist', path=path).read(NOW)
  assert with_speed == without
  assert with_speed[0].blocked and with_speed[0].reason == 'confirmed_phone_target'
  assert not with_speed[1].blocked


def test_read_side_speeds_returns_a_fresh_confirmed_vehicle(tmp_path):
  path = tmp_path / 'phone.json'
  write(path, left={**{'hits': 1, 'confidence': 0.1, 'occupied': 0.1}, **speed()}, right=None)
  got = read_side_speeds(path, NOW)
  assert got['left'] == PhoneSideSpeed(
    True, 18.5, -1.5, 12.0, 7, 6, 0.77, 40, 'ok')
  assert got['right'] == PhoneSideSpeed(reason='missing_side')
  # Occupancy confidence stays irrelevant: a close fast vehicle with a low score is still a measurement.
  assert PhoneBlindspotAssist(mode='assist', path=path).read(NOW)[0].blocked is False


def test_stale_packet_or_sample_is_not_a_speed(tmp_path):
  path = tmp_path / 'phone.json'
  write(path, left=speed())
  assert read_side_speeds(path, NOW + MAX_AGE_NS + 1)['left'].reason == 'stale'
  write(path, left=speed(age_ms=501))
  assert read_side_speeds(path, NOW)['left'].reason == 'stale_measurement'
  write(path, left=speed(age_ms=500))
  assert read_side_speeds(path, NOW)['left'].available
  write(path, left=speed(track_hits=2))
  assert read_side_speeds(path, NOW)['left'].reason == 'unconfirmed'
  write(path, left=speed(distance_m=1, relative_speed_mps=40, absolute_speed_mps=-1))
  assert read_side_speeds(path, NOW)['left'].reason == 'no_measurement'


def test_missing_file_and_bad_json_fail_closed(tmp_path):
  missing = read_side_speeds(tmp_path / 'absent.json', NOW)
  assert missing['left'].reason == 'missing_or_malformed' and not missing['left'].available
  path = tmp_path / 'phone.json'
  path.write_text('{')
  assert read_side_speeds(path, NOW)['right'].reason == 'missing_or_malformed'
  path.write_text(json.dumps({'valid': True}))
  assert read_side_speeds(path, NOW)['left'].reason == 'invalid'
