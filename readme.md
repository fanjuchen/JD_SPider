# 京东爬虫/京东模拟登录

## 简介
本项目包含一个pyppeteer登录模块和一个requests网络爬虫模块，用于批量抓取数据。爬虫模块支持通过代理和多线程并发请求，从配置文件读取参数，自动管理请求计数和等待时间。

## 依赖
- Python 3.9
- 需要以下Python库：
  ```bash
  pip install requests pandas tqdm beautifulsoup4 pyppeteer opencv-python lxml pyinstaller
  ```
## 文件说明
- login.py：包含登录验证的相关功能。
- spider.py：核心爬虫模块，支持代理、重试机制和多线程抓取。

## 使用方法
1. 在 cfgs 文件夹下配置 config.cfg 文件，内容如下：
``` bash
    # 自身IP
    IP=112.23.44.123
    # 提取IP的URL 支持多个IP提取平台
    URL=http://api.xiequ.cn/VAD/GetIp.aspx?act=get&uid=150431&vkey=1007827AFFC2074AECAB63BCF9C59A8F&num=50&time=30&plat=1&re=0&type=2&so=1&ow=1&spl=1&addr=&db=1
    # chrome浏览器路径：绝对路径
    CHROME_PATH=C:/Program Files/Google/Chrome/Application/chrome.exe
    #休息延迟 单位:s
    WAIT_TIME=12000
    #是否使用代理 True/False
    USE_PROXY=True
    # 爬取方式 单线程/多线程 SINGLE/MULT 多线程数量默认使用的是用户数量*2的线程数目
    TYPE=MULT
    # 多线程数目
    WORKS=3
    # 多长时间更新IP 单位s
    INTERVAL=30
    # 登录浏览器无头模式 True/False 第一次登录需要二次验证需要设置为False
    HEADLESS=False
    # 爬取文件名称
    FILE_NAME=data
    # 每个线程休息时间
    SLEEP_TIME=1
    # 滑块span
    SPAN=7
    # 重试次数
    MAX_RETRIES=3
    # 最大请求次数
    MAX_REQUESTS=100
    # 等待延迟
    DELAY=100
```
2. 在终端中执行以下命令：
``` bash
    python ./spider.py
```
3. 程序运行过程中会在 cfgs/spider.log 中记录日志，方便跟踪抓取过程中的请求状态和代理设置
示例 2024-11-13 12:00:00,000 - Spider - INFO - URL: https://example.com/item1, Status: Success, Data: [title, author, price, ...]
4. 爬虫结果将保存在 result 文件夹下，文件名与数据文件名相同，包含抓取到的所有项目信息



