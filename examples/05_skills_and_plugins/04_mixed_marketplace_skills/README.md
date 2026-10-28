<a id="mixed-marketplace-skills-example"></a>

# 混合市场技能示例

此示例演示了如何创建包含本地和远程技能的市场。

<a id="overview"></a>

## 概述

市场可以参考多个来源的技能：
- **本地技能**：托管在您的项目目录中
- **远程技能**：托管在GitHub（或其他 Git 存储库）上

当您想要执行以下操作时，此模式非常有用：
- 在您的项目中本地维护自定义技能
- 来自 GitHub 存储库的参考社区技能
- 为您的团队创建一套精心策划的技能

<a id="directory-structure"></a>

## 目录结构

```
04_mixed_marketplace_skills/
├── .plugin/
│   └── marketplace.json     # 市场配置
├── skills/
│   └── greeting-helper/
│       └── SKILL.md         # 本地技能
├── main.py                  # 示例脚本
└── README.md                # 这个文件
```

<a id="marketplace-schema"></a>

## 市场模式

`marketplace.json` 文件支持插件和技能：

```json
{
    "name": "my-marketplace",
    "owner": {"name": "Team Name"},
    "skills": [
        {
            "name": "local-skill",
            "source": "./skills/my-skill",
            "description": "A local skill"
        },
        {
            "name": "remote-skill",
            "source": "https://github.com/owner/repo/blob/main/skills/skill-name",
            "description": "A remote skill from GitHub"
        }
    ]
}
```

<a id="source-path-formats"></a>

### 源路径格式

技能可以来源于：

1. **相对本地路径**：`./path`或`../path`（相对于市场目录）
2. **绝对路径**：`/absolute/path`
3. **主目录**：`~/path`
4. **文件 URLs**：`file:///path`
5. **GitHub URLs**: `https://github.com/{owner}/{repo}/blob/{branch}/{path}`

<a id="usage"></a>

## 用途

```bash
# 查看市场信息
python main.py

# 从市场安装所有技能
python main.py --install

# 强制重新安装现有技能
python main.py --install --force

# 列出已安装的技能
python main.py --list
```

<a id="how-it-works"></a>

## 它是如何运作的

1. **市场加载**：`Marketplace.load()`函数读取`.plugin/marketplace.json`文件

2. **来源解析**：每个技能的来源已解析：
   - 本地路径相对于市场目录进行解析
   - GitHub  URLs 触发克隆缓存仓库

3. **技能安装**：`install_skills_from_marketplace()`功能：
   - 解析各个技能来源
   - 将技能复制到`~/.openhands/skills/installed/`
   - 跟踪安装元数据

4. **技能加载**：已安装的技能可以加载`load_installed_skills()`

<a id="api-reference"></a>

## API 参考资料

<a id="install-skills-from-marketplace"></a>

### 从市场安装技能

```python
from openhands.sdk.skills import install_skills_from_marketplace

# 从市场安装所有技能
installed = install_skills_from_marketplace("./my-marketplace", force=False)

for info in installed:
    print(f"Installed: {info.name}")
```

<a id="load-installed-skills"></a>

### 加载已安装的技能

```python
from openhands.sdk.skills import load_installed_skills

# 加载所有已安装的技能
skills = load_installed_skills()

for skill in skills:
    print(f"Skill: {skill.name}")
    print(f"Description: {skill.description}")
```

<a id="list-installed-skills"></a>

### 列出已安装的技能

```python
from openhands.sdk.skills import list_installed_skills

# 获取已安装技能的元数据
installed = list_installed_skills()

for info in installed:
    print(f"{info.name}: {info.source}")
```
