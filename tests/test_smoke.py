"""M1 验收冒烟测试：包可被导入、版本号存在。

M2 迁入核心代码后，本文件可删除或保留为最小 import 守卫。
"""

from __future__ import annotations

import dom_snapshot


def test_package_importable() -> None:
    """包能被 import（M1 验收判据之一）。"""
    assert dom_snapshot is not None


def test_version_exposed() -> None:
    """__version__ 已定义。"""
    assert isinstance(dom_snapshot.__version__, str)
    assert dom_snapshot.__version__  # 非空
