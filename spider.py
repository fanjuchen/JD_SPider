import math
import os
import asyncio
import subprocess
from bs4 import BeautifulSoup
import pandas as pd
import threading
import requests
import queue
import random
import sys
from login import periodic_login_task, login_main
import time
import json
import logging
import re
import concurrent.futures
from tqdm import tqdm  # 引入 tqdm 用于显示进度条
import warnings
warnings.filterwarnings("ignore")
base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
# 确保目录存在
log_dir = os.path.join(base_path, 'cfgs')
os.makedirs(log_dir, exist_ok=True)  # 若目录不存在则创建

# 创建文件处理器，并设置编码为utf-8
file_handler = logging.FileHandler(os.path.join(base_path, 'cfgs', 'spider.log'), mode='a', encoding='utf-8')

# 创建日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 获取根日志记录器，并配置它
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(file_handler)


def run_exe():
    exe_path = os.path.join(base_path, 'login.exe')
    result = subprocess.run([exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    print("标准输出:", result.stdout.decode())
    print("标准错误:", result.stderr.decode())


class Unit:
    def __init__(self, path='./config.json'):
        self.path = path
        # self.config = self.read_config()
        self.dir_path = os.path.dirname(__file__)
        self.read_file_name = None

    def read_config(self):
        with open(self.path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config

    def get_config(self):
        return self.config

    def read_file(self, file_dir):
        files = [item for item in os.listdir(file_dir) if item.split('.')[-1] in ['xls', 'xlsx', 'csv']]
        urls = []
        prices = []
        for file in files:
            if file.split('.')[-1] in ['xls', 'xlsx']:
                df = pd.read_excel(os.path.join(base_path, file_dir, file))
            else:
                df = pd.read_csv(os.path.join(base_path, file_dir, file))

            urls += df.iloc[:, 1].values.tolist()
            prices += df.iloc[:, -1].values.tolist()
        urls = list(zip(urls, prices))
        return urls

    def save_file(self, data, filename=None):
        if not os.path.exists(self.dir_path + '/result'):
            os.makedirs(self.dir_path + '/result')
        df = pd.DataFrame(data, )
        if filename is None:
            df.to_csv(os.path.join(self.dir_path, 'result',  f'{self.read_file_name}.csv'), index=False)
        else:
            df.to_csv(os.path.join(self.dir_path, f'{filename}.csv'))


class Proxy:
    def __init__(self, proxy_url, white_ip, interval=30):
        self.proxy_url = proxy_url
        self.white_ip = white_ip
        self.proxies = []
        self.interval = interval
        self.update_thread = None  # 存储更新线程
        self.init()

    def init(self):
        # 启动线程来定时更新代理, 确保只启动一个线程
        self.add_white_list(self.white_ip)
        self.get_proxies()
        if self.update_thread is None or not self.update_thread.is_alive():
            self.update_thread = threading.Thread(target=self.update_proxy_thread, daemon=True)
            self.update_thread.start()
            logging.info('已开启定时更新ip池...')

    def add_white_list(self, white_ip):
        # self_ip = self.get_white_ip()
        if white_ip:
            try:
                response = requests.get(
                    f'http://op.xiequ.cn/IpWhiteList.aspx?uid=150431&ukey=FA8DB957B7298997E403B5A41FB5C780&act=add&ip={white_ip}',
                    timeout=5)
                if response.status_code == 200:
                    logging.info('ip白名单添加成功!')
                else:
                    logging.error(f"添加IP白名单失败: {response.status_code}")
            except requests.RequestException as e:
                logging.error(f"添加IP白名单请求失败: {e}")

    def get_random_ip(self):
        if self.proxies:
            return {'http': f'http://{random.choice(self.proxies)}',
                    # 'https': f'http://{random.choice(self.proxies)}',
                    }
        return None

    def get_proxies(self):
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            # print(self.proxy_url)
            response = requests.get(self.proxy_url, headers=headers, timeout=5)
            # print(response.text)
            if response.status_code == 200:
                new_proxies = [item.strip() for item in response.text.splitlines()]
                if new_proxies:
                    self.proxies = new_proxies  # 更新代理列表
                    logging.info(f'ips更新成功: {len(new_proxies)} 个代理')
                else:
                    logging.warning("未获取到有效代理IP")
            else:
                logging.warning(f'获取代理IP失败，状态码: {response.status_code}')
        except requests.RequestException as e:
            logging.error(f'获取代理IP请求失败: {e}')

    def update_proxy_thread(self):
        """线程函数，定时更新代理"""
        while True:
            self.get_proxies()
            logging.info(f"当前ips列表为: {', '.join(self.proxies)}")
            time.sleep(self.interval)  # 按照设定的时间间隔更新代理池


class Spider:
    def __init__(self, proxy_url, white_ip, works=16, use_proxy=True, max_retries=3, retry_delay=2, max_requests=100, wait_time=60,
                 executablePath='', span=7, headless=True, file_name='./data'):
        self.works = works
        self.unit = Unit()
        self.abs_path_dir = base_path
        self.use_proxy = use_proxy
        # self.configs = self.unit.get_config()
        self.max_retries = max_retries  # 最大重试次数
        self.retry_delay = retry_delay  # 重试的延迟时间
        self.cookie_pools = [
        ]
        self.ua_agent_pools = [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/37.0.2062.94 Chrome/37.0.2062.94 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
        "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/600.8.9 (KHTML, like Gecko) Version/8.0.8 Safari/600.8.9",
        "Mozilla/5.0 (iPad; CPU OS 8_4_1 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12H321 Safari/600.1.4",
        "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.10240",
        "Mozilla/5.0 (Windows NT 6.3; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; rv:11.0) like Gecko",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko",
        "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_4) AppleWebKit/600.7.12 (KHTML, like Gecko) Version/8.0.7 Safari/600.7.12",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/600.8.9 (KHTML, like Gecko) Version/7.1.8 Safari/537.85.17",
        "Mozilla/5.0 (iPad; CPU OS 8_4 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12H143 Safari/600.1.4",
        "Mozilla/5.0 (iPad; CPU OS 8_3 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12F69 Safari/600.1.4",
        "Mozilla/5.0 (Windows NT 6.1; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; WOW64; Trident/6.0)",
        "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)",
        "Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; Touch; rv:11.0) like Gecko",
        "Mozilla/5.0 (Windows NT 5.1; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/600.6.3 (KHTML, like Gecko) Version/8.0.6 Safari/600.6.3",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/600.5.17 (KHTML, like Gecko) Version/8.0.5 Safari/600.5.17",
        "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:38.0) Gecko/20100101 Firefox/38.0",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 8_4_1 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12H321 Safari/600.1.4",
        "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
        "Mozilla/5.0 (iPad; CPU OS 7_1_2 like Mac OS X) AppleWebKit/537.51.2 (KHTML, like Gecko) Version/7.0 Mobile/11D257 Safari/9537.53",
        "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)",
        "Mozilla/5.0 (Windows NT 6.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36",
        "Mozilla/5.0 (X11; CrOS x86_64 7077.134.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.156 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/600.7.12 (KHTML, like Gecko) Version/7.1.7 Safari/537.85.16",
        "Mozilla/5.0 (Windows NT 6.0; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6; rv:40.0) Gecko/20100101 Firefox/40.0",
        "Mozilla/5.0 (iPad; CPU OS 8_1_3 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12B466 Safari/600.1.4",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/600.3.18 (KHTML, like Gecko)"
        ]
        self.headers = {
            "User-Agent": 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0',
            'Cookie': '',
            # 'referer': 'https://item.jd.com/',
        }
        self.job_list = queue.Queue()
        if self.use_proxy:
            self.proxy = Proxy(proxy_url, white_ip)
        self.result = []
        self.failed_urls = []  # 用于存储超过最大重试次数的URL
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.read_cookies()

        # 全局请求计数器和阈值
        self.request_count = 0
        self.max_requests = max_requests
        self.wait_time = wait_time

        self.file_name = file_name
        self.span = span
        self.executablePath = executablePath
        self.headless = headless
    def read_cookies(self):
        with open(os.path.join(self.abs_path_dir, 'cfgs/cookies.json'), 'r', encoding='utf-8') as f:
            cookies = json.loads(f.read())
            cookies = list(cookies.values())
        self.cookie_pools = cookies

    def set_random_ua(self):
        self.headers['User-Agent'] = random.choice(self.ua_agent_pools)

    def set_random_cookie(self):

        self.headers['Cookie'] = random.choice(self.cookie_pools)

    def fetch_with_retries(self, url):
        """带有重试机制的请求函数，并增加全局请求计数"""
        for attempt in range(self.max_retries):
            self.set_random_cookie()
            self.set_random_ua()
            try:
                if self.use_proxy:
                    proxy = self.proxy.get_random_ip()
                    logging.info(f'Using proxy {proxy}, requesting {url}')
                    res = requests.get(url, headers=self.headers, proxies=proxy, verify=False, timeout=2, allow_redirects=False)
                else:
                    res = requests.get(url, headers=self.headers, allow_redirects=False)
                if res.status_code == 200:
                    return res
                else:
                    logging.error(f"Request failed with status {res.status_code}, retrying...")
                    self.increment_request_count()
            except requests.RequestException as e:
                logging.error(f"Request error: {e}, retrying...")
                self.increment_request_count()


        logging.error(f"Failed to fetch {url} after {self.max_retries} attempts.")
        return None

    def increment_request_count(self):
        """增加请求计数并检查是否超出限制"""
        self.request_count += 1
        if self.request_count >= self.max_requests:
            self.pause_all_requests()

    async def async_login(self):
        """用于调用异步 login_main 的包装函数"""
        await login_main(executablePath=self.executablePath, headless=self.headless, span=self.span)

    def pause_all_requests(self):
        """暂停所有请求，等待指定的恢复时间后继续"""
        print(f"请求次数达到 ({self.request_count}), 暂停请求...")
        # 在这里运行异步的 login_main 函数
        self.pause_event.clear()  # 暂停所有协程
        time.sleep(self.wait_time)  # 等待一段时间
        self.request_count = 0  # 重置请求计数
        self.pause_event.set()  # 恢复所有协程
        print("恢复请求...")

    def get_info_type(self, content, info='包装'):
        for item in content.find_all('li'):
            if info in item.text:
                return item.text.replace('\n', '').replace(' ', '')
        return '暂无'

    def parse_html(self, url, price, sleep_time=1):
        self.pause_event.wait()  # 等待事件被设置为True
        res = self.fetch_with_retries(url)
        if res is None:
            return None
        content = res.text
        soup = BeautifulSoup(content, 'lxml')
        catName = re.findall('catName: \[(.*?)\],', content)
        if catName:
            catName = catName[0].replace('"', '')
        else:
            catName = '暂无'
        try:
            title = soup.find('div', class_='item ellipsis')['title']
        except:
            title = '未知'
        # 作者
        try:
            author = soup.find('div', id="p-author").text.replace('\n', '').replace(' ', '')
        except:
            author = '未知'

        # 图片地址
        try:
            image = soup.find('img', id='spec-img')['data-origin']
        except:
            image = '未知'
        try:
            ul = soup.find('ul', class_='parameter2 p-parameter-list')
            lis = ul.find_all('li')
            # 出版社
            publisher = lis[1].text.replace('\n', '').replace(' ', '')
            # ISBN
            isbn = lis[2].text.replace('\n', '').replace(' ', '')
            # 包装
            package_tp = self.get_info_type(ul, info='包装')
            # 开本
            open_tp = self.get_info_type(ul, info='开本')
            shop_name = lis[0].text.replace('\n', '').replace(' ', '')
        except Exception as err:
            publisher = "暂无"
            isbn = "暂无"
            package_tp = "暂无"
            open_tp = "暂无"
            shop_name = "暂无"
        time.sleep(sleep_time)
        logging.info(" ".join([catName, title, author, str(price), image, publisher, isbn, package_tp, open_tp, shop_name, url]))
        print(" ".join([catName, title, author, str(price), image, publisher, isbn, package_tp, open_tp, shop_name, url]))
        return [catName, title, author, str(price), image, publisher, isbn, package_tp, open_tp, shop_name, url]

    def parse_multiple(self, urls, sleep_time=1):
        urls = list(urls.queue)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.works) as executor:
            # 提交所有 URL 的任务
            future_to_url = {executor.submit(self.parse_html, url[0], url[1], sleep_time): url for url in urls}
            # tqdm显示进度条, 使用len(urls)作为总任务数
            for future in tqdm(concurrent.futures.as_completed(future_to_url), total=len(future_to_url), desc="Crawling Progress"):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        self.result.append(result)
                    else:
                        if url not in list(self.job_list.queue):
                            self.job_list.put(url)
                except Exception as exc:
                    if url not in list(self.job_list.queue):
                        self.job_list.put(url)

    def parse_single(self, urls, sleep_time=1):
        urls = list(urls.queue)
        for url in tqdm(urls, total=len(urls)):
            try:
                data = self.parse_html(url[0], url[1])
                self.result.append(data)
            except Exception as err:
                if url not in self.failed_urls:
                    self.job_list.put(url)
                    self.failed_urls.append(url)
            time.sleep(sleep_time)

    async def run(self, type_='mult', sleep_time=1):
        # 用户登录
        await login_main(executablePath=self.executablePath, headless=self.headless, span=self.span)
        exe_thread = threading.Thread(target=run_exe)
        exe_thread.start()
        urls = self.unit.read_file(self.file_name)
        print('Total URLs:', len(urls))
        # 添加URL到job_list队列
        for url in urls:
            self.job_list.put(url)
        print('Starting crawling...')
        while not self.job_list.empty():
            if type_ == 'MULT':
                self.parse_multiple(self.job_list, sleep_time=sleep_time)
            else:
                self.parse_single(self.job_list, sleep_time=sleep_time)
        print('Crawling completed, results saved to "result" folder.')
        # exe_thread = threading.Thread(target=run_exe)
        exe_thread.join()
        self.unit.save_file(self.result)
if __name__ == '__main__':
    def read_config():
        with open(os.path.join(base_path, 'cfgs', 'config.cfg'), 'r', encoding='utf-8') as f:
            cfgs = f.readlines()
            cfgs = [item.replace('\n', '') for item in cfgs if not item.startswith('#')]
        ccfgs = {}
        for cfg in cfgs:
            cfg = cfg.split('=')
            ccfgs[cfg[0]] = '='.join(cfg[1:])
        return ccfgs
    cfgs = read_config()
    spider = Spider(use_proxy=True if cfgs['USE_PROXY'] == 'True' else False,
                    proxy_url=cfgs['URL'], white_ip=str(cfgs['IP']),
                    works=int(cfgs['WORKS']), max_retries=int(cfgs['MAX_RETRIES']),
                    wait_time=int(cfgs['WAIT_TIME']), file_name=cfgs['FILE_NAME'],
                    executablePath=cfgs['CHROME_PATH'], headless=False if cfgs['HEADLESS'] == "False" else True,
                    span=int(cfgs['SPAN']), max_requests=int(cfgs['MAX_REQUESTS']))

    # asyncio.get_event_loop().run_until_complete(spider.run(type_=cfgs['TYPE'], sleep_time=int(cfgs["SLEEP_TIME"])))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(spider.run(type_=cfgs['TYPE'], sleep_time=int(cfgs["SLEEP_TIME"])))

    loop.close()