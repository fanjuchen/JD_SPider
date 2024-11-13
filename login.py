import asyncio
import base64
import json
import os
import re
import sys
import time
from pyppeteer import launch
import cv2
import numpy as np
from PIL import Image

# base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

def identify_block_area(image_data: bytes):
    x, y, w, h = 0, 0, 0, 0
    image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    threshold = cv2.mean(gray)[0]
    threshold = 100 if threshold > 100 else 50
    lower_threshold = np.array([0, 0, 0])  # 下限，调整以满足条件
    upper_threshold = np.array([180, 255, threshold])  # 上限（亮度低于threshold）

    mask = cv2.inRange(hsv, lower_threshold, upper_threshold)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2:]
    filtered_contours = []
    for cnt in contours:
        if 1500 < cv2.contourArea(cnt) < 1800:
            x, y, w, h = cv2.boundingRect(cnt)
            if 0.9 <= (w / h) <= 1.2:
                filtered_contours.append(cnt)
    if filtered_contours:
        x, y, w, h = cv2.boundingRect(filtered_contours[0])
    return x, y, w, h

async def perform_slide(page, span = 5):
    await page.waitForSelector('.JDJRV-bigimg img')

    img_src = await page.evaluate('''() => {
        const img = document.querySelector('.JDJRV-bigimg img');
        return img ? img.src : null;
    }''')

    # 检查并提取 Base64 数据部分
    if img_src and img_src.startswith("data:image"):
        base64_data = img_src.split(",")[1]  # 去掉 "data:image/png;base64," 部分
        image_data = base64.b64decode(base64_data)
        with open("element_screenshot.png", "wb") as img_file:
            img_file.write(image_data)
        x, y, w, h = identify_block_area(image_data)
    else:
        print("src 属性不是 base64 编码的图片")
        return

    slider = await page.J('.JDJRV-slide-inner.JDJRV-slide-btn')
    box = await slider.boundingBox()
    start = box['x'] + box['width'] / 2
    end = box['x'] + x + box['width'] / 2 - span
    await page.mouse.move(start, box['y'] + box['height'] / 2)
    await page.mouse.down()
    await page.mouse.move(end, box['y'] + box['height'] / 2, {'steps': 1})

    shake_magnitude = 2
    for _ in range(3):
        await page.mouse.move(end + shake_magnitude, box['y'] + box['height'] / 2)
        await page.mouse.move(end - shake_magnitude, box['y'] + box['height'] / 2)
    await page.mouse.move(end, box['y'] + box['height'] / 2)
    await page.mouse.up()

async def perform_slide_verify(page, x):

    slider = await page.J('.move-img')
    box = await slider.boundingBox()
    start = box['x'] + box['width'] / 2
    end = box['x'] + x + 27
    await page.mouse.move(start, box['y'] + box['height'] / 2)
    await page.mouse.down()
    await page.mouse.move(end, box['y'] + box['height'] / 2, {'steps': 1})

    shake_magnitude = 2
    for _ in range(3):
        await page.mouse.move(end + shake_magnitude, box['y'] + box['height'] / 2)
        await page.mouse.move(end - shake_magnitude, box['y'] + box['height'] / 2)
    await page.mouse.move(end, box['y'] + box['height'] / 2)
    await page.mouse.up()

