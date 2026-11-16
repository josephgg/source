#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位 joetv 项目目录与 TVBox 构建目录。

支持两种放置方式，避免把源码搬进仓库后路径写死失效：
  1. 独立工作区：<ws>/joetv + <ws>/repo-source/tvbox
  2. 仓库内：    <repo>/tvbox/joetv + <repo>/tvbox
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

_CANDIDATES = ("tvbox", "repo-source/tvbox", "../tvbox")


def find_tvbox() -> Path:
    for base in (PROJECT, *PROJECT.parents):
        for rel in _CANDIDATES:
            cand = (base / rel).resolve()
            if (cand / "build.py").is_file():
                return cand
    raise SystemExit("找不到 tvbox 构建目录（build.py）")
