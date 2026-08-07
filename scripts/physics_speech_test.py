# -*- coding: utf-8 -*-
"""物理公式朗读回归测试：导数、点记号、向量、散度等。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.parser.python_engine import parse_latex

CASES = [
    ("三维非稳态导热方程", r"\rho c_p \frac{\partial T}{\partial t} = \frac{\partial}{\partial x}\left(k_x \frac{\partial T}{\partial x}\right) + \frac{\partial}{\partial y}\left(k_y \frac{\partial T}{\partial y}\right) + \frac{\partial}{\partial z}\left(k_z \frac{\partial T}{\partial z}\right) + \dot{q}"),
    ("能量方程（含耗散）", r"\rho c_p \left( \frac{\partial T}{\partial t} + \mathbf{u} \cdot \nabla T \right) = \nabla \cdot \left( k \nabla T \right) + \Phi + \dot{q}"),
    ("二阶偏导", r"\frac{\partial^2 T}{\partial x^2}"),
    ("常导数", r"\frac{dy}{dx}"),
    ("向量记号", r"\vec{F} = m \ddot{x} \hat{n}"),
    ("旋度", r"\nabla \times \mathbf{B}"),
    ("普通分数不受影响", r"\frac{a+b}{2}"),
]

for title, latex in CASES:
    r = parse_latex(latex)
    print(f"=== {title} ===")
    print(r["speech_text"])
    print()
