"""Offroad page for the seven TN follow-distance levels."""
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets.list_view import button_item
from openpilot.tesla.ui.pages.base import Header, ListPage, params

FOLLOW_LEVELS = (
  ("0", "1.05 s", "很近，堵车/慢速"),
  ("33", "1.25 s", "接近原始 aggressive"),
  ("66", "1.45 s", "标准"),
  ("100", "1.60 s", "标准偏舒适"),
  ("133", "1.75 s", "舒适"),
  ("166", "1.90 s", "明显拉远"),
  ("200", "2.10 s", "最远，长途/舒适"),
)


class TnFollowPage(ListPage):
  def __init__(self):
    super().__init__()
    self.add(Header("TN Follow Distance"))
    self._rows = []
    for level, (dtr, seconds, use) in enumerate(FOLLOW_LEVELS):
      row = button_item(
        f"{level + 1}/7 · DTR {dtr} · {seconds}",
        lambda level=level: "CURRENT" if params().get("ExtTnScrollLevel", return_default=True) == level else "SET",
        use,
        callback=lambda level=level: self._set(level),
        enabled=ui_state.is_offroad,
      )
      self._rows.append(row)
      self.add(row)

  def _set(self, level: int) -> None:
    if ui_state.is_offroad():
      params().put("ExtTnScrollLevel", level)
      self.refresh()

  def refresh(self) -> None:
    # Button text is a callable and is evaluated by the row host on each frame.
    pass
