# 腾讯地图地址跳转（手机 v69，2026-11-23）

用户要求：像高德车机接口一样，在 X-Pilot 输入地址后跳到腾讯地图并携带目的地。

## 行为

- 腾讯来源允许目的地搜索、历史记录选择和地图选点，已有腾讯路线也可重新选目的地；不再误提示“当前导航已启动”。高德 SDK 原有导航中禁止搜索、高德车机外部规划行为均保留。
- 点击“发送到腾讯地图”时使用 qqmap://map/routeplan，type=drive，fromcoord=CurrentLocation，tocoord 按纬度、经度发送；搜索和地图选点沿用 GCJ-02，不把原始 GNSS 坐标错误传入目的地。
- 终点名称、调用来源进行 URL 编码；拒绝非有限或越界坐标。明确指定 com.tencent.map；跳转失败显示未发送，不假装成功或改为只打开首页。
- 明确发送目的地后沿用现有 startRealtime 的来源准备流程。路线页成功打开只表示请求已交给腾讯，不表示已开始导航，更不直接允许 C3 动作。源时间、真实模式、定位、路线匹配与 C3 原有许可检查继续生效。
- 车机代码、打灯、变道、规则、固件和 250/800/640/400 米规划门槛均未修改；本轮没有重启 C3。

## 腾讯接口依据与兼容边界

腾讯官方移动路线 URI 文档： https://lbs.qq.com/webApi/uriV1/uriGuide/uriMobileRoute ，说明 qqmap://map/routeplan、CurrentLocation、目的地坐标顺序和路线规划页面。

较早官方文档 https://lbs.qq.com/uri_v1/guide-route.html 将 referer 定义为调用应用名称；目前新移动文档要求开发者 key。针对已安装旧版腾讯探针，使用实际 X-Pilot 包名作为调用来源，不复制示例密钥、不借用高德 key。系统已确认该版本由 com.tencent.map/.QuickUriActivity 接收协议；实际页面是否接收目的地须由设备检查单独确认，不能只凭 intent 解析成功认定导航完成。后续如换新版腾讯并强制 key，应配置自己的合法凭据并重验。

## 验证

修复前先添加失败契约并运行 NavigationDataSourceTest：7 项中 1 项失败，明确复现腾讯 IDLE 仍禁止搜索。目的地契约在生产实现前添加，覆盖经纬度顺序、中文及 &/+/# 编码、无效坐标、空来源和不同 Locale。

最终 Android scoped 回归 380 项：379 通过、1 跳过。四份原有 CpPaint 缺失类测试仍由本地 init 脚本明确排除，没有声称它们通过。tenengkai 构建、原签名及 zipalign 通过。原包模型、图标、资产和动态库 1706 项逐项与 v68 一致；默认源码未含 side_vehicle320.onnx，构建时从用户本地确切 v68 包提取原资产注入，模型不进入公共仓库。

按项目规范完成 27 项宿主/开关/索引检查，其中 26 通过；shared_safety_check 的旧宿主 API 错误仍存在，本轮未改测试规避。未对无变更的 C3 驾驶逻辑重跑整趟道路数据，也未进行路试。

## 安装与回滚

v69 / 1.56-xpilot-tencent-destination 已通过 USB 原包覆盖安装，包名及证书不变、应用数据不清除、不创建分身。实际安装 APK 哈希已与构建核对：e2a41440ed032596da7c50d23a5acf56e797f8fcb8a0cf2f4f9c91e346609a4d。

C3 仍运行上一轮已部署的 navassist 2.4.9-lane-data、宿主 a0c4486247。本轮开始前重新核对其 90 文件和 74 设置均与上一轮回执一致。手机 v68 的准确原包仍在本地私有制品目录，可用于源码回退后重新构建更高版本号恢复；不要卸载清除用户数据。

本机私有制品目录：/Users/liangjiajian/Documents/Codex/artifacts/tencent-destination-20261123。包含构建、验收 result.json、失败契约回执与保留模型，原始位置、密钥及安装包均不提交 Git。

已参考本轮上游 AGENTS、XPILOT、plugin.py、manifest.py 与贡献规则；手机改动不引入新宿主钩子或 ABI，也不要求迁移固件。遵守用户的 Sniper-Eon fork、中文 UI、集成 navassist 和现车文件优先规则。

设备界面验收当前受手机锁屏阻挡：v69 安装及实际 APK 哈希已核验，已请求用户解锁；未声称已看到腾讯目的地路线页。
