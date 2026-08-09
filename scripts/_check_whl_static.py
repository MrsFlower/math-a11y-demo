import zipfile

whl = r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\dist\math_a11y_assistant_0091999c-0.1.0-py3-none-any.whl"
names = [n for n in zipfile.ZipFile(whl).namelist() if "static" in n]
print(names)
