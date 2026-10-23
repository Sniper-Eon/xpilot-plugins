"""openpilot Model: runs openpilot's own modeld with the model bundled in the release. While this plugin owns
role:perception.model the host stops SP's models_manager, modeld, modeld_tinygrad and modeld_warmup."""
from openpilot.tesla.plugin import Plugin


def _onroad(started, params, CP) -> bool:
  return started


class OpModels(Plugin):

  @classmethod
  def processes(cls) -> list:
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess("op_modeld", "openpilot.selfdrive.modeld.modeld", _onroad)]
