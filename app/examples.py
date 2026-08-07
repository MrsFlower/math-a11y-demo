"""内置示例公式：分式/根式、积分、矩阵方程组各一。"""

EXAMPLES = [
    {
        "id": "fraction-root",
        "title": "求根公式（分式 + 根式）",
        "latex": r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        "hint": "一元二次方程的求根公式，包含分数、根号、上标结构。",
    },
    {
        "id": "fourier-integral",
        "title": "傅里叶变换（积分）",
        "latex": r"F(\omega) = \int_{-\infty}^{\infty} f(x) e^{-i\omega x} \, dx",
        "hint": "带上下限的积分，含指数项与希腊字母。",
    },
    {
        "id": "matrix-equation",
        "title": "线性方程组（矩阵）",
        "latex": r"\begin{pmatrix} a & b \\ c & d \end{pmatrix} \begin{pmatrix} x \\ y \end{pmatrix} = \begin{pmatrix} e \\ f \end{pmatrix}",
        "hint": "2×2 系数矩阵乘以未知数列向量的矩阵形式方程。",
    },
]


def get_example(example_id: str):
    for ex in EXAMPLES:
        if ex["id"] == example_id:
            return ex
    return None
