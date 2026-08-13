"""临时：启动本地工作台 HTTP 服务，供 jsdom 网页版模式测试使用。"""
import sys
import time

sys.path.insert(0, r"D:\github\Peko")
from peko.ui.workbench_server import ensure_server  # noqa: E402

print(ensure_server(), flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
