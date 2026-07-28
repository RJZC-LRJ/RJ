#coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox / 影视仓  Python源脚本
站点: 柯南影视 (www.knvod.com)
模板: MacCMS v10 + ds3
说明: 需手机UA访问，7.1起关闭PC端
"""

import sys
import re
import json
import requests
from urllib.parse import quote
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def __init__(self):
        super().__init__()
        self.site = 'https://www.knvod.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': 'https://www.knvod.com/'
        })
        self.cateManual = {
            '电影': '1',
            '连续剧': '2',
            '动漫': '3',
            '综艺': '4'
        }

    def init(self, extend=""):
        pass

    def getName(self):
        return "柯南影视"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _get(self, url):
        try:
            r = self.session.get(url, timeout=15)
            r.encoding = 'utf-8'
            return r.text
        except Exception as e:
            print(f'_get error: {e}')
            return None

    def _fixUrl(self, url):
        if not url:
            return ''
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.site + url
        return self.site + '/' + url

    def _clean(self, s):
        if not s:
            return ''
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def getVid(self, url):
        if not url:
            return ''
        m = re.search(r'/vdetail/(\d+)\.html', url)
        if m:
            return m.group(1)
        m = re.search(r'/vplay/(\d+)-', url)
        if m:
            return m.group(1)
        return ''

    def _parse_list(self, html):
        """从HTML中解析视频列表"""
        videos = []
        seen = set()

        # 匹配所有public-list-box区块
        items = re.findall(r'<div\s+class="public-list-box[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>', html, re.DOTALL)

        # 如果结果少，尝试更宽松的匹配 (搜索结果页格式)
        if len(items) < 10:
            items2 = re.findall(r'<div\s+class="public-list-box search-box[^"]*"[^>]*>.*?(?=<div\s+class="public-list-box|$)', html, re.DOTALL)
            if items2:
                items = items2

        # 直接匹配所有vdetail链接作为备用方案
        if not items or len(items) < 5:
            all_links = re.findall(r'<a[^>]+href="(/vdetail/\d+\.html)"[^>]*title="([^"]*)"[^>]*>.*?<img[^>]+data-src="([^"]+)"', html, re.DOTALL)
            for href, title, pic in all_links:
                vid = self.getVid(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                title = self._clean(title)
                pic = self._fixUrl(pic)
                if 'data:image' in pic:
                    pic = ''
                if title:
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': pic,
                        'vod_remarks': ''
                    })
            if videos:
                return videos

        for block in items:
            # 标题和链接 - 优先匹配title属性
            tm = re.search(r'href="(/vdetail/\d+\.html)"[^>]*title="([^"]*)"', block)
            if not tm:
                # 搜索页格式
                tm = re.search(r'class="thumb-txt[^"]*"[^>]*>\s*<a[^>]+href="(/vdetail/\d+\.html)"[^>]*>([^<]+)<', block)
            if not tm:
                tm = re.search(r'href="(/vdetail/\d+\.html)"[^>]*>\s*([^<\n]+)<', block)
            if not tm:
                continue

            href = tm.group(1)
            title = self._clean(tm.group(2))

            vid = self.getVid(href)
            if not vid or vid in seen:
                continue
            seen.add(vid)

            # 封面 - 优先data-src
            pic = ''
            pm = re.search(r'data-src="([^"]+)"', block)
            if not pm:
                pm = re.search(r'src="([^"]+)"', block)
            if pm:
                pic = self._fixUrl(pm.group(1))
                if 'data:image' in pic or 'loading' in pic or 'zanwupic' in pic:
                    pic = ''

            # 备注
            note = ''
            nm = re.search(r'class="public-list-prb[^"]*"[^>]*>([^<]+)<', block)
            if not nm:
                nm = re.search(r'class="public-bg[^"]*"[^>]*>([^<]*)<', block)
            if nm:
                note = nm.group(1).strip()

            if title:
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': note
                })
        return videos

    def _build_category_url(self, tid, page, extend):
        """构建分类URL
        URL格式: /vshow/{id}-{地区}-{排序}-{类型}-{语言}-{}-{}-{}-{分页}-{}-{年份}.html
        共11个部分，用-分隔
        """
        area = extend.get('area', '') if extend else ''
        sort = extend.get('sort', '') if extend else ''
        typ = extend.get('type', '') if extend else ''
        lang = extend.get('lang', '') if extend else ''
        year = extend.get('year', '') if extend else ''

        # URL编码
        area_enc = quote(area) if area else ''
        sort_enc = sort
        typ_enc = quote(typ) if typ else ''
        lang_enc = quote(lang) if lang else ''
        year_enc = year
        page_str = str(page) if page and int(page) > 1 else ''

        # 11个部分: 地区-排序-类型-语言-空-空-空-分页-空-空-年份
        parts = [
            area_enc,    # 0: 地区
            sort_enc,    # 1: 排序
            typ_enc,     # 2: 类型
            lang_enc,    # 3: 语言
            '',          # 4: 空
            '',          # 5: 空
            '',          # 6: 空
            page_str,    # 7: 分页
            '',          # 8: 空
            '',          # 9: 空
            year_enc,    # 10: 年份
        ]

        url_part = '-'.join(parts)
        return f'{self.site}/vshow/{tid}-{url_part}.html'

    # ==================== TVBox 接口 ====================

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}
        try:
            # 分类
            for k, v in self.cateManual.items():
                result['class'].append({'type_id': str(v), 'type_name': k})

            # 筛选条件 (通用，所有分类都适用)
            common_filters = [
                {
                    'key': 'sort',
                    'name': '排序',
                    'value': [
                        {'n': '最新', 'v': 'time'},
                        {'n': '最热', 'v': 'hits'},
                        {'n': '评分', 'v': 'score'},
                    ]
                },
                {
                    'key': 'type',
                    'name': '类型',
                    'value': [
                        {'n': '全部', 'v': ''},
                        {'n': '喜剧', 'v': '喜剧'},
                        {'n': '爱情', 'v': '爱情'},
                        {'n': '恐怖', 'v': '恐怖'},
                        {'n': '动作', 'v': '动作'},
                        {'n': '科幻', 'v': '科幻'},
                        {'n': '剧情', 'v': '剧情'},
                        {'n': '战争', 'v': '战争'},
                        {'n': '警匪', 'v': '警匪'},
                        {'n': '犯罪', 'v': '犯罪'},
                        {'n': '动画', 'v': '动画'},
                        {'n': '奇幻', 'v': '奇幻'},
                        {'n': '武侠', 'v': '武侠'},
                        {'n': '冒险', 'v': '冒险'},
                    ]
                },
                {
                    'key': 'area',
                    'name': '地区',
                    'value': [
                        {'n': '全部', 'v': ''},
                        {'n': '内地', 'v': '内地'},
                        {'n': '港台', 'v': '港台'},
                        {'n': '美国', 'v': '美国'},
                        {'n': '韩国', 'v': '韩国'},
                        {'n': '日本', 'v': '日本'},
                        {'n': '泰国', 'v': '泰国'},
                        {'n': '印度', 'v': '印度'},
                        {'n': '法国', 'v': '法国'},
                        {'n': '英国', 'v': '英国'},
                    ]
                },
                {
                    'key': 'year',
                    'name': '年份',
                    'value': [
                        {'n': '全部', 'v': ''},
                        {'n': '2026', 'v': '2026'},
                        {'n': '2025', 'v': '2025'},
                        {'n': '2024', 'v': '2024'},
                        {'n': '2023', 'v': '2023'},
                        {'n': '2022', 'v': '2022'},
                        {'n': '2021', 'v': '2021'},
                        {'n': '2020', 'v': '2020'},
                        {'n': '2019', 'v': '2019'},
                        {'n': '2018', 'v': '2018'},
                    ]
                },
                {
                    'key': 'lang',
                    'name': '语言',
                    'value': [
                        {'n': '全部', 'v': ''},
                        {'n': '国语', 'v': '国语'},
                        {'n': '粤语', 'v': '粤语'},
                        {'n': '韩语', 'v': '韩语'},
                        {'n': '日语', 'v': '日语'},
                        {'n': '英语', 'v': '英语'},
                        {'n': '泰语', 'v': '泰语'},
                    ]
                },
            ]

            for k, v in self.cateManual.items():
                result['filters'][str(v)] = common_filters
        except Exception as e:
            print(f'homeContent error: {e}')
        return result

    def homeVideoContent(self):
        # 首页推荐从电影分类第一页获取
        result = {'list': [], 'parse': 0, 'jx': 0}
        try:
            cat = self.categoryContent('1', '1', True, {})
            result['list'] = cat.get('list', [])[:20]
        except Exception as e:
            print(f'homeVideoContent error: {e}')
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        try:
            url = self._build_category_url(tid, page, extend)

            html = self._get(url)
            if not html:
                return result

            videos = self._parse_list(html)
            result['list'] = videos

            # 分页信息
            result['page'] = page
            result['pagecount'] = page + 1 if len(videos) > 0 else page
            result['limit'] = len(videos)
            result['total'] = len(videos)
        except Exception as e:
            print(f'categoryContent error: {e}')
        return result

    def detailContent(self, ids):
        result = {'list': [], 'parse': 0, 'jx': 0}
        vid = ids[0] if ids else ''
        if not vid:
            return result
        try:
            url = f'{self.site}/vdetail/{vid}.html'
            html = self._get(url)
            if not html:
                return result

            # 标题从title标签提取
            title_match = re.search(r'<title>《(.+?)》', html)
            title = title_match.group(1) if title_match else ''
            if not title:
                m = re.search(r'<h1[^>]*>([^<]+)<', html)
                if m:
                    title = m.group(1).strip()

            # 图片
            pic = ''
            img_match = re.search(r'class="[^"]*lazy1[^"]*"[^>]+data-src="([^"]+)"', html)
            if not img_match:
                img_match = re.search(r'class="[^"]*lazy1[^"]*"[^>]+src="([^"]+)"', html)
            if not img_match:
                img_match = re.search(r'video-cover[^>]*>.*?data-src="([^"]+)"', html, re.DOTALL)
            if not img_match:
                img_match = re.search(r'video-cover[^>]*>.*?src="([^"]+)"', html, re.DOTALL)
            if img_match:
                pic = self._fixUrl(img_match.group(1))
                if 'data:image' in pic or 'loading' in pic or 'zanwupic' in pic:
                    pic = ''

            # 剧情从meta description提取
            desc = ''
            desc_match = re.search(r'<meta name="description" content="(.+?)"', html)
            if desc_match:
                desc = desc_match.group(1)
                desc = desc.replace('剧情介绍：', '').strip()

            # 从页面文本提取导演/主演
            actor = ''
            director = ''
            info_match = re.search(r'class="slide-info[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if info_match:
                info_text = info_match.group(1)
                # 去掉HTML标签
                info_text = re.sub(r'<[^>]+>', ' ', info_text)
                info_text = re.sub(r'\s+', ' ', info_text).strip()
                actor_match = re.search(r'主演[:：]\s*([^\n]+?)(?:导演|简介|$)', info_text)
                if actor_match:
                    actor = actor_match.group(1).strip()
                director_match = re.search(r'导演[:：]\s*([^\n]+?)(?:主演|简介|$)', info_text)
                if director_match:
                    director = director_match.group(1).strip()

            # 播放线路和集数
            play_from = []
            play_url = []

            # 获取所有线路标签 - 在swiper-wrapper中的a标签
            tabs = []
            tab_match = re.search(r'class="[^"]*anthology-tab[^"]*"[^>]*>.*?<div class="swiper-wrapper">(.*?)</div>', html, re.DOTALL)
            if tab_match:
                tabs_html = tab_match.group(1)
                # 提取每个swiper-slide的文本
                slide_matches = re.findall(r'<a[^>]*class="[^"]*swiper-slide[^"]*"[^>]*>(.*?)</a>', tabs_html, re.DOTALL)
                for slide in slide_matches:
                    # 去掉i标签和badge，取纯文本
                    text = re.sub(r'<i[^>]*>.*?</i>', '', slide)
                    text = re.sub(r'<span[^>]*>.*?</span>', '', text)
                    text = text.replace('&nbsp;', ' ').strip()
                    if text:
                        tabs.append(text)

            # 如果上面没找到，备用方案
            if not tabs:
                tabs = re.findall(r'<a[^>]*class="[^"]*anthology-tab[^"]*"[^>]*>([^<]+)<', html)
            if not tabs:
                tabs = re.findall(r'class="[^"]*anthology-tab[^"]*"[^>]*>.*?<a[^>]*>([^<]+)<', html, re.DOTALL)

            # 获取所有播放列表面板
            panels = re.findall(r'class="[^"]*anthology-list-play[^"]*"[^>]*>(.*?)</ul>', html, re.DOTALL)
            if not panels:
                panels = re.findall(r'class="[^"]*anthology-list-box[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)

            for i, tab_text in enumerate(tabs):
                tab_text = tab_text.strip() or f'线路{i+1}'
                play_from.append(tab_text)

                episodes = []
                if i < len(panels):
                    panel_html = panels[i]
                    # 提取所有播放链接
                    ep_links = re.findall(r'<li[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([^<]+)<', panel_html)
                    for ep_href, ep_name in ep_links:
                        ep_name = ep_name.strip()
                        if ep_name and ep_href:
                            episodes.append(f'{ep_name}${ep_href}')

                play_url.append('#'.join(episodes))

            vod = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'type_name': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': '',
                'vod_actor': actor,
                'vod_director': director,
                'vod_content': desc,
                'vod_play_from': '$$$'.join(play_from) if play_from else '',
                'vod_play_url': '$$$'.join(play_url) if play_url else ''
            }
            result['list'].append(vod)
        except Exception as e:
            print(f'detailContent error: {e}')
            import traceback
            traceback.print_exc()
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        try:
            play_url = id
            if id and not id.startswith('http'):
                play_url = self.site + id

            # 请求播放页
            html = self._get(play_url)
            if not html:
                result['parse'] = 1
                result['url'] = play_url
                result['jx'] = 0
                result['header'] = {
                    'User-Agent': self.session.headers.get('User-Agent', ''),
                    'Referer': self.site + '/'
                }
                return result

            # 提取player_aaaa中的url
            player_url = ''
            m = re.search(r'player_aaaa\s*=\s*\{[^}]*"url"\s*:\s*"([^"]+)"', html)
            if m:
                player_url = m.group(1)

            # 提取iframe播放器URL
            iframe_url = ''
            m2 = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            if m2:
                iframe_url = m2.group(1)
            else:
                m3 = re.search(r"src='([^']+player[^']+)'", html)
                if m3:
                    iframe_url = m3.group(1)

            # 如果有加密的url，返回播放页让TVBox解析
            # 如果有iframe，返回iframe地址
            if iframe_url and iframe_url.startswith('http'):
                result['parse'] = 1
                result['url'] = iframe_url
                result['jx'] = 0
                result['header'] = {
                    'User-Agent': self.session.headers.get('User-Agent', ''),
                    'Referer': self.site + '/'
                }
            else:
                # 返回播放页URL，让TVBox自己解析
                result['parse'] = 1
                result['url'] = play_url
                result['jx'] = 0
                result['header'] = {
                    'User-Agent': self.session.headers.get('User-Agent', ''),
                    'Referer': self.site + '/'
                }
        except Exception as e:
            print(f'playerContent error: {e}')
            result['parse'] = 1
            result['url'] = id
            result['jx'] = 0
            result['header'] = {}
        return result

    def searchContent(self, key, quick, pg='1'):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        try:
            # 搜索URL: /search/-------------.html?wd={keyword}
            if page == 1:
                url = f'{self.site}/search/-------------.html?wd={quote(key)}'
            else:
                url = f'{self.site}/search/-------------{page}.html?wd={quote(key)}'

            html = self._get(url)
            if not html:
                return result

            videos = self._parse_list(html)
            result['list'] = videos

            # 分页信息
            result['page'] = page
            result['pagecount'] = page + 1 if len(videos) > 0 else page
            result['limit'] = len(videos)
            result['total'] = len(videos)
        except Exception as e:
            print(f'searchContent error: {e}')
        return result

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]
