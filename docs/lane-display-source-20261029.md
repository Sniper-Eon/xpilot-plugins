# 地图冗余位置与 CP 线型来源修复（2026-10-29）

来源：已部署 2.4.2 提交 18b0147；候选 navassist 2.4.3、cp_nav 0.2.3、TesNav v32。

地图上的“原车车道位置未知 · 无法判定”是旧位置比较显示，不是控制开关。没有有效编号时隐藏此行，不关闭模型数据通道；有效模型车道编号、路线匹配和推荐箭头继续保留。详细观察弹窗仍解释未知/过期。标题不再把未知模型位置标为“原车”，不支持的线型明确标“车端未提供虚实线类型”。

实际手机 CP APK 8.0.20，versionCode 26102406，SHA256 c107503712f8938a4663824cda9366caefea4548c66df9809b4483976f0ceeae，与已反编译参考完全一致。C2183x0.java:110 等读取 carState.leftLaneLine/rightLaneLine。AbstractC0409Pu.java:232 的“规划采用车道线”读取 lateralPlan.useLaneLines，属于规划布尔值，不是虚实线分类。当前宿主没有提供线型字段。新 CP UI 未显示数据的截图不构成模型已输出虚实线的证据。

在 navassist 和 cp_nav 的 compact 适配器发现：缺失线型字段原来填 0，而 CP 将 0 显示成虚线。修复为 -1（未报告）；仅透传真实且合法的原车码，10/21 仍表示白色虚线/黄色实线，不使用模型编号、邻车道几何或导航推荐伪造线型。这能修复缺失值假虚线，但不能解释用户曾见有色线型的全部场景；没有同步包与画面，不断言该显示均为误报。

手机 MNN 当前只接左右车道计数；roadOut 4 通道尚缺可靠训练标签映射，不凭通道数量编造白/黄/虚/实。未添加模型分类器，也未改变跨线许可、控制规则或固件。

验证：实施前地图隐藏用例失败；缺失线型编码回归用例旧版得到(0,0)，期望(-1,-1)，失败。随后 scoped Python 50 项及地图 19 项通过。最终 Python 850 passed（排除已有宿主不兼容 mixed_control）；Android 355 项，354 passed、1 skipped；APK assemble 成功。签名 f5ec7f024863d08af62f97d8e64e096b7a7523fc6a1fe484dba8829ae8f1905d、包名 com.garan.tesnav.tenengkai.lane 保持原身份。28 个 native/model APK 成员逐字节未变。入口、独立主开关、中文元数据、runtime_rules、30 项商店安装发现、归档一致性、ruff 和 fork_pair 检查通过。无行驶控制注入或新增线型准确率路测。

设备激活与手机安装以独立 verified.json/phone-verified.json 为准；本地构建不能替代设备验收。原 APK 与日志留在工作区 private，不提交仓库。
