# 两个 X-Pilot 候选版本

| 项目 | CP搭子版 | 特会开版 |
| --- | --- | --- |
| 系统基础 | Sniper-Eon/xpilot，xpilot 分支 | 同一套 X-Pilot |
| 手机导航 | CP搭子 8.0.20 导航 v2 协议候选适配 | 原有特会开 v3 导航 |
| 导航变道 | 共用推荐车道、打灯预备与安全阻止逻辑 | 相同 |
| 盲区 | 回传特斯拉原车 BSM，无需取图 | 原车 BSM，保留可选手机单目辅助 |
| 双目测速、自动超车、自动回原车道 | 已从本项目应用与服务移除 | 已移除 |

普通插件共 18 个，包含旧 TN 纵向、灯光、BMS、交通灯、显示、模型选择等源码。保留源码和成功安装，不代表每项已完成实车验收。

CP 版尚未实现完整 CP 兼容：目前接入导航数据和原车盲区状态。CP 专用模型、侧向雷达、远程参数、下载模型和其他 Carrot 专有接口尚不支持；CP 应用自己的授权和菜单没有修改。原车 BSM 未触发不等于确认安全。

旧 Mac Jetlink 大模型替换后端尚未迁入新平台；现有 external_compute 是建议接口，不能据此称大模型运行已恢复。

两版初始接收导航，关闭主动打灯、导航变道、导航降速和取图，先检查连接及观测。基础安全约束仍保留。准备工具只写入新建隔离目录，不启动插件，不修改当前软件和设备启动路径。

已完成：547 项插件检查；329 项 Android 检查，0 失败、1 跳过；16 项主机检查。两套配置在 C3 隔离目录各成功安装 18 个插件；TN 求解器三组试运行正常。特会开 APK 版本 19，沿用原包名和签名。

待完成：真实 CP App 联调、X-Pilot 完整驻车及相机负载验证、原有设置和 Mac 后端迁移。当前设备 AGNOS 19.7，新平台目标 19.9，编译成功不能替代系统切换验证。两版均为候选，设备未切换。

准备命令只创建新目录：

```sh
python3 tools/prepare_profile.py --host /path/to/xpilot --profile cpdazi --destination /path/to/new-cpdazi
python3 tools/prepare_profile.py --host /path/to/xpilot --profile tesnav --destination /path/to/new-tesnav
```

C3 的 TN 本机库仅供 aarch64 / CPython 3.12；其他平台会记录跳过。每台设备一次只选择一种导航来源，切换后需重启对应进程。
