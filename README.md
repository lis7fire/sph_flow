# 视频号流速监控系统 Python 版

这是把 `D:\java_project\flow_monitor` 迁移到本地 Python 项目后的首版。

## 已迁移能力

- 本地 Web 服务启动后可在浏览器中使用
- 后台定时采集，默认 1 分钟一次，可配置
- 采集前先读取近期视频列表，勾选本次需要采集的视频
- 本地持久化保存视频快照
- 按周期汇总每条视频的新增数据
- 折线图查看趋势，鼠标悬停可看横纵轴数据
- Excel 导出采集数据

## 当前首版说明

Chrome 扩展原先直接复用浏览器登录态。迁移到纯 Python 本地项目后，首版改成了通过 Cookie 调接口：

1. 打开视频号后台
2. 在浏览器开发者工具里找到任意统计接口请求
3. 复制完整 `Cookie` 请求头
4. 粘贴到页面的“视频号后台 Cookie”设置项里
5. 保存后即可开始采集

后续如果你要继续升级，我建议下一步把“自动读取登录态 / 多账号配置”接上，这样就能把这一步手工贴 Cookie 去掉。

## 运行方式

```powershell
D:\python_project\sph_flow\.venv\Scripts\python.exe D:\python_project\sph_flow\main.py
```

启动后访问：

```text
http://127.0.0.1:8765
```
