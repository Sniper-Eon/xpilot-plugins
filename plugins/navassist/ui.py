"""AMap-style navigation HUD. Draws only in the strip below the road view."""
import time
import pyray as rl
from openpilot.system.ui.lib.application import FontWeight
from openpilot.tesla.ui.plugin_ui import ScreenOverlay
from openpilot.tesla.ui.tile import text, lines_in
from .display import read_state, signal_status
from .hud import present_hud, hud_rect, signal_authority

CYAN=rl.Color(78,224,255,255)
WHITE=rl.Color(238,244,252,255)
DIM=rl.Color(142,159,180,255)
AMBER=rl.Color(255,191,87,255)


def arrow(x,y,size,direction,color):
  """Vector arrows avoid missing icon glyphs in C3 fonts."""
  left='left' in str(direction)
  right='right' in str(direction)
  mid=x+size*.5
  if left or right:
    side=x+size*(.16 if left else .84)
    pts=[(mid,y+size*.86),(mid,y+size*.35),(side,y+size*.35)]
    head=[(side+size*(.2 if left else -.2),y+size*.16),(side,y+size*.35),
          (side+size*(.2 if left else -.2),y+size*.54)]
  else:
    pts=[(mid,y+size*.86),(mid,y+size*.16)]
    head=[(x+size*.3,y+size*.36),(mid,y+size*.16),(x+size*.7,y+size*.36)]
  for path in (pts,head):
    for a,b in zip(path,path[1:]):rl.draw_line_ex(rl.Vector2(*a),rl.Vector2(*b),max(3,size*.065),color)


class NavAssistOverlay(ScreenOverlay):
  def __init__(self):
    self.nav={};self.intent={};self.oem={};self.topology={}
    self._msgs=None;self.car=None;self.authority=None

  def update(self,sm):
    try:
      if self._msgs is None:
        from openpilot.tesla.plugins import PluginMsgs
        self._msgs=PluginMsgs()
      for key,value in read_state(self._msgs).items():setattr(self,key,value)
    except Exception:self.nav,self.intent,self.oem,self.topology={},{},{},{}
    self.car=None;self.authority=None
    now=time.monotonic_ns()
    try:
      if sm.alive['carState'] and sm.valid['carState'] and 0<=now-sm.logMonoTime['carState']<=500_000_000:
        cs=sm['carState'];self.car=dict(leftBlinker=bool(cs.leftBlinker),rightBlinker=bool(cs.rightBlinker))
      if sm.alive['pandaStates'] and sm.valid['pandaStates'] and 0<=now-sm.logMonoTime['pandaStates']<=500_000_000:
        states=[p for p in sm['pandaStates'] if str(p.safetyModel)=='tesla']
        if states:self.authority=any(signal_authority(p.controlsAllowed, getattr(p,'controlsAllowedLateral',False), p.alternativeExperience) for p in states)
    except (KeyError,AttributeError,TypeError):pass

  def draw(self,zones):
    bottom=zones.get('bottom')
    if bottom is None:return
    x,y,w,h=hud_rect((bottom.x,bottom.y,bottom.width,bottom.height))
    if w<1000 or h<180:return
    state=present_hud(self.nav,self.intent,self.topology,car=self.car,authority=self.authority)
    rl.draw_rectangle_rounded(rl.Rectangle(x,y,w,h),.13,12,rl.Color(9,17,28,250))
    rl.draw_line_ex(rl.Vector2(x+24,y+2),rl.Vector2(x+w-24,y+2),2,rl.Color(73,177,216,125))
    tint=CYAN if state['tone']=='cyan' else AMBER if state['tone']=='amber' else DIM
    text(FontWeight.MEDIUM,'AMap Navigation',x+30,y+18,26,DIM)
    arrow(x+24,y+65,115,state['maneuver'],tint if state['active'] else DIM)
    distance=state['distance']
    value='--' if distance is None else f'{distance/1000:.1f} km' if distance>=1000 else f'{distance:.0f} m'
    text(FontWeight.BOLD,value,x+170,y+65,72,WHITE)
    labels={'turn_left':'TURN L','turn_right':'TURN R','sharp_left':'SHARP L','sharp_right':'SHARP R',
      'u_turn_left':'U-TURN L','u_turn_right':'U-TURN R','merge_left':'MERGE L','merge_right':'MERGE R',
      'exit_left':'EXIT L','exit_right':'EXIT R','ramp_left':'RAMP L','ramp_right':'RAMP R',
      'slight_left':'KEEP L','slight_right':'KEEP R','straight':'STRAIGHT'}
    text(FontWeight.MEDIUM,labels.get(state['maneuver'],''),x+174,y+156,34,DIM)
    lx=x+w*.40
    text(FontWeight.MEDIUM,'Recommended lanes',lx,y+20,26,DIM)
    count=state['count']
    if count:
      step=min(62,(w*.37)/count)
      for index in range(count):
        bx=lx+index*step;selected=index in state['recommended']
        rl.draw_rectangle_rounded(rl.Rectangle(bx,y+65,step-7,83),.15,6,rl.Color(25,63,77,255) if selected else rl.Color(23,33,48,255))
        arrow(bx+3,y+75,step-13,'straight',CYAN if selected else DIM)
        if state['ego']==index:rl.draw_line_ex(rl.Vector2(bx+5,y+154),rl.Vector2(bx+step-12,y+154),4,WHITE)
    else:text(FontWeight.MEDIUM,'Waiting for lane guidance',lx,y+88,29,DIM)
    text(FontWeight.MEDIUM,state['lane_status'],lx,y+176,25,DIM)
    status_box=rl.Rectangle(x+w*.79,y+30,w*.19,h-45)
    lines=[state['status']]
    if self.intent.get('signalRequested'):
      lines.append(signal_status(self.intent))
    lines_in(status_box,lines,30,color=tint)
