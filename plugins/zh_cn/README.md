# 简体中文增强

独立开关：`ExtChineseUiEnabled`。插件列表名称为 `Simplified Chinese UI`。
默认关闭；开启后汉化选项名称、可选值、说明、插件信息与设置页面。关闭后恢复设备原有语言，
不写入 LanguageSetting，不改变参数键、选择值、导航开关或车辆控制。

需要配对 xpilot 宿主的 `ui_translation` 接口；仅把插件安装到旧宿主不能生效。
宿主接口提交：`405d877`（或包含该提交的后续版本）。
词库保留原始英文为键，1.0.1 包含 460 条内容。未知文字保留原文，远端更新日志、
第三方模型名、原始错误详情等不承诺自动翻译。

已有的中文字体是精简子集，1.0.0 所需字符中有 240 个汉字不在其中。本包附带未经修改的
Noto Sans CJK SC Regular 2.004，使用 SIL Open Font License 1.1（见 FONT-LICENSE.txt）。
宿主只为当前基础翻译和本插件词库中的字符生成字库，不一次加载所有 CJK 字符。
字体 SHA-256：2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b。
官方字体来源：https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf

验证：词库覆盖当前所有商店插件名称、说明和设置标签/枚举标签；1.0.0 核对 554 个所需字符，
完整字体无缺字；真实宿主安装器、插件发现及启用/关闭/恢复验证通过（本地隔离目录和模拟 Params）。
新增 UI 翻译桥 8 项契约通过。基础磁贴、页面和静态导入检查通过。
Mac 全量插件宿主检查受已有 msgq 二进制与解释器 ABI 不匹配阻挡，未记为通过。
1.0.0 已在 C3 激活并完成原生界面截图检查；1.0.1 当前仅完成源码与本地检查，尚未部署。

## 1.0.1 对照补漏

参考 juyun86/xpilot-plugins 的 chinese_ui 1.1.0 词库（提交
`2c35df28fd623ef88a5f4e66e668bdbd0c5d8e20`），对照当前源码补齐 50 个实际页面词条，
包括磁贴编辑、商店、设备操作、更新状态和新手引导。保留当前导航专用词条和既有用词。
参考来源：https://github.com/juyun86/xpilot-plugins/tree/2c35df28fd623ef88a5f4e66e668bdbd0c5d8e20/plugins/chinese_ui
其 README 声明基础词库来自旧版 sunnypilot；此处只采纳经当前 UI 源码匹配的词条，
不整体引入旧版页面、无关功能或该分支的宿主接口。格式占位符必须与原文一致。
其 ui_language/role:ui.language 接口与本插件不同，不能直接替换；该分支启动时加载，
本插件继续支持现有宿主的开关刷新。
