#coding=utf-8
# ============================================================
# 枫叶4K影院 TVBox爬虫
#
# 【OCR配置 - 三选一，不需要改】
# 本脚本内置了 3 种验证码识别方式，会自动依次尝试：
#   1. 自建OCR服务器（如果你有的话，在下面配置）
#   2. UTOOL Pro 在线验证码识别（免费，验证码专用）
#   3. OCR.space 在线通用OCR（免费，每分钟限10次）
# 只要网络通，不需要自建服务器也能用搜索和分类功能。
# ============================================================
OCR_SERVER = ''  # 如果有自建服务器，填 'http://IP:端口'，否则留空

import sys
import re
import json
import random
import base64
import html as html_module
import requests
sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.site = 'https://www.cd-zj.com'
        self.session = requests.Session()
        self.ua = 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        self.base_headers = {
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(self.base_headers)
        self._verify_passed = {}  # 记录已通过验证的URL前缀

        # 分类配置（使用可用的label页面）
        self.cateManual = {
            '2': '电视剧', '1': '电影', '4': '动漫', '3': '综艺', '5': '热门短剧',
            'qq': '腾讯VIP精选', 'bli': 'B站VIP精选', 'youku': '优酷VIP精选'
        }

        # 播放线路解析器配置
        self.parser_config = {
            'JD4K':   {'show': '至臻4k', 'ps': '1', 'parse': 'https://fgsrg.hzqingshan.com/player/?url='},
            'JD2K':   {'show': '蓝光2k', 'ps': '1', 'parse': 'https://fgsrg.hzqingshan.com/player/?url='},
            'co':     {'show': '蓝光2k', 'ps': '1', 'parse': 'https://zsmyyrv.hzqingshan.com/player/?url='},
            'BBA':    {'show': '蓝光2k', 'ps': '1', 'parse': 'https://zsmyyrv.hzqingshan.com/player/?url='},
            'YYNB':   {'show': '蓝光2k', 'ps': '1', 'parse': 'https://zsmyyrv.hzqingshan.com/player/?url='},
            'dyttm3u8': {'show': '自营t', 'ps': '0', 'parse': ''},
            '1080zy':  {'show': '自营y', 'ps': '0', 'parse': ''},
            '1080zyk': {'show': '自营y', 'ps': '0', 'parse': ''},
            'rym3u8':  {'show': '自营r', 'ps': '0', 'parse': ''},
            'ruyi':    {'show': '自营r', 'ps': '0', 'parse': ''},
        }

        self.play_headers = {
            'User-Agent': self.ua,
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }

    def _clean(self, text):
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = html_module.unescape(text)
        text = text.replace('&amp;', '&').replace('\xa0', ' ').replace('\u3000', ' ')
        text = ' '.join(text.split())
        return text.strip()

    def _get(self, url, referer=None, timeout=15):
        try:
            h = {}
            if referer:
                h['Referer'] = referer
            r = self.session.get(url, timeout=timeout, headers=h if h else None)
            r.encoding = 'utf-8'
            if r.status_code == 403:
                return ''
            return r.text
        except:
            return ''

    def _recognize_captcha(self, img_data):
        """
        多路OCR识别验证码，返回4位数字字符串，全部失败返回空。
        识别优先级：
          1. 自建OCR服务器（如果配置了）
          2. UTOOL Pro 在线验证码识别（免费专用）
          3. OCR.space 在线通用OCR（免费，速率受限）
        """
        b64 = base64.b64encode(img_data).decode('utf-8')

        # 方式1: 自建OCR服务器
        if OCR_SERVER:
            try:
                r = requests.post(
                    f'{OCR_SERVER}/ocr',
                    data=img_data,
                    headers={'Content-Type': 'application/octet-stream'},
                    timeout=10
                )
                res = r.json()
                if res.get('code') == 0:
                    result = res.get('result', '')
                    if len(result) == 4 and result.isdigit():
                        return result
            except:
                pass

        # 方式2: UTOOL Pro 在线验证码识别（验证码专用，最准）
        try:
            r = requests.post(
                'https://api.leepow.com/verifycode',
                json={'image': b64},
                timeout=15
            )
            res = r.json()
            if res.get('code') == 0:
                result = str(res.get('data', ''))
                result = result.lower()
                result = result.replace('o', '0').replace('l', '1').replace('i', '1')
                result = result.replace('z', '2').replace('s', '5').replace('b', '6')
                result = result.replace('g', '9').replace('q', '9')
                cleaned = ''.join(c for c in result if c.isdigit())
                if len(cleaned) == 4:
                    return cleaned
        except:
            pass

        # 方式3: OCR.space 在线通用OCR（备选）
        try:
            r = requests.post(
                'https://api.ocr.space/parse/image',
                data={
                    'apikey': 'helloworld',
                    'base64Image': f'data:image/png;base64,{b64}',
                    'language': 'eng',
                    'isOverlayRequired': 'false',
                    'OCREngine': '2',
                },
                timeout=15
            )
            res = r.json()
            if res.get('OCRExitCode') == 1 and res.get('ParsedResults'):
                text = res['ParsedResults'][0].get('ParsedText', '').strip()
                text = text.lower()
                text = text.replace('o', '0').replace('l', '1').replace('i', '1')
                text = text.replace('z', '2').replace('s', '5').replace('b', '6')
                text = text.replace('g', '9').replace('q', '9')
                cleaned = ''.join(c for c in text if c.isdigit())
                if len(cleaned) == 4:
                    return cleaned
        except:
            pass

        return ''

    def _bypass_captcha(self, url, referer=None, max_attempts=20):
        """
        尝试绕过验证码。
        返回通过验证后的页面HTML，失败返回空字符串。
        """
        # 先正常访问
        html = self._get(url, referer=referer)
        if not html or '系统安全验证' not in html:
            return html

        for attempt in range(max_attempts):
            try:
                # 获取验证码图片
                r = self.session.get(
                    f'{self.site}/captcha.php?type=code&r={random.random()}',
                    headers={'Referer': url}
                )
                if r.content[:4] != b'\x89PNG':
                    continue

                code = self._recognize_captcha(r.content)
                if not code or len(code) != 4:
                    continue

                # 提交验证
                r = self.session.post(
                    f'{self.site}/captcha.php?type=verify',
                    data={'check': code},
                    headers={
                        'Referer': url,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }
                )

                try:
                    res = r.json()
                    if res.get('code') == 1:
                        # 验证成功，重新访问目标页面
                        html = self._get(url, referer=url)
                        if html and '系统安全验证' not in html:
                            return html
                except:
                    pass

            except Exception as e:
                continue

        return ''

    def _get_parser_html(self, parser_url, video_id):
        """访问解析器页面获取 token"""
        url = parser_url + video_id
        try:
            r = self.session.get(url, timeout=15, headers={
                'User-Agent': self.ua,
                'Referer': self.site + '/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
            })
            r.encoding = 'utf-8'
            return r.text
        except:
            return ''

    def _resolve_video_url(self, video_id, parser_url):
        """通过解析器获取真实视频URL"""
        try:
            html = self._get_parser_html(parser_url, video_id)
            if not html:
                return ''

            te_match = re.search(r'data-te="([^"]+)"', html)
            if not te_match:
                return ''

            token = te_match.group(1)
            bt_match = re.search(r'data-bt="([^"]+)"', html)
            base_path = bt_match.group(1) if bt_match else '/player/'

            parsed = requests.utils.urlparse(parser_url)
            api_url = f'{parsed.scheme}://{parsed.netloc}{base_path}mplayer.php'

            r = self.session.post(api_url, data={
                'url': video_id,
                'token': token
            }, headers={
                'User-Agent': self.ua,
                'Referer': parser_url + video_id,
                'Origin': f'{parsed.scheme}://{parsed.netloc}',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            }, timeout=15)

            data = r.json()
            if data.get('code') == 200 and data.get('url'):
                return data['url']
            return ''
        except Exception as e:
            print(f'resolve_video_url error: {e}')
            return ''

    def _pick_best_quality(self, raw_url, referer=''):
        """解析 master m3u8，选最高码率"""
        try:
            h = dict(self.play_headers)
            if referer:
                h['Referer'] = referer
            r = self.session.get(raw_url, headers=h, timeout=15)
            r.encoding = 'utf-8'
            content = r.text
        except:
            return raw_url

        if '#EXT-X-STREAM-INF' not in content:
            return raw_url

        variants = []
        for m in re.finditer(
            r'#EXT-X-STREAM-INF:.*?BANDWIDTH=(\d+).*?(?:RESOLUTION=(\d+)x(\d+))?.*?\n(.*?)(?:\n|$)',
            content
        ):
            bw = int(m.group(1))
            url = m.group(4).strip()
            w = int(m.group(2)) if m.group(2) else 0
            h = int(m.group(3)) if m.group(3) else 0
            variants.append((bw, w, h, url))

        if not variants:
            return raw_url

        variants.sort(key=lambda x: (x[0], x[1] * x[2]), reverse=True)
        best = variants[0]
        chosen_url = best[3]
        if not chosen_url.startswith('http'):
            base = raw_url.rsplit('/', 1)[0]
            chosen_url = base + '/' + chosen_url
        return chosen_url

    def init(self, extend=''):
        pass

    def getName(self):
        return '枫叶4K影院'

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}
        for tid, name in self.cateManual.items():
            result['class'].append({'type_id': str(tid), 'type_name': str(name)})
        return result

    def homeVideoContent(self):
        result = {'list': [], 'parse': 0, 'jx': 0}
        try:
            html = self._get(f'{self.site}/label/qq.html', referer=self.site)
            videos = self._extract_list(html)
            result['list'] = videos[:24]
        except:
            pass
        return result

    def _extract_list(self, html):
        """从HTML中提取视频列表 - 按视频卡片精确提取，避免ID和海报错位"""
        videos = []
        seen = set()
        if not html:
            return videos

        # 方案1: 精确匹配 public-list-exp 卡片（首页/分类页标准结构）
        for m in re.finditer(
            r'<a[^>]*class="[^"]*public-list-exp[^"]*"[^>]*href="/detail/(\d+)\.html"[^>]*>(.*?)</a>',
            html, re.DOTALL
        ):
            vid = m.group(1)
            inner = m.group(2)
            full_a = m.group(0)
            if vid in seen:
                continue
            seen.add(vid)

            # 标题：优先取a标签的title，其次取img的alt
            title = ''
            tm = re.search(r'title="([^"]+)"', full_a)
            if tm:
                title = self._clean(tm.group(1))
            if not title:
                tm = re.search(r'alt="([^"]+)"', inner)
                if tm:
                    title = self._clean(tm.group(1))
            if not title:
                # 从右侧thumb-txt中找（搜索结果页结构）
                continue

            pic = ''
            pm = re.search(r'data-src="([^"]+)"', inner)
            if not pm:
                pm = re.search(r'src="(https?://[^"]+\.(?:jpg|webp|png)[^"]*)"', inner)
            if pm:
                pic = pm.group(1).replace('&amp;', '&')

            remarks = ''
            # 优先匹配更新状态（public-list-prb）
            rm = re.search(r'public-list-prb[^>]*>(?:<[^>]+>)?\s*([^<]+)', inner)
            if rm:
                remarks = self._clean(rm.group(1))
            if not remarks:
                # 再匹配其他状态标签（今日更新、4K等）
                rm = re.search(r'public-prt[^>]*>(?:<[^>]+>)?\s*([^<]+)', inner)
                if rm:
                    remarks = self._clean(rm.group(1))
            if not remarks:
                rm = re.search(r'更新至([^<]+)', inner)
                if rm:
                    remarks = self._clean(rm.group(1))

            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks[:40] if remarks else ''
            })

        if videos:
            return videos

        # 方案2: fallback 旧逻辑（兼容其他模板结构）
        for m in re.finditer(r'href="/detail/(\d+)\.html"', html):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, m.start() - 500)
            end = min(len(html), m.end() + 1500)
            snippet = html[start:end]

            title = ''
            tm = re.search(r'title="([^"]+)"', snippet)
            if tm:
                title = self._clean(tm.group(1))

            pic = ''
            pm = re.search(r'data-src="([^"]+)"', snippet)
            if not pm:
                pm = re.search(r'src="(https?://[^"]+\.(?:jpg|webp|png)[^"]*)"', snippet)
            if pm:
                pic = pm.group(1).replace('&amp;', '&')

            remarks = ''
            rm = re.search(r'pic-text[^>]*>\s*([^<]+)\s*<', snippet)
            if rm:
                remarks = self._clean(rm.group(1))
            if not remarks:
                rm = re.search(r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>(.*?)</span>', snippet, re.DOTALL)
                if rm:
                    remarks = self._clean(rm.group(1))

            if title:
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks[:40] if remarks else ''
                })
        return videos

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1

        if tid in ('qq', 'bli', 'youku'):
            url = f'{self.site}/label/{tid}/page/{page}.html' if page > 1 else f'{self.site}/label/{tid}.html'
        elif tid in ('2', '1', '4', '3', '5'):
            # 翻页格式: /cupfox-list/{tid}--------{page}---.html
            url = f'{self.site}/cupfox-list/{tid}--------{page}---.html' if page > 1 else f'{self.site}/cupfox-list/{tid}-----------.html'
        else:
            url = f'{self.site}/label/{tid}/page/{page}.html' if page > 1 else f'{self.site}/label/{tid}.html'

        # 尝试绕过验证码
        html = self._bypass_captcha(url, referer=self.site, max_attempts=15)
        if not html:
            # 验证码绕不过就返回空，绝不回退首页（否则分类内容会混在一起）
            result['page'] = page
            result['pagecount'] = 1
            result['limit'] = 0
            result['total'] = 0
            return result

        videos = self._extract_list(html)
        result['list'] = videos
        # 判断是否有下一页：找页码区域是否有比当前页大的链接
        next_page = page + 1
        has_next = bool(re.search(rf'cupfox-list/{tid}--------{next_page}---\.html', html))
        if not has_next:
            has_next = bool(re.search(r'下一页|next page-link|»|›', html))
        result['page'] = page
        result['pagecount'] = page + 1 if has_next else page
        result['limit'] = len(videos)
        result['total'] = 99999
        return result

    def detailContent(self, ids):
        result = {'list': [], 'parse': 0, 'jx': 0}
        vid = ''
        if isinstance(ids, list):
            vid = ids[0] if ids else ''
        elif ids:
            vid = str(ids)
        if not vid:
            return result

        detail_html = self._get(f'{self.site}/detail/{vid}.html', referer=self.site)
        if not detail_html:
            return result

        # 标题
        title = ''
        tm = re.search(r'<h3[^>]*>(.*?)</h3>', detail_html, re.DOTALL)
        if tm:
            title = self._clean(tm.group(1))
        if not title:
            tm = re.search(r'<title>([^<]+)', detail_html)
            if tm:
                title = self._clean(re.sub(r'\s*[-–—|].*$', '', tm.group(1)))

        # 图片
        pic = ''
        pm = re.search(r'data-src="([^"]+)"', detail_html)
        if not pm:
            pm = re.search(r'src="(https?://[^"]+\.(?:jpg|webp|png)[^"]*)"', detail_html)
        if pm:
            pic = pm.group(1).replace('&amp;', '&')

        # 导演
        director = ''
        dm = re.search(r'导演[：:]\s*(.*?)(?:</p>|</div>|<br)', detail_html)
        if dm:
            director = self._clean(dm.group(1))

        # 主演
        actor = ''
        am = re.search(r'主演[：:]\s*(.*?)(?:</p>|</div>|<br)', detail_html)
        if am:
            actor = self._clean(am.group(1))

        # 类型
        type_name = ''
        tym = re.search(r'类型[：:]\s*(.*?)(?:</p>|</div>|<br)', detail_html)
        if tym:
            type_name = self._clean(tym.group(1))

        # 地区
        area = ''
        arm = re.search(r'地区[：:]\s*(.*?)(?:</p>|</div>|<br)', detail_html)
        if arm:
            area = self._clean(arm.group(1))

        # 年份
        year = ''
        ym = re.search(r'年份[：:]\s*(\d{4})', detail_html)
        if ym:
            year = ym.group(1)

        # 简介
        desc = ''
        d_block = re.search(r'简介[：:]\s*(.*?)(?:</div>|</p>)', detail_html, re.DOTALL)
        if d_block:
            desc = self._clean(d_block.group(1))
        if not desc:
            dm = re.search(r'name="description"\s*content="([^"]+)"', detail_html)
            if dm:
                desc = dm.group(1)

        # 备注
        remarks = ''
        rm = re.search(r'(?:更新|连载)[：:]\s*(.*?)(?:</p>|</div>|<br)', detail_html)
        if rm:
            remarks = self._clean(rm.group(1))

        # ---- 提取线路名称（按HTML中的顺序，保持全部）----
        tab_names = []
        for sm in re.finditer(r'<a[^>]*swiper-slide[^>]*>(.*?)</a>', detail_html, re.DOTALL):
            inner = sm.group(1)
            # 提取名称：&nbsp;至臻4k<span class="badge">(15)</span>
            name_match = re.search(r'&nbsp;([^<]+)', inner)
            if name_match:
                name = name_match.group(1).strip()
                if name:
                    tab_names.append(name)

        # ---- 提取播放列表（按HTML中的顺序，与tab顺序对应）----
        play_from = []
        play_url = []

        box_matches = re.finditer(
            r'<div class="anthology-list-box[^"]*"[^>]*>(.*?)</div>\s*</div>',
            detail_html, re.DOTALL
        )

        for box_idx, box_match in enumerate(box_matches):
            box_html = box_match.group(1)

            # 从第一个链接获取 sid
            sid_match = re.search(r'href="/play/\d+-(\d+)-\d+\.html"', box_html)
            if not sid_match:
                continue
            sid = sid_match.group(1)

            # 提取该box下的所有集数
            episodes = []
            for em in re.finditer(r'href="/play/\d+-' + sid + r'-(\d+)\.html"[^>]*>(.*?)</a>', box_html):
                nid = int(em.group(1))
                label = self._clean(em.group(2))
                if not label or label.strip() == '' or label.isdigit():
                    label = f'第{nid:02d}集'
                episodes.append((nid, label))

            if not episodes:
                continue

            episodes.sort(key=lambda x: x[0])

            line_name = tab_names[box_idx] if box_idx < len(tab_names) else f'线路{sid}'
            ep_list = [f'{label}${vid}|{sid}|{nid}' for nid, label in episodes]

            play_from.append(line_name)
            play_url.append('#'.join(ep_list))

        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': year,
            'vod_area': area,
            'vod_remarks': remarks,
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': desc,
            'vod_play_from': '$$$'.join(play_from) if play_from else '',
            'vod_play_url': '$$$'.join(play_url) if play_url else ''
        }
        result['list'].append(vod)
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        try:
            parts = id.split('|')
            if len(parts) >= 3:
                vod_id = parts[0]
                sid = parts[1]
                nid = parts[2]

                play_url = f'{self.site}/play/{vod_id}-{sid}-{nid}.html'
                html = self._get(play_url, referer=self.site)
                if not html:
                    return {'parse': 1, 'url': '', 'jx': 0, 'header': self.play_headers}

                # 修复：player_aaaa 后面没有分号，直接是 </script>
                pm = re.search(r'var player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.DOTALL)
                if not pm:
                    return {'parse': 1, 'url': play_url, 'jx': 0, 'header': self.play_headers}

                try:
                    player_data = json.loads(pm.group(1))
                except:
                    return {'parse': 1, 'url': play_url, 'jx': 0, 'header': self.play_headers}

                video_url = player_data.get('url', '')
                from_key = player_data.get('from', '')
                encrypt = player_data.get('encrypt', 0)

                # 处理加密
                if encrypt == 1:
                    video_url = requests.utils.unquote(video_url)
                elif encrypt == 2:
                    import base64
                    try:
                        video_url = requests.utils.unquote(base64.b64decode(video_url).decode('utf-8'))
                    except:
                        pass

                if not video_url:
                    return {'parse': 1, 'url': play_url, 'jx': 0, 'header': self.play_headers}

                parser_cfg = self.parser_config.get(from_key, {})

                if parser_cfg.get('ps') == '1' and parser_cfg.get('parse'):
                    # 解析器线路
                    parser_url = parser_cfg['parse']
                    real_url = self._resolve_video_url(video_url, parser_url)
                    if real_url:
                        best_url = self._pick_best_quality(real_url, parser_url)
                        return {
                            'parse': 0, 'url': best_url, 'jx': 0,
                            'header': dict(self.play_headers, **{'Referer': parser_url})
                        }
                    return {'parse': 1, 'url': play_url, 'jx': 0, 'header': self.play_headers}

                elif parser_cfg.get('ps') == '0' or not parser_cfg:
                    # 自营线路
                    if video_url.startswith('http'):
                        if '.m3u8' in video_url:
                            best_url = self._pick_best_quality(video_url, self.site + '/')
                            return {
                                'parse': 0, 'url': best_url, 'jx': 0,
                                'header': dict(self.play_headers, **{'Referer': self.site + '/'})
                            }
                        return {
                            'parse': 0, 'url': video_url, 'jx': 0,
                            'header': dict(self.play_headers, **{'Referer': self.site + '/'})
                        }

                # 兜底：根据URL格式自动判断解析器
                if video_url.startswith('JD-'):
                    real_url = self._resolve_video_url(video_url, 'https://fgsrg.hzqingshan.com/player/?url=')
                    if real_url:
                        best_url = self._pick_best_quality(real_url, 'https://fgsrg.hzqingshan.com/')
                        return {
                            'parse': 0, 'url': best_url, 'jx': 0,
                            'header': dict(self.play_headers, **{'Referer': 'https://fgsrg.hzqingshan.com/'})
                        }
                elif video_url.startswith('co_') or video_url.startswith('knmb-'):
                    real_url = self._resolve_video_url(video_url, 'https://zsmyyrv.hzqingshan.com/player/?url=')
                    if real_url:
                        best_url = self._pick_best_quality(real_url, 'https://zsmyyrv.hzqingshan.com/')
                        return {
                            'parse': 0, 'url': best_url, 'jx': 0,
                            'header': dict(self.play_headers, **{'Referer': 'https://zsmyyrv.hzqingshan.com/'})
                        }

                return {'parse': 1, 'url': play_url, 'jx': 0, 'header': self.play_headers}
            else:
                return {'parse': 1, 'url': '', 'jx': 0, 'header': self.play_headers}
        except Exception as e:
            print(f'playerContent error: {e}')
            return {'parse': 1, 'url': '', 'jx': 0, 'header': self.play_headers}

    def searchContent(self, key, quick, pg='1'):
        result = {'list': [], 'parse': 0, 'jx': 0}
        wd = requests.utils.quote(key)
        url = f'{self.site}/cupfox-search/-------------.html?wd={wd}'
        # 搜索前重置session，避免上一次验证码的cookie干扰结果
        self.session = requests.Session()
        self.session.headers.update(self.base_headers)
        html = self._bypass_captcha(url, referer=self.site, max_attempts=20)
        if html and '系统安全验证' not in html and key in html:
            result['list'] = self._extract_list(html)
        return result

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]