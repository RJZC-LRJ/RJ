# -*- coding: utf-8 -*-
# by @嗷呜

from urllib.parse import urlparse, quote, unquote
from pprint import pprint
from base64 import b64decode, b64encode
from pyquery import PyQuery as pq
from Crypto.Util.Padding import unpad
from Crypto.Cipher import AES
from pyquery.pyquery import PyQuery
import colorsys
import json
import random
import re
import sys

import threading
import requests
import os
import hashlib
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from base.spider import Spider


sys.path.append('..')



class WebDecryptor:
    def __init__(self):
        self.cookies = {}
    
    def is_unicode_encoded(self, text):
        """判断字符串是否是Unicode编码"""
        return bool(re.search(r'\\u[0-9a-fA-F]{4}', text))
    
    def extract_play_source_src(self, html_content):
        """直接提取playSource.src的值"""
        # 直接查找playSource.src的赋值
        pattern = r'playSource\s*=\s*\{[^}]*src\s*:\s*"([^"]*)"[^}]*\}'
        match = re.search(pattern, html_content, re.DOTALL)
        
        if match:
            return match.group(1)
        
        return None
    
    def extract_encrypted_string(self, html_content):
        """提取加密字符串"""
        # 查找KKYS.safePlay().url()中的加密字符串
        pattern = r'KKYS\.safePlay\(\)\.url\("([^"]+)"\)'
        match = re.search(pattern, html_content)
        
        if match:
            return match.group(1)
        
        return None
    
    def get_web_content(self, url):
        """获取网页内容"""
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,ko;q=0.5",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "priority": "u=0, i",
                "sec-ch-ua": "\\Chromium;v=\\142, \\Microsoft",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\\Windows",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
            }
            
            response = requests.get(url, headers=headers, cookies=self.cookies, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"获取网页内容失败: {e}")
            return None
    
    def extract_encrypted_value(self, html_content):
        """从HTML中提取加密的值"""
        pattern = r"window\.whatTMDwhatTMDPPPP\s*=\s*'([^']+)'"
        match = re.search(pattern, html_content)
        
        if match:
            return match.group(1)
        return None
    
    def decrypt_value_python(self, encrypted_value):
        """使用Python实现AES解密"""
        try:
            print(f"正在使用Python解密...")
            
            # AES密钥
            key = b"Isu7fOAvI6!&IKpAbVdhf&^F"
            
            # Base64解码
            encrypted_bytes = b64decode(encrypted_value)
            
            # 创建AES解密器 (ECB模式)
            cipher = AES.new(key, AES.MODE_ECB)
            
            # 解密
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            
            # 去除PKCS7填充
            decrypted_bytes = unpad(decrypted_bytes, AES.block_size)
            
            # 转换为字符串
            result = decrypted_bytes.decode('utf-8')
            
            print(f"解密完成: {result}")
            return result
            
        except Exception as e:
            print(f"Python解密失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def decrypt_value(self, encrypted_value):
        """解密加密的值 - 尝试两种方法"""
        # 首先尝试Python解密
        result = self.decrypt_value_python(encrypted_value)
        if result and not result.startswith("解密失败"):
            return result
        
        # 如果Python解密失败，尝试execjs（如果可用）
        try:
            import execjs
            # 如果有execjs，可以在这里添加execjs的解密代码
            print("execjs可用，但Python解密已失败")
            return None
        except ImportError:
            print("execjs不可用")
            return None
    
    def process_url(self, url):
        """处理整个URL解密流程"""
        print(f"开始处理URL: {url}")
        
        # 1. 获取网页内容
        html_content = self.get_web_content(url)
        if not html_content:
            return None
        
        # 2. 获取m3u8地址
        m3u8_url = self.extract_play_source_src(html_content)

        if not m3u8_url:
            print("加密了 开始解密")
            # 找不到就是加密了
            # 3. 原来的功能：提取whatTMDwhatTMDPPPP值并解密
            encrypted_value = self.extract_encrypted_value(html_content)
            if encrypted_value:
                m3u8_url = self.decrypt_value(encrypted_value)
                if m3u8_url and m3u8_url.startswith("解密失败"):
                    print(f"❌ 解密失败: {m3u8_url}")
                    return None
            else:
                print("❌ 未找到加密值")
                return None

        else:
            print("未加密")
            print(f"m3u8地址: {m3u8_url}")
            
        return {
            'url': url,
            'm3u8_url': m3u8_url,
        }



class Spider(Spider):

    def init(self, extend="{}"):
        self.domin = 'https://103.194.185.51:51123'
        self.proxies = {}
        self.headers = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 Edg/142.0.0.0",
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'pragma': "no-cache",
            'cache-control': "no-cache",
            'sec-ch-ua': "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': "\"Android\"",
            'upgrade-insecure-requests': "1",
            'sec-fetch-site': "none",
            'sec-fetch-mode': "navigate",
            'sec-fetch-user': "?1",
            'sec-fetch-dest': "document",
            'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,ko;q=0.5",
            'priority': "u=0, i",
        }

        self.host = "https://103.194.185.51:51123"
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})

        # 初始化t参数缓存
        self._t_param_cache = None
        self._t_param_time = 0
        self._t_param_timeout = 300  # 5分钟缓存

        # 预加载t参数
        self._preload_t_parameter()
        
    def _preload_t_parameter(self):
        """在初始化时预加载t参数"""
        def preload_task():
            try:
                print("🔄 预加载t参数...")
                t_value = self.get_t_parameter()
                if t_value:
                    self._t_param_cache = t_value
                    self._t_param_time = time.time()
                    print("✅ t参数预加载成功")
                else:
                    print("❌ t参数预加载失败")
            except Exception as e:
                print(f"预加载t参数异常: {e}")
        
        # 在新线程中预加载，不阻塞主初始化
        thread = threading.Thread(target=preload_task)
        thread.daemon = True
        thread.start()
    def get_t_parameter_cached(self):
        """带缓存的t参数获取"""
        current_time = time.time()
        
        # 检查缓存是否有效（5分钟）
        if (self._t_param_cache and 
            current_time - self._t_param_time < self._t_param_timeout):
            print("♻️ 使用缓存的t参数")
            return self._t_param_cache
        
        # 重新获取t参数
        print("🔄 重新获取t参数")
        t_value = self.get_t_parameter()
        if t_value:
            self._t_param_cache = t_value
            self._t_param_time = current_time
        return t_value    
    # 其他方法保持不变...
    def getName(self):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def _parse_video_item(self, item):
        """解析单个视频项"""
        try:
            #             # 获取视频链接 选择所有 <a> 标签，并且这些 <a> 标签具有 v-item 这个类  .attr('href') 就是获取这个 <a> 元素的 href 属性
            #             a.v-item 的含义
            # a.v-item 这个CSS选择器的意思是：

            # a: 选择所有 <a> 标签（超链接元素）

            # .v-item: 选择所有具有 class="v-item" 的元素

                    # 组合起来: 选择所有既是 <a> 标签又具有 v-item 类的元素
            vid = item.find('a.v-item').attr('href')
            if not vid:
                print("❌ 未找到视频链接")
                return None



            # 获取标题
            title = item.find('.v-item-title').eq(1).text().strip()

            cover = item.find(
                '.v-item-cover img').eq(1).attr('data-original')  # 第二个img是实际图片
            if not cover:
                cover = item.find('.v-item-cover img').attr('src')

            # 获取评分
            score_elem = item.find('.v-item-top-left span:contains("豆瓣")')
            score = score_elem.text().replace('豆瓣:', '').replace(
                '分', '').strip() if score_elem else ''

            # 获取状态/更新信息
            status = item.find('.v-item-bottom span').text().strip()

            return {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': "https://vres.zclmjc.com"+cover,
                'vod_remarks': status
            }

        except Exception as e:
            print(f"Error parsing video item: {e}")
            return None

    def homeContent(self, filter):
        try:

            response = requests.get(
                self.host, headers=self.headers, proxies=self.proxies)
            doc = pq(response.content)
            result = {}
            classes = []
            
            
            # 尝试不同的选择器来找到分类菜单
            # 方法1: 查找所有包含分类的菜单
            # 查找所有菜单项

            menu_items = doc('.t-p-side-inner .menu-item')
            for item in menu_items.items():

                # 获取菜单文本

                label = item.find('.menu-item-label').text().strip()
                href = item.find('a').attr('href')

                # 过滤出需要的分类
                if label in ['电影', '连续剧', '动漫', '综艺纪录', '短剧', '今日更新']:
                    # 从链接中提取类型ID
                    classes.append({
                        'type_name': label,
                        'type_id': href
                    })
            result['class'] = classes

 # [{'type_name': '电影', 'type_id': '/channel/1.html'}, {'type_name': '连续剧', 'type_id': '/channel/2.html'}, {'type_name': '动漫', 'type_id': '/channel/3.html'}, {'type_name': '综艺纪录', 'type_id': '/channel/4.html'}, {'type_name': '短剧', 'type_id': '/channel/6.html'}, {'type_name': '今日更新', 'type_id': '/label/new.html'}]

    # 提取视频列表 - 从各个模块中提取
            video_list = []

            # 方法1: 从"近期热门电影"模块提取
            movie_items = doc('.section-box:contains("近期热门电影") .module-item')
            for item in movie_items.items():
                video_info = self._parse_video_item(item)
                if video_info:
                    video_list.append(video_info)

            # 方法2: 从"近期热门剧集"模块提取
            tv_items = doc('.section-box:contains("近期热门剧集") .module-item')
            for item in tv_items.items():
                video_info = self._parse_video_item(item)
                if video_info:
                    video_list.append(video_info)

            # 方法3: 从"最近更新"模块提取
            update_items = doc('.section-box:contains("最近更新") .module-item')
            for item in update_items.items():
                video_info = self._parse_video_item(item)
                if video_info:
                    video_list.append(video_info)

            result['list'] = video_list
            return result

        except Exception as e:
            print(f"首页内容获取失败: {e}")
            import traceback
            traceback.print_exc()
            return {'class': [], 'list': []}

    # 其他方法保持不变...
    def homeVideoContent(self):
        pass

    def _parse_category_video_item(self, item):
        """解析分类页面的单个视频项 - 返回单个视频字典"""
        try:
            # 获取视频链接
            link = item.find('a.v-item').attr('href')
            if not link:
                return None

            # 获取视频ID
            vid = link.split(
                '/detail/')[1].split('.')[0] if '/detail/' in link else ''

            # 获取标题 - 选择第二个.v-item-title（第一个和第三个是隐藏的）
            title = item.find('.v-item-title').eq(1).text().strip()
            if not title:
                return None

            cover = item.find(
                '.v-item-cover img').eq(1).attr('data-original')  # 第二个img是实际图片
            if not cover:
                cover = item.find('.v-item-cover img').attr('src')

            # 获取评分
            score_elem = item.find('.v-item-top-left span:contains("豆瓣")')
            score = score_elem.text().replace('豆瓣:', '').replace(
                '分', '').strip() if score_elem else ''

            # 获取更新状态
            status = item.find('.v-item-bottom span').text().strip()

            # 返回单个视频字典
            return {
                'vod_id': link,  # 使用完整链接作为ID
                'vod_name': title,
                'vod_pic': "https://vres.zclmjc.com/"+cover,
                'vod_remarks': status,
                'vod_tag': ''  # 普通视频没有特殊标签
            }

        except Exception as e:
            print(f"❌ 解析视频项失败: {e}")
            return None

    def getlist_category(self, data, tid=''):
        """专门处理分类页面的视频列表"""
        videos = []

        # 如果data选择器没有找到内容，尝试使用新的选择器
        if data.length != 0:
            # 使用新的选择器查找视频项
            video_items = data('.section-box .module-item')
            for item in video_items.items():
                video_info = self._parse_category_video_item(item)
                if video_info:
                    videos.append(video_info)

        return videos

    def categoryContent(self, tid, pg, filter, extend):
        print(f"🎯 分类页面请求，tid: {tid}, 页码: {pg}")

        # 🆕 只处理第一页，其他页码返回空
        if int(pg) != 1:
            print(f"⚠️ 网站不支持分页，跳过第{pg}页请求")
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}

        try:
            if '@folder' in tid:
                id = tid.replace('@folder', '')
                videos = self.getfod(id)
            else:
                url = f"{self.host}{tid}"
                print(f"🌐 请求URL: {url}")

                response = requests.get(
                    url, headers=self.headers, proxies=self.proxies)
                data = pq(response.content)
                videos = self.getlist_category(data, tid)

            print(f"✅ 成功获取 {len(videos)} 个视频")

            return {
                'list': videos,
                'page': pg,
                'pagecount': 1,  # 🆕 明确告诉APP只有1页
                'limit': len(videos),
                'total': len(videos)  # 🆕 使用实际数量
            }

        except Exception as e:
            print(f"❌ 分类页面请求失败: {e}")
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}