def process_and_find_closed_regions(img_path, canny_threshold1=500, canny_threshold2=700, area_threshold=100):
    """
    读取图像，转换为灰度图并应用 Canny 边缘检测，过滤出严格封闭的区域，并返回其边界框信息 (x, y, w, h)。

    Parameters:
        img_path (str): 图像路径
        canny_threshold1 (int): Canny 边缘检测的第一个阈值
        canny_threshold2 (int): Canny 边缘检测的第二个阈值
        area_threshold (int): 用于过滤封闭区域的最小面积阈值

    Returns:
        List of tuples: 封闭区域的边界框信息列表，每个元素为 (x, y, width, height)
        str: 保存的严格封闭区域图像的路径
    """
    # Step 1: 读取图像并转换为灰度图
    img = Image.open(img_path)
    gray_img = img.convert("L")
    gray_img_cv = np.array(gray_img)
    # Step 2: 应用 Canny 边缘检测
    canny_edges = cv2.Canny(gray_img_cv, threshold1=canny_threshold1, threshold2=canny_threshold2)
    # Step 3: 查找轮廓并过滤出严格封闭的区域
    contours, _ = cv2.findContours(canny_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # 创建一个空白图像来绘制严格封闭区域
    strictly_closed_img = np.zeros_like(canny_edges)
    # 用于存储封闭区域的边界框信息
    closed_regions = []
    # 遍历轮廓，筛选出严格封闭的区域并记录边界框
    for contour in contours:
        if cv2.contourArea(contour) > area_threshold:  # 使用面积过滤
            # 绘制封闭区域
            cv2.drawContours(strictly_closed_img, [contour], -1, 255, thickness=cv2.FILLED)
            # 获取边界框信息
            x, y, w, h = cv2.boundingRect(contour)
            closed_regions.append((x, y, w, h))
            # 在封闭区域图像上绘制边界框
            cv2.rectangle(strictly_closed_img, (x, y), (x + w, y + h), 255, 2)
    # 返回封闭区域的边界框信息列表和保存的图像路径
    return closed_regions

async def jd_login(browser, username, password, max_retries=10, span=5):
    page = await browser.newPage()
    await page.setViewport({"width": 1280, "height": 800})
    await page.goto('https://passport.jd.com/new/login.aspx')
    await page.type('#loginname', username, {'delay': 100})
    await page.type('#nloginpwd', password, {'delay': 100})
    await page.click('#loginsubmit')
    await page.waitForSelector('.JDJRV-slide-inner.JDJRV-slide-btn')
    time.sleep(1)

    retries = 0
    while retries < max_retries:
        try:
            print(f"用户：{username}, 尝试第 {retries + 1} 次登录...")
            await perform_slide(page, span=span)
            # 等待页面跳转，设置 longer timeout 避免快速失败
            await page.waitForNavigation(timeout=10000)
            page_content = await page.content()
            if '身份认证' in page_content:
                print('进行手动验证...')
                choice = input('是否验证完成:y/n:')
                if choice == 'y':
                    return page
                else:
                    retries += 1
                    print("登录失败, 重试...")

            return page  # 返回当前页面对象供后续使用

        except Exception as err:

            page_content = await page.content()
            if '身份认证' in page_content:
                print('进行手动验证...')
                choice = input('是否验证完成:y/n:')
                if choice == 'y':
                    return page
                else:
                    retries += 1
                    print("登录失败, 重试...")
            if page.url.startswith('https://www.jd.com/'):
                print('登录成功!')
                return page
            retries += 1
            print("登录失败, 重试...")
    print("滑块验证未通过，已达最大尝试次数。")
    return None

async def get_cookies(page):
    # 获取当前页面的 cookies
    cookies = await page.cookies()
    cookies_list = []
    for cookie in cookies:
        cookies_list.append("{}={}".format(cookie['name'], cookie['value']))
    return ";".join(cookies_list)

def read_users():
    with open('./users.txt', 'r', encoding='utf-8') as f:
        user = f.readlines()
        return [item.replace('\n', '') for item in user]


def read_cfg():
    # abs_path = os.path.dirname(os.path.abspath(__file__))
    with open('./cfgs/config.cfg', 'r', encoding='utf-8') as f:
        delay = int(re.findall('DELAY=(\d+)', f.read())[0])
        print(delay)
        return delay


def update_cookie(username, cookie):
    # base_path = os.path.dirname(os.path.abspath(__file__))
    cookies = dict()
    cookies[username] = cookie
    with open('./cfgs/cookies.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(cookies))


async def periodic_login_task(executablePath=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=False, span=5):
    while True:
        delay = read_cfg()  # 读取配置中的延时
        print(f"等待 {delay} 秒后重试登录...")
        await asyncio.sleep(delay)
        users = read_users()
        for user in users:
            if executablePath:
                browser = await launch(
                    executablePath=executablePath,
                    headless=headless,
                    args=[
                        '--no-sandbox',
                        '--disable-infobars',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                    ]
                )
            else:
                browser = await launch(
                    headless=headless,
                    args=[
                        '--no-sandbox',
                        '--disable-infobars',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                    ]
                )
            username, password = user.split(' ')
            try:
                page = await jd_login(browser, username, password, span=span)
                if page:
                    cookies = await get_cookies(page)
                    print(f'用户 {username} 登录成功')
                    update_cookie(username, cookies)
                    await browser.close()
            except Exception as e:
                pass
            await browser.close()


async def login_main(executablePath=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=False, span=5):

    users = read_users()
    for user in users:
        if executablePath:
            browser = await launch(
                executablePath=executablePath,
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-infobars',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                ]
            )
        else:
            browser = await launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-infobars',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                ]
            )
        username, password = user.split(' ')
        try:
            page = await jd_login(browser, username, password, span=span)
            if page:
                cookies = await get_cookies(page)
                print(f'用户 {username} 登录成功')
                update_cookie(username, cookies)
                await browser.close()
        except Exception as e:
            pass
        await browser.close()
    delay = read_cfg()  # 读取配置中的延时
    print(f"等待 {delay} 秒后重试登录...")
    # await asyncio.sleep(delay)
# # 运行异步主函数
if __name__ == '__main__':
    # asyncio.get_event_loop().run_until_complete(login_main(span=7))
    # read_cfg()
    def read_config_full():
        with open('./cfgs/config.cfg', 'r', encoding='utf-8') as f:
            cfgs = f.readlines()
            cfgs = [item.replace('\n', '') for item in cfgs if not item.startswith('#')]
        ccfgs = {}
        for cfg in cfgs:
            cfg = cfg.split('=')
            ccfgs[cfg[0]] = '='.join(cfg[1:])
        return ccfgs
    cfgs = read_config_full()
    asyncio.get_event_loop().run_until_complete(periodic_login_task(executablePath=cfgs['CHROME_PATH'], headless=False if cfgs['HEADLESS'] == "False" else True,
                    span=int(cfgs['SPAN']),))
