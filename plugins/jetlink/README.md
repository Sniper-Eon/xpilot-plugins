# Jetlink Accelerator plugin

Status: step 1 scaffold. It owns role:perception.model and runs openpilot's bundled modeld from a plugin
process. It does NOT attach Jetlink or the big model yet. Default is off.

## Failure cases to keep in mind

- Enabled with no usable model files: no modelV2/drivingModelData/cameraOdometry/modelDataV2SP; the host
  will show a communication failure. Disable the plugin to return to the SP model stack.
- Enabled together with another role:perception.model plugin: one loses the role conflict; check the
  Plugins page before driving.
- The plugin process dies or is killed: the host keeps running but has no model messages. Do not enable
  during a drive; process restarts happen at manager level.
- This step does not use the USB link at all. Unplugging the Mac must not change vehicle behavior.
- Enabling replaces SP's model manager and its four processes; model downloads/selection are not available
  while this plugin owns the role.

## Not implemented yet

- Jetlink gadget owner (jetlinkd)
- Jetlink attach / external inference
- nav_map / navigation inputs
- rollback to SP model stack without a manager restart