#         vod_name (标题)

# vod_pic (封面)

# vod_content (描述)

# vod_director (导演)

# vod_actor (演员)

# vod_year (年份)

# vod_area (地区)

# type_name (类型)

# vod_remarks (备注，可能是更新状态)

# vod_play_from (播放源，多个用$$$分隔)

# vod_play_url (播放列表，多个源用$$$分隔，同一源的多集用#分隔，每集格式：集名$URL)


    def detailContent(self, ids):
        """
        获取视频详情内容
        优化点：更好的错误处理、性能优化、代码结构清晰化
        """
        try:
            # 1. URL处理优化
            url = ids[0] if ids[0].startswith(
                "http") else f"{self.host}{ids[0]}"

            # 2. 请求优化 - 添加超时和重试
            response = requests.get(url, headers=self.headers,
                                    proxies=self.proxies, timeout=10)
            response.raise_for_status()  # 自动处理HTTP错误

            data = pq(response.content)
            vod = self._parse_vod_info(data, url)

            return {'list': [vod]}

        except requests.RequestException as e:
            print(f"网络请求失败: {e}")
            return {'list': [self._create_fallback_vod(ids[0])]}
        except Exception as e:
            print(f"解析详情页失败: {e}")
            return {'list': [self._create_fallback_vod(ids[0])]}

    def _parse_vod_info(self, data, url):
        """解析视频基本信息 - 模块化处理"""
        vod = {}

        # 基础信息提取
        vod.update(self._parse_basic_info(data))
        vod.update(self._parse_metadata(data))
        vod.update(self._parse_play_info(data, url))

        return vod

    def _parse_basic_info(self, data):
        """解析基础信息"""
        info = {}

        try:
            # 标题 - 使用更精确的选择器
            title_elem = data('.detail-title strong:nth-child(2)')
            info['vod_name'] = title_elem.text(
            ).strip() if title_elem else "未知标题"

            # 封面图 - 优化URL处理
            cover_img = data('.detail-pic img')
            cover = cover_img.attr('data-original') or cover_img.attr('src')
            if cover:
                if not cover.startswith('http'):
                    cover = f"https://vres.zclmjc.com/{cover}"
            info['vod_pic'] = cover or ""

            # 描述
            desc_elem = data('.detail-desc p')
            info['vod_content'] = desc_elem.text(
            ).strip() if desc_elem else "暂无简介"

        except Exception as e:
            print(f"解析基础信息失败: {e}")
            info.update({
                'vod_name': '未知标题',
                'vod_pic': '',
                'vod_content': '暂无简介'
            })

        return info

    def _parse_metadata(self, data):
        """解析元数据信息"""
        info = {}

        try:
            # 使用字典映射更清晰
            field_mapping = {
                '导演': 'vod_director',
                '演员': 'vod_actor',
                'shou': 'vod_year',
                '首映': 'vod_year',
                '地区': 'vod_area'
            }

            info_rows = data('.detail-info-row')
            for row in info_rows.items():
                label = row.find('.detail-info-row-side').text().strip()
                content = row.find('.detail-info-row-main').text().strip()

                for key, field in field_mapping.items():
                    if key in label and content:
                        info[field] = content
                        break

            # 类型标签 - 使用列表推导式优化
            tags = [tag.text().strip()
                    for tag in data('.detail-tags-item').items()]
            valid_tags = [tag for tag in tags if tag]
            info['type_name'] = ','.join(
                valid_tags[1:]) if valid_tags else "未知"

            # 更新状态
            status_elem = data('.detail-info-row-main').eq(3)
            info['vod_remarks'] = status_elem.text(
            ).strip() if status_elem else "正片"

        except Exception as e:
            print(f"解析元数据失败: {e}")
            info.update({
                'vod_director': '',
                'vod_actor': '',
                'vod_year': '',
                'vod_area': '',
                'type_name': '未知',
                'vod_remarks': '正片'
            })

        return info

    def _parse_play_info(self, data, url):
        """解析播放信息 - 核心优化"""
        info = {}

        try:
            play_sources = []
            source_episodes_list = []
                    # 🆕 定义要跳过的线路关键词列表
            skip_keywords = ['4k告诉不卡',  '4K(高峰不卡)', '测试线路']
        
            # 获取所有播放源
            sources = data('.source-swiper-slide')

            for i, source in enumerate(sources.items()):
                source_name = source.find('.source-item-label').text().strip()
                if not source_name:
                    continue
            # 🆕 检查是否包含要跳过的关键词
                skip_this_source = any(keyword in source_name for keyword in skip_keywords)
                if skip_this_source:
                    print(f"⏭️ 跳过线路: {source_name}")
                    continue

                play_sources.append(source_name)

                # 获取对应剧集列表
                episodes = self._parse_episodes(data, i)
                if episodes:
                    source_episodes_list.append('#'.join(episodes))
                else:
                    # 如果没有剧集，添加空列表占位
                    source_episodes_list.append('')

            # 最终处理
            if play_sources and any(source_episodes_list):
                info['vod_play_from'] = '$$$'.join(play_sources)
                info['vod_play_url'] = '$$$'.join(source_episodes_list)
            else:
                # 如果没有有效的播放源，使用默认
                info['vod_play_from'] = '默认'
                info['vod_play_url'] = f"正片${url}"

        except Exception as e:
            print(f"解析播放信息失败: {e}")
            info.update({
                'vod_play_from': '默认',
                'vod_play_url': f"正片${url}"
            })

        return info

    def _parse_episodes(self, data, source_index):
        """解析剧集列表 - 独立方法便于维护"""
        episodes = []

        try:
            episode_lists = data('.episode-list')
            if source_index < len(episode_lists):
                episode_list = episode_lists.eq(source_index)

                for episode in episode_list.find('.episode-item').items():
                    episode_name = episode.text().strip()
                    episode_url = episode.attr('href')

                    if episode_url and episode_name:
                        if not episode_url.startswith('http'):
                            episode_url = f"{self.host}{episode_url}"
                        episodes.append(f"{episode_name}${episode_url}")

        except Exception as e:
            print(f"解析第{source_index}个播放源的剧集失败: {e}")

        return episodes

    def _create_fallback_vod(self, url):
        """创建回退的vod信息"""
        return {
            'vod_name': '加载失败',
            'vod_pic': '',
            'vod_content': '详情加载失败，请重试',
            'vod_director': '',
            'vod_actor': '',
            'vod_year': '',
            'vod_area': '',
            'type_name': '未知',
            'vod_remarks': '加载失败',
            'vod_play_from': '默认',
            'vod_play_url': f"正片${url}"
        }
    def searchContent(self, key, quick, pg="1"):
        """优化搜索性能 - 使用缓存t参数 + 快速解析"""
        try:
            start_time = time.time()
            
            # 1. 获取t参数（带缓存）
            t_value = self.get_t_parameter_cached()
            if not t_value:
                print("❌ 无法获取t参数，搜索失败")
                return {'list': [], 'page': pg}

            # 2. 使用t参数搜索
            result_html = self.search_with_t(t_value, key)
            if not result_html:
                print("❌ 搜索请求失败")
                return {'list': [], 'page': pg}

            # 3. 快速解析搜索结果
            search_data = self.parse_search_results_fast(result_html)
            
            # 4. 转换为标准格式
            videos = []
            for item in search_data.get('items', []):
                video_item = {
                    'vod_id': item.get('detail_url', '').replace(self.host, ''),
                    'vod_name': item.get('title', ''),
                    'vod_pic': "https://vres.zclmjc.com/" + item.get('image_url', ''),
                    'vod_remarks': item.get('year', '') or item.get('type', ''),
                    'vod_content': f"{item.get('region', '')} {item.get('genres', '')} {item.get('actors', '')}"
                }
                # 过滤空值
                video_item = {k: v for k, v in video_item.items() if v}
                if video_item.get('vod_id') and video_item.get('vod_name'):
                    videos.append(video_item)

            elapsed = time.time() - start_time
            print(f"✅ 搜索完成，耗时: {elapsed:.2f}秒，结果数: {len(videos)}")
            
            return {
                'list': videos, 
                'page': pg, 
                'pagecount': 99999, 
                'total': search_data.get('total_results', 0)
            }

        except Exception as e:
            print(f"❌ 搜索过程中出错: {e}")
            return {'list': [], 'page': pg}

    def parse_search_results_fast(self, html_content):
        """快速解析搜索结果 - 优化性能"""
        data = pq(html_content)
        results = {
            'total_results': 0,
            'current_page_results': 0,
            'items': []
        }

        # 快速提取总数
        result_info = data('.search-result-info')
        if result_info:
            result_text = result_info.text()
            match = re.search(r'找到\s*(\d+)\s*部影片', result_text)
            if match:
                results['total_results'] = int(match.group(1))

        # 快速解析每个项目
        search_items = data('.search-result-item')
        
        for item in search_items.items():
            try:
                
                    
                detail_url = item.attr('href') or ''
                if detail_url and not detail_url.startswith('http'):
                    detail_url = "https://103.194.185.51:51123" + detail_url

                # 标题
                title_elem = item.find('.title')
                title = title_elem.text() if title_elem else "未知标题"

                # 图片
                img_elem = item.find('img.lazy').eq(0)
                image_url = img_elem.attr('data-original') or img_elem.attr('src') or ''

                # 其他信息一次性获取
                tags_elem = item.find('.tags')
                tags_text = tags_elem.text() if tags_elem else ""
                tags_parts = tags_text.split('/') if tags_text else []
                
                year = tags_parts[0].strip() if len(tags_parts) > 0 else ""
                region = tags_parts[1].strip() if len(tags_parts) > 1 else ""
                genres = tags_parts[2].strip() if len(tags_parts) > 2 else ""

                # 演员
                actors_elem = item.find('.actors')
                actors = actors_elem.text() if actors_elem else ""

                results['items'].append({
                    'title': title,
                    'detail_url': detail_url,
                    'image_url': image_url,
                    'year': year,
                    'region': region,
                    'genres': genres,
                    'actors': actors
                })
                
            except Exception as e:
                print(f"解析搜索项失败: {e}")
                continue

        results['current_page_results'] = len(results['items'])
        return results


    def get_t_parameter(self):
        """从首页获取 t 参数值 - 现在使用初始化时生成的cookie"""
        url = "https://103.194.185.51:51123"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            # 使用 pyquery 解析 HTML
            data = pq(response.text)
            t_input = data('input[name="t"]')

            if t_input and t_input.attr('value'):
                t_value = t_input.attr('value')
                print(f"成功获取 t 参数: {t_value}")
                return t_value
            else:
                print("未找到 t 参数")
                return None

        except requests.RequestException as e:
            print(f"获取 t 参数请求失败: {e}")
            return None

    def search_with_t(self, t_value, keyword):
        """使用获取的 t 参数进行搜索 - 使用初始化时生成的cookie"""
        url = "https://103.194.185.51:51123/search"
        params = {
            "t": t_value,
            "k": keyword
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()

            print(f"搜索请求状态码: {response.status_code}")
            print(f"搜索URL: {response.url}")

            return response.text

        except requests.RequestException as e:
            print(f"搜索请求失败: {e}")
            return None

    # 其他方法保持不变...
   
   

    def playerContent(self, flag, id, vipFlags):
        """
        播放时使用WebDecryptor解析真实视频地址
        """
        print(f"🎬 开始解析播放地址: {id}")

        try:
            # 如果已经是视频格式，直接返回
            if self.isVideoFormat(id):
                print(f"✅ 已是视频格式，直接返回: {id}")
                return {
                    'parse': 0,
                    'url': id,
                    'header': self.headers
                }

            # 使用WebDecryptor解析播放页面获取真实视频地址
            real_video_url = self._parse_play_page_with_decryptor(id)

            if real_video_url:
                print(f"✅ 解析到真实视频地址: {real_video_url}")

                # 判断是否需要进一步解析
                if self.isVideoFormat(real_video_url):
                    return {
                        'parse': 0,  # 直接播放
                        'url': real_video_url,
                        'header': self.headers
                    }
                else:
                    return {
                        'parse': 1,  # 需要进一步解析
                        'url': real_video_url,
                        'header': self.headers
                    }
            else:
                print(f"❌ 无法解析播放地址，返回原始地址")
                return {
                    'parse': 1,
                    'url': id,
                    'header': self.headers
                }

        except Exception as e:
            print(f"❌ 播放地址解析失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'parse': 1,
                'url': id,
                'header': self.headers
            }

    def _parse_play_page_with_decryptor(self, play_page_url):
        """
        使用WebDecryptor解析播放页面，提取真实视频地址
        """
        try:
            print(f"🔍 使用解密器解析播放页面: {play_page_url}")
            
            # 确保URL完整
            if not play_page_url.startswith('http'):
                play_page_url = f"{self.host}{play_page_url}"
            
            # 创建解密器实例 - 使用你原来的cookie
            decryptor = WebDecryptor()
            
            # 使用spider的cookie
            if hasattr(self, 'current_cookie') and self.current_cookie:
                cookie_value = self.current_cookie.split('=')[1] if '=' in self.current_cookie else self.current_cookie
                decryptor.cookies = {"cdndefend_js_cookie": cookie_value}
            
            # 处理URL获取m3u8地址
            result = decryptor.process_url(play_page_url)
            
            if result and result.get('m3u8_url'):
                m3u8_url = result['m3u8_url']
                print(f"✅ 成功获取m3u8地址: {m3u8_url}")
                
                # 确保URL是绝对路径
                if m3u8_url and not m3u8_url.startswith('http'):
                    if m3u8_url.startswith('//'):
                        m3u8_url = f"https:{m3u8_url}"
                    elif m3u8_url.startswith('/'):
                        m3u8_url = f"{self.host}{m3u8_url}"
                    else:
                        m3u8_url = f"{self.host}/{m3u8_url}"
                
                return m3u8_url
            else:
                print("❌ 解密器未能获取到m3u8地址")
                return None
            
        except Exception as e:
            print(f"❌ 使用解密器解析播放页面失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def isVideoFormat(self, url):
        """检查URL是否是视频格式"""
        if not url:
            return False
        return any(ext in url.lower() for ext in ['.m3u8', '.mp4', '.flv', '.ts', '.mkv', '.avi', '.mov', '.webm'])

    def localProxy(self, param):
        try:
            xtype = param.get('type', '')
            if 'm3u8' in xtype:
                path, url = unquote(param['pdid']).split('_dm_')
                data = requests.get(url, headers=self.headers,
                                    proxies=self.proxies, timeout=10).text
                lines = data.strip().split('\n')
                times = 0.0
                for i in lines:
                    if i.startswith('#EXTINF:'):
                        times += float(i.split(':')[-1].replace(',', ''))
                thread = threading.Thread(
                    target=self.some_background_task, args=(path, int(times)))
                thread.start()
                print('[INFO] 获取视频时长成功', times)
                return [200, 'text/plain', data]
            elif 'xdm' in xtype:
                url = f"{self.host}{unquote(param['path'])}"
                res = requests.get(url, headers=self.headers,
                                   proxies=self.proxies, timeout=10).json()
                dms = []
                for k in res:
                    text = k.get('text')
                    children = k.get('children')
                    if text:
                        dms.append(text.strip())
                    if children:
                        for j in children:
                            ctext = j.get('text')
                            if ctext:
                                ctext = ctext.strip()
                                if "@" in ctext:
                                    dms.append(ctext.split(' ', 1)[-1].strip())
                                else:
                                    dms.append(ctext)
                return self.xml(dms, int(param['times']))
            url = self.d64(param['url'])
            match = re.search(r"loadBannerDirect\('([^']*)'", url)
            if match:
                url = match.group(1)
            res = requests.get(url, headers=self.headers,
                               proxies=self.proxies, timeout=10)
            return [200, res.headers.get('Content-Type'), res.content]
        except Exception as e:
            print(e)
            return [500, 'text/html', '']

    def some_background_task(self, path, times):
        try:
            time.sleep(1)
            purl = f"{self.getProxyUrl()}&path={quote(path)}&times={times}&type=xdm"
            self.fetch(
                f"http://127.0.0.1:9978/action?do=refresh&type=danmaku&path={quote(purl)}")
        except Exception as e:
            print(e)

    def xml(self, dms, times):
        try:
            tsrt = f'共有{len(dms)}条弹幕来袭！！！'
            danmustr = f'<?xml version="1.0" encoding="UTF-8"?>\n<i>\n\t<chatserver>chat.xtdm.com</chatserver>\n\t<chatid>88888888</chatid>\n\t<mission>0</mission>\n\t<maxlimit>99999</maxlimit>\n\t<state>0</state>\n\t<real_name>0</real_name>\n\t<source>k-v</source>\n'
            danmustr += f'\t<d p="0,5,25,16711680,0">{tsrt}</d>\n'
            for i in range(len(dms)):
                base_time = (i / len(dms)) * times
                dm0 = base_time + random.uniform(-3, 3)
                dm0 = round(max(0, min(dm0, times)), 1)
                dm2 = self.get_color()
                dm4 = re.sub(r'[<>&\u0000\b]', '', dms[i])
                tempdata = f'\t<d p="{dm0},1,25,{dm2},0">{dm4}</d>\n'
                danmustr += tempdata
            danmustr += '</i>'
            return [200, "text/xml", danmustr]
        except Exception as e:
            print(e)
            return [500, 'text/html', '']

    def get_color(self):
        # 10% 概率随机颜色, 90% 概率白色
        if random.random() < 0.1:
            h = random.random()
            s = random.uniform(0.7, 1.0)
            v = random.uniform(0.8, 1.0)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            r = int(r * 255)
            g = int(g * 255)
            b = int(b * 255)
            decimal_color = (r << 16) + (g << 8) + b
            return str(decimal_color)
        else:
            return '16777215'

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def gethosts(self):
        url = self.domin
        curl = self.getCache('host_51cn')
        if curl:
            try:
                data = pq(requests.get(curl, headers=self.headers,
                          proxies=self.proxies).content)('a').attr('href')
                if data:
                    parsed_url = urlparse(data)
                    url = parsed_url.scheme + "://" + parsed_url.netloc
            except:
                pass
        try:
            html = pq(requests.get(url, headers=self.headers,
                      proxies=self.proxies).content)
            html_pattern = r"Base64\.decode\('([^']+)'\)"
            html_match = re.search(html_pattern, html(
                'script').eq(-1).text(), re.DOTALL)
            if not html_match:
                raise Exception("未找到html")
            html = pq(b64decode(html_match.group(1)).decode())(
                'script').eq(-4).text()
            return self.hstr(html)
        except Exception as e:
            print(f"获取主域名失败: {str(e)}")
            # self.log(f"获取: {str(e)}")
            return ""

    def getcnh(self):
        data = pq(requests.get(f"{self.host}/homeway.html",
                  headers=self.headers, proxies=self.proxies).content)
        url = data(
            '.post-content[itemprop="articleBody"] blockquote p').eq(0)('a').attr('href')
        parsed_url = urlparse(url)
        host = parsed_url.scheme + "://" + parsed_url.netloc
        self.setCache('host_51cn', host)

    def hstr(self, html):
        pattern = r"(backupLine\s*=\s*\[\])\s+(words\s*=)"
        replacement = r"\1, \2"
        html = re.sub(pattern, replacement, html)
        data = f"""
        var Vx = {{
            range: function(start, end) {{
                const result = [];
                for (let i = start; i < end; i++) {{
                    result.push(i);
                }}
                return result;
            }},

            map: function(array, callback) {{
                const result = [];
                for (let i = 0; i < array.length; i++) {{
                    result.push(callback(array[i], i, array));
                }}
                return result;
            }}
        }};

        Array.prototype.random = function() {{
            return this[Math.floor(Math.random() * this.length)];
        }};

        var location = {{
            protocol: "https:"
        }};

        function executeAndGetResults() {{
            var allLines = lineAry.concat(backupLine);
            var resultStr = JSON.stringify(allLines);
            return resultStr;
        }};
        {html}
        executeAndGetResults();
        """
        return self.p_qjs(data)

    def p_qjs(self, js_code):
        try:
            # 使用execjs执行JavaScript代码并获取实际生成的域名
            try:

                # 创建JavaScript执行环境
                ctx = execjs.compile(js_code)

                # 执行获取域名列表的函数
                result = ctx.call("executeAndGetResults")

                # 解析JSON结果
                import json
                domains = json.loads(result)

                if domains and len(domains) > 0:
                    print("获取主页成功")
                    return domains

            except ImportError:
                self.log("execjs未安装，尝试其他方法")

            # 如果execjs不可用，尝试使用subprocess调用Node.js
            try:
                import subprocess
                import tempfile
                import os

                # 创建临时JS文件
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                    # 修改JS代码，使其直接输出结果
                    modified_js = js_code.replace(
                        'executeAndGetResults();',
                        'console.log(executeAndGetResults());'
                    )
                    f.write(modified_js)
                    temp_file = f.name

                # 使用Node.js执行
                result = subprocess.check_output(['node', temp_file],
                                                 stderr=subprocess.PIPE,
                                                 text=True)

                # 清理临时文件
                os.unlink(temp_file)

                # 解析结果
                import json
                domains = json.loads(result.strip())
                return domains

            except Exception as e:
                self.log(f"Node.js执行失败: {e}")

            # 如果以上方法都失败，尝试从JS代码中提取已生成的域名
            import re

            # 查找lineAry和backupLine的定义
            lineAry_match = re.search(
                r'lineAry\s*=\s*(\[.*?\]);', js_code, re.DOTALL)
            backupLine_match = re.search(
                r'backupLine\s*=\s*(\[.*?\]);', js_code, re.DOTALL)

            domains = []

            # 尝试直接提取lineAry的值
            if lineAry_match:
                try:
                    lineAry_str = lineAry_match.group(1)
                    # 简单的字符串解析，提取URL
                    urls = re.findall(r"https?://[^'\"]+", lineAry_str)
                    domains.extend(urls)
                except:
                    pass

            # 尝试直接提取backupLine的值
            if backupLine_match:
                try:
                    backupLine_str = backupLine_match.group(1)
                    # 简单的字符串解析，提取URL
                    urls = re.findall(r"https?://[^'\"]+", backupLine_str)
                    domains.extend(urls)
                except:
                    pass

            # 如果成功提取到域名，返回它们
            if domains:
                return domains

            # 如果所有方法都失败，返回空列表
            self.log("无法从JS代码中提取域名")
            return []

        except Exception as e:
            self.log(f"域名提取失败: {e}")
            return []

    def get_domains(self):
        html = pq(requests.get(self.domin, headers=self.headers,
                  proxies=self.proxies).content)
        html_pattern = r"Base64\.decode\('([^']+)'\)"
        html_match = re.search(html_pattern, html(
            'script').eq(-1).text(), re.DOTALL)
        if not html_match:
            raise Exception("未找到html")
        html = b64decode(html_match.group(1)).decode()
        words_pattern = r"words\s*=\s*'([^']+)'"
        words_match = re.search(words_pattern, html, re.DOTALL)
        if not words_match:
            raise Exception("未找到words")
        words = words_match.group(1).split(',')
        main_pattern = r"lineAry\s*=.*?words\.random\(\)\s*\+\s*'\.([^']+)'"
        domain_match = re.search(main_pattern, html, re.DOTALL)
        if not domain_match:
            raise Exception("未找到主域名")
        domain_suffix = domain_match.group(1)
        domains = []
        for _ in range(3):
            random_word = random.choice(words)
            domain = f"https://{random_word}.{domain_suffix}"
            domains.append(domain)
        return domains

    def getfod(self, id):
        url = f"{self.host}{id}"
        data = pq(requests.get(url, headers=self.headers,
                  proxies=self.proxies).content)
        vdata = data('.post-content[itemprop="articleBody"]')
        r = ['.txt-apps', '.line', 'blockquote', '.tags', '.content-tabs']
        for i in r:
            vdata.remove(i)
        p = vdata('p')
        videos = []
        for i, x in enumerate(vdata('h2').items()):
            c = i*2
            videos.append({
                'vod_id': p.eq(c)('a').attr('href'),
                'vod_name': p.eq(c).text(),
                'vod_pic': f"{self.getProxyUrl()}&url={self.e64(p.eq(c+1)('img').attr('data-xkrkllgl'))}",
                'vod_remarks': x.text()
            })
        return videos

    def host_late(self, url_list):
        if isinstance(url_list, str):
            urls = [u.strip() for u in url_list.split(',')]
        else:
            urls = url_list

        if len(urls) <= 1:
            return urls[0] if urls else ''

        results = {}
        threads = []

        def test_host(url):
            try:
                start_time = time.time()
                response = requests.head(
                    url, headers=self.headers, proxies=self.proxies, timeout=1.0, allow_redirects=False)
                delay = (time.time() - start_time) * 1000
                results[url] = delay
            except Exception as e:
                results[url] = float('inf')

        for url in urls:
            t = threading.Thread(target=test_host, args=(url,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return min(results.items(), key=lambda x: x[1])[0]

    def getlist(self, data, tid=''):
        videos = []
        l = '/mrdg' in tid
        for k in data.items():
            a = k.attr('href')
            b = k('h2').text()
            c = k('span[itemprop="datePublished"]').text()
            if a and b and c:
                videos.append({
                    'vod_id': f"{a}{'@folder' if l else ''}",
                    'vod_name': b.replace('\n', ' '),
                    'vod_pic': f"{self.getProxyUrl()}&url={self.e64(k('script').text())}&type=img",
                    'vod_remarks': c,
                    'vod_tag': 'folder' if l else '',
                    'style': {"type": "rect", "ratio": 1.33}
                })
        return videos

    def aesimg(self, word):

        key = b64decode("Bp2ZFMpge+R67heFSoTDcNur2xa8pJACIOIvcK35pYU=")
        # JavaScript的十六进制字符串IV转换为Python bytes
        iv = bytes.fromhex("6b6b7973313233343536373839303030")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(word), AES.block_size)
        return decrypted
