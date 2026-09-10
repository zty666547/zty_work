# DebugPath 答辩部署说明

## Windows 单文件版本

仓库标签 `windows-v*` 会触发 Windows 自动打包。流水线生成 `DebugPath.exe` 后会实际启动程序并访问健康检查接口；只有检查成功才会发布到 GitHub Releases。便携版内置离线知识库，不读取 API 密钥，也不依赖 Neo4j。

使用方法：

1. 从 GitHub Releases 下载 `DebugPath.exe`；
2. 双击运行，等待浏览器自动打开；
3. 演示结束后点击侧栏的“关闭 DebugPath”，或在任务管理器中结束程序。

学校电脑可能禁止未签名程序，因此在线演示和录屏仍应作为答辩兜底。

## 推荐：Streamlit Community Cloud

部署后，学校电脑只需要浏览器和网络，不需要安装 Python。

当前在线入口：[DebugPath 在线演示](https://ztywork-w4dzhwedqtyxgzbuqzkyus.streamlit.app/)

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io/)；
2. 使用能够访问本项目仓库的 GitHub 账号登录；
3. 选择仓库 `zty666547/zty_work`；
4. 分支选择 `main`；
5. 入口文件填写 `app.py`；
6. 在 Advanced settings 中选择 Python 3.12；
7. 离线稳定模式不需要填写 Secrets，直接部署；
8. 部署完成后，在学校网络中提前测试公网地址。

如果以后需要 DeepSeek，只能在 Community Cloud 的 Secrets 设置中配置，不要把真实密钥提交到 GitHub。

## Windows 本地备用

学校电脑需要预先安装 Python，并能在首次运行时下载依赖。

1. 下载或克隆完整仓库；
2. 双击 `scripts/run_debugpath.bat`；
3. 等待浏览器自动打开；
4. 如果没有自动打开，访问 `http://127.0.0.1:8501`。

首次运行会创建 `.venv` 并安装依赖。答辩前必须在同一台电脑上完整运行一次，不能等到现场首次安装。

## macOS 本地备用

首次使用时，在项目根目录执行：

```bash
chmod +x scripts/run_debugpath.command
```

以后双击 `scripts/run_debugpath.command` 即可启动。也可以在终端运行：

```bash
./scripts/run_debugpath.command
```

## 答辩前检查

- 公网地址能够在学校网络打开；
- “PyTorch检测不到GPU”案例可以完成三轮询问；
- 左侧问答和右侧候选子图同步变化；
- 浏览器使用全屏或至少1280像素宽度；
- 本地备用版本已经安装全部依赖；
- PPT保留完整轨迹，另准备一段录屏作为最终兜底。

本地地址 `127.0.0.1` 只对正在运行 DebugPath 的那台电脑有效，不能作为公网链接分享。
