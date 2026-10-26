# 手机地图显示与界面（22 版）

保持特会开为主：高德 SDK 或高德车机继续提供原导航，现有前台服务、观察时间戳、语音、v3 协议与 C3 navassist 的控制条件不变。地图画面可用不代表定位、推荐车道或变道许可有效。

## 修复范围

- 竖屏与横屏都创建同一套高德车机显示层。原竖屏只有 SDK 底图，没有车机路线画面。
- 保留搜索页正在观察的地图中心，仅作初始预览，不写导航位置、GPS 时间或导出状态。
- 只有车机窗口确认在指定显示器且 TextureView 收到实际帧后才隐藏 SDK 底图。授权、服务或窗口失败时保留底图与重连提示。
- Android 新版 RootTaskInfo 使用 childTaskNames，旧 StackInfo 使用 taskNames。既有远程显示桥的反射例外补齐到继承字段 TaskInfo.displayId；实际窗口管理和触控仍需用户已有的 Stellar/Shizuku 授权。
- 窗口/画面回调仍检查本次生命周期，分离后释放显示和触控资源，重新附加时恢复入口。不会因地图连接而启用 C3 插件或车辆动作。
- 搜索卡片、按钮、系统栏避让和横屏地图空间统一；真实车机地图可见时让车机自身显示导航提示，避免双重覆盖。

## 借鉴官方导航的边界

对照的官方源代码（2026-10-26）：

- [navd](https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/navigation/navd.py)：navRoute/navInstruction 分离，路线周期重发、持续偏离确认与重算冷却。
- [mapsd](https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/navigation/mapsd.py)：无有效地图返回无效帧，失败后释放并退避重试。
- [renderer](https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/navigation/renderer.py)：256×256 灰度道路图，适合其既定消费链，不能当作完整中文高德地图直接替换。

本版采用“显示可用性与导航控制有效性分开”的恢复思路，继续由手机承担地图显示，不运行 C3 mapsd、不增加 C3 摄像头传输。官方 navRoute 接口适配与车内路线绘制属于后续独立项目：需要核对实际 X-Pilot 消费者、唯一发布者、源生命周期，以及高德 GCJ-02 和 WGS-84 的坐标转换；发布消息本身不等于已有可用地图页，也不自动获得云端目的地接入。

地图和路线服务本身是否可离线取决于高德的数据与离线包，不将“手机到 C3 使用局域网”等同于整套导航完全离线。

## 验证

`python3 tests/test_map_view_contract.py`：六个显示结构契约，旧代码六项失败；Android 原生窗口字段兼容问题另在初版候选上复现失败后修复。

Java 17 / Android SDK 37：`gradle :app:testDebugUnitTest :app:assembleTenengkai :app:compileReleaseKotlin`。实际手机出图、旋转、后台恢复、触控与错误回退须单独记录；编译不替代实测。UI 变化不构成驾驶或导航动作的路测验收。
