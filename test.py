# 遍历当前文件夹的所有子文件夹
# 查找是否包含 main.py 文件
import json
from pathlib import Path


def find_main_py_files(directory: Path):
    main_py_files = []
    for path in directory.rglob("main.py"):
        if path.is_file():
            main_py_files.append(path.parent.name)
    return main_py_files


def main():
    current_directory = Path(__file__).parent
    main_py_files = find_main_py_files(current_directory)
    print(main_py_files)

    with open(current_directory / "list2.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data_map = {item["name"]: item for item in data["list"]}
    new_list = []
    for plugin in main_py_files:
        if plugin in data_map:
            new_list.append(data_map[plugin])
    with open(current_directory / "list.json", "w", encoding="utf-8") as f:
        json.dump({"list": new_list}, f, ensure_ascii=False, indent=4)


main()
