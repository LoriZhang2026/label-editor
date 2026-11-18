# 第三方组件与资源

本项目源码使用 GNU Affero General Public License version 3，完整文本见 `LICENSE`。第三方代码与字体仍遵循各自许可证。

| 组件 | 用途 | 上游 |
| --- | --- | --- |
| PyMuPDF / MuPDF | PDF 解析、编辑与渲染 | https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright |
| PySide6 / Qt / shiboken6 | Windows 桌面界面 | https://doc.qt.io/qtforpython-6/licenses.html |
| fontTools | 字体元数据、子集与编码处理 | https://github.com/fonttools/fonttools |
| Arimo | 内置完整同款字体，OFL 1.1 | https://github.com/googlefonts/Arimo |
| ReportLab / Pillow | 开发阶段生成示例和图标 | https://www.reportlab.com/ / https://python-pillow.github.io/ |
| PyInstaller | Windows 打包 | https://pyinstaller.org/ |

依赖版本固定在 `requirements.txt`、`requirements-dev.txt`。发行目录 `licenses/` 收录安装包中的第三方许可文本；Arimo 的 OFL、固定提交和校验值在 `assets/fonts/Arimo/`。

系统字体只从用户自己的 Windows 安装中读取，不附带可独立安装的微软雅黑或 Arial 字体文件。示例 PDF 中嵌入了展示虚构内容所需的字形。

分发包的 `source/` 包含本项目对应源码及构建脚本。修改或再分发时请保留本项目和第三方的许可文件与声明。
