# xpilot 插件架构与功能分组核查

核查基准：系统 xpilot 分支 7cf967f；插件 main 分支 cbab3df。
这里核查源码和清单，不代表设备已经安装了这些版本或全部完成道路验证。

## 为什么采用插件接口

1. **保持主干稳定。** SP 仍提供基本感知、规划和控制，扩展通过宿主钩子接入；新增功能不必在多处主干文件写条件分支。基础修复仍应修在正确的主干层。
2. **开关控制执行入口。** `plugin.json` 声明 `enable_param`，宿主 `active()` 选择实际参与的插件，manager 包装进程启动条件，UI 根据有效插件名单显示。只改设置页而保留后台执行不算关闭功能。
3. **统一裁决资源。** CAN 发送地址、进程名和可替换角色通过 claims 声明；独占资源按优先级及 id 选出所有者。消息和可叠加目标有自己的合并规则。
4. **限制扩展边界。** CAN 发送由宿主检查资源声明并由 panda 校验；导航目标不能取代原车和 SP 的执行准入。插件开关不能关闭基础安全边界。
5. **隔离已捕获的故障。** 钩子抛异常后，宿主记录并在相应进程中停用该插件；UI 连续绘制失败会停止该叠加层。插件并不是独立安全沙箱，可信 Python 代码、进程挂起和共享依赖仍需专门验证，不能宣称故障绝对不会影响主系统。
6. **独立更新与回退。** 商店打包、校验和安装插件；纯 Python 扩展通常无需改动系统或重刷固件。新增 CAN 能力仍需配套系统和固件验证，不能用安装插件代替。

代码依据：配对系统 `openpilot/tesla/plugins/__init__.py` 的发现、`active/resolve`、`processes`、CAN 检查及故障处理；`manifest.py` 的 claims 裁决；`ui/plugin_ui.py` 的显示启停；`lane_policy.py` 和 `core_host.py` 的限制与兜底。

## 用户明确选择的导航集成

导航保持 **一个** `navassist` 商店插件，主开关 `ExtNavAssistEnabled`。

| 导航内部功能 | 现有开关或入口 |
| --- | --- |
| 导航数据接收、协议与状态 | 插件总开关；来源配置选择特会开或 CP |
| 导航车道定位/变道准备 | `ExtNavAssistLaneChange` |
| 导航物理打灯 | `ExtNavAssistTurnSignal` |
| 转弯/路口速度上限 | `ExtNavAssistTurnSlowdown` |
| 导航变道提示音 | `ExtNavAssistBeep` |
| 导航提示显示 | 由导航插件总开关控制，目前没有独立显示分项开关 |
| 手机视觉附加否决 | `ExtNavAssistPhoneBlindspot`；取图另由 phone_vision 控制 |

上述功能不再拆成多个商店插件。内部参数不是新的独立插件。总开关开启不等于自动获得变道、打灯或降速权限；各分项、输入时效、SP/原车/panda 条件仍需同时满足。

## 其他已存在的独立插件

| 功能组 | 插件 | 总开关 |
| --- | --- | --- |
| 手机单目取图传输 | phone_vision | ExtPhoneVisionEnabled |
| TN 纵向规划 | tn_long | ExtTnLong |
| 外部计算建议通道 | external_compute | XpilotExternalEnabled |
| 驾驶模型选择/替换 | op_models | ExtOpModels |
| 红绿灯控制 | traffic_light | TeslaTrafficSignalControlEnabled |
| 自动限速 | auto_speed | TeslaAutoSpeedLimit |
| 盲区氛围灯 | ambient_light | TeslaBlindspotAmbientEnabled |
| 屏幕盲区提示 | blindspot_edges | XpilotBlindspotEdges |
| 电池状态 | bms | XpilotBms |
| 超速提醒 | overspeed_warning | ExtOverspeedWarning |
| 车辆磁贴 | car_tile | XpilotCarTile |
| 时钟磁贴 | clock_tile | XpilotClockTile |
| IP 磁贴 | ip_tile | XpilotIpTile |
| 前车卡片 | lead_card | XpilotLeadCard |
| 地图磁贴 | map_tile | XpilotMapTile |
| 车速卡片 | speed_card | XpilotSpeedCard |
| 限速卡片 | speed_limit_card | XpilotSpeedLimitCard |

当前 18 个商店插件都有自己声明的、互不共用的 BOOL 总开关。系统内置的 sp_models、sp_engagement、sp_safety_fallback 是默认基础链路，不能与可选扩展的关闭规则混淆。

## 范围和后续验收

- 特会开 R21 的高德接入适配在手机端，C3 侧仍经 navassist 消费；没有新增绕过插件的控制入口。
- phone_vision 提供图像传输不等于手机模型已训练成功或控制已启用；手机推理与 C3 否决许可是不同阶段。
- external_compute 是现有建议通道，不代表 Mac 大模型后端迁移已经完成。
- 双目测距/测速、主动超车、自动返回原车道已从当前候选移除，不把历史实验列为已完成插件。
- DS 的接管检查修复、P 挡设置和中文界面属于基础维护，不改成可关闭的执行功能。
- 当前独立开关具有不同生效时机：UI 的有效名单约每秒刷新；card/规划钩子的实例通常在进程或行程开始时选定，不能承诺所有功能都即时热切换。已拥有灯光的取消、退出和过期处理必须继续验证，不在行驶中卸载或强行重启来测试。
- 未来新增一个可选功能组，先写清插件归属、开关、依赖与关闭行为；只新增确有需要的通用宿主接口。导航组内的增量继续留在 navassist，并按需要增加内部设置。
- 元数据检查只能证明每个插件都有有效独立主开关；不能替代关闭时无后台作用、无越权发包、无旧请求恢复的动态验证。
