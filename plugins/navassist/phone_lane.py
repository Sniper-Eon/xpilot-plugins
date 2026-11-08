"""Frame-bound CP phone lane candidates. Single-frame estimates; no model-only absolute lane promotion."""
from .phone import bounded_json, OBSERVATION_PATH

MIN_PLANNING_SAMPLES = 3
MIN_PLANNING_SAMPLES_NIGHT = 2   # 夜间模型车道数更抖，放宽到 2 帧

# C 方案：连续帧凑不齐时，用最近 2 秒的样本投票兜底。
WINDOW_NS = 2_000_000_000
WINDOW_MIN_COUNT = 2
WINDOW_MIN_SHARE = 0.6
_window = {"identity": None, "last_stamp": 0, "items": []}


def _window_vote(candidate, nav):
  """Return the voted absolute lane index, or None when the window is inconclusive."""
  identity = (str(nav.get("sessionId", "")), int(nav.get("routeRevision", 0)))
  if _window["identity"] != identity:
    _window["identity"] = identity
    _window["last_stamp"] = 0
    _window["items"] = []
  stamp = candidate.get("captureMonoNs")
  number, count = candidate.get("laneNumber"), candidate.get("laneCount")
  if candidate.get("valid") and type(stamp) is int and type(number) is int and type(count) is int:
    if stamp != _window["last_stamp"]:
      _window["last_stamp"] = stamp
      _window["items"].append((stamp, number, count))
    cutoff = stamp - WINDOW_NS
    _window["items"] = [item for item in _window["items"] if item[0] >= cutoff]
  items = _window["items"]
  if len(items) < WINDOW_MIN_COUNT:
    return None
  tally = {}
  for _stamp, number, count in items:
    tally[(number, count)] = tally.get((number, count), 0) + 1
  (number, count), hits = max(tally.items(), key=lambda kv: (kv[1], kv[0][0]))
  if hits < WINDOW_MIN_COUNT or hits / len(items) < WINDOW_MIN_SHARE:
    return None
  total = nav.get("laneTotalCount")
  if type(total) is int and total > 0 and count != total:
    return None
  return number - 1


def read_observation():
  try:
    return bounded_json(OBSERVATION_PATH)
  except (OSError,ValueError,TypeError,RecursionError):
    return None


class PhoneLaneEvidence:
  def __init__(self):
    self.identity = None
    self.stream = None
    self.last_stamp = -1
    self.last_frame = -1
    self.key = None
    self.samples = 0

  def update(self, record, nav, now_ns, *, enabled=False):
    unknown = dict(valid=False,laneNumber=None,laneCount=None,absoluteConfirmed=False,
                   source='cpPhoneVision',scope='visibleCorridor',samples=0,controlEligible=False)
    identity = (nav.get('sessionId'),nav.get('routeRevision'))
    if not enabled or not nav.get('valid') or not identity[0] or identity != self.identity:
      previous = (self.last_stamp, self.last_frame, self.stream)
      self.__init__()
      self.last_stamp, self.last_frame, self.stream = previous
      self.identity = identity
      if not enabled or not nav.get('valid') or not identity[0]:return unknown
    def reject():
      self.key,self.samples=None,0
      return unknown
    if not isinstance(record,dict):return reject()
    stamp,frame,stream = (record.get(k) for k in ('updated_mono_ns','frame_id','stream_id'))
    lane=record.get('lane_cp')
    if (type(record.get('version')) is not int or record.get('version') != 1 or record.get('source') != 'tesnav-phone'
        or record.get('valid') is not True or record.get('control_eligible') is not False
        or type(stamp) is not int or not 0 <= now_ns-stamp <= 800_000_000
        or type(frame) is not int or frame < 0 or not isinstance(stream,str) or not 8 <= len(stream) <= 128
        or not isinstance(lane,dict)):
      return reject()
    if self.stream is not None and stream != self.stream:
      self.key,self.samples=None,0
      if stamp <= self.last_stamp:return reject()
      self.last_frame=-1
    self.stream=stream
    if any(type(lane.get(k)) is not int for k in ('version','leftClass','rightClass','laneNumber','laneCount')):
      return reject()
    left,right=lane['leftClass'],lane['rightClass']
    if (lane['version'] != 1 or not 1 <= left <= 3 or not 1 <= right <= 3
        or lane['laneNumber'] != left or lane['laneCount'] != left+right-1
        or lane.get('scope') != 'visibleCorridor' or lane.get('control_eligible') is not False
        or lane.get('model') not in ('vlaneDay.mnn','vlaneNight.mnn')):
      return reject()
    if stamp < self.last_stamp or frame < self.last_frame:return reject()
    if (stamp == self.last_stamp) != (frame == self.last_frame):return reject()
    key=(left,right,lane['model'])
    if stamp != self.last_stamp and frame > self.last_frame:
      self.samples=self.samples+1 if key==self.key and stamp-self.last_stamp<=800_000_000 else 1
      self.key,self.last_stamp,self.last_frame=key,stamp,frame
    elif key != self.key:return reject()
    return dict(unknown,valid=True,laneNumber=left,laneCount=left+right-1,
                samples=self.samples,captureMonoNs=stamp,frameId=frame,streamId=stream,model=lane['model'])


def planning_index(candidate, nav, *, enabled=False):
  """Use a route-matched estimate for planning, without declaring it absolute."""
  if not enabled or not nav.get('valid') or not candidate.get('valid'):
    return None
  count, index = candidate.get('laneCount'), candidate.get('laneNumber')
  if type(count) is not int or type(index) is not int or not 1 <= index <= count <= 5:
    return None
  # 单帧估计不足以驱动变道：要求连续多帧一致，避免模型偶发误判把车并到错误车道。
  samples = candidate.get('samples')
  need = MIN_PLANNING_SAMPLES_NIGHT if candidate.get('model') == 'vlaneNight.mnn' else MIN_PLANNING_SAMPLES
  if type(samples) is not int or samples < need:
    # 连续帧不够（夜间车道数抖动）：用最近 2 秒的样本投票兜底。
    return _window_vote(candidate, nav)
  # 高德多数时候不给 laneTotalCount；缺省时信任手机的车道总数，只有两边都给出且矛盾才拒绝。
  total = nav.get('laneTotalCount')
  if type(total) is int and total > 0 and count != total:
    return None
  return index-1
