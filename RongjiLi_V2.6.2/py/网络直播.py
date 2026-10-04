# -*- coding: utf-8 -*-

import json
import re
import sys
import time
import hashlib
import random
import math
import urllib.parse
from base64 import b64decode, b64encode
from urllib.parse import parse_qs
import requests
from pyquery import PyQuery as pq

sys.path.append("..")
from base.spider import Spider
from concurrent.futures import ThreadPoolExecutor

# ==================== 抖音 a_bogus 签名算法（移植自社区开源方案） ====================


def _dy_rc4_encrypt(plaintext, key):
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + ord(key[i % len(key)])) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    result = []
    for char in plaintext:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        t = (s[i] + s[j]) % 256
        result.append(chr(s[t] ^ ord(char)))
    return "".join(result)


def _dy_left_rotate(x, n):
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _dy_get_t_j(j):
    if 0 <= j < 16:
        return 2043430169
    return 2055708042


def _dy_ff_j(j, x, y, z):
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    return ((x & y) | (x & z) | (y & z)) & 0xFFFFFFFF


def _dy_gg_j(j, x, y, z):
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    return ((x & y) | (~x & z)) & 0xFFFFFFFF


class _DySM3(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.reg = [
            1937774191,
            1226093241,
            388252375,
            3666478592,
            2842636476,
            372324522,
            3817729613,
            2969243214,
        ]
        self.chunk = []
        self.size = 0

    def write(self, data):
        a = list(data.encode("utf-8")) if isinstance(data, str) else data
        self.size += len(a)
        f = 64 - len(self.chunk)
        if len(a) < f:
            self.chunk.extend(a)
        else:
            self.chunk.extend(a[:f])
            while len(self.chunk) >= 64:
                self._compress(self.chunk)
                if f < len(a):
                    self.chunk = a[f : min(f + 64, len(a))]
                else:
                    self.chunk = []
                f += 64

    def _fill(self):
        bit_length = 8 * self.size
        padding_pos = len(self.chunk)
        self.chunk.append(0x80)
        padding_pos = (padding_pos + 1) % 64
        if 64 - padding_pos < 8:
            padding_pos -= 64
        while padding_pos < 56:
            self.chunk.append(0)
            padding_pos += 1
        high_bits = bit_length // 4294967296
        for i in range(4):
            self.chunk.append((high_bits >> (8 * (3 - i))) & 0xFF)
        for i in range(4):
            self.chunk.append((bit_length >> (8 * (3 - i))) & 0xFF)

    def _compress(self, data):
        w = [0] * 132
        for t in range(16):
            w[t] = (
                (data[4 * t] << 24)
                | (data[4 * t + 1] << 16)
                | (data[4 * t + 2] << 8)
                | data[4 * t + 3]
            )
            w[t] &= 0xFFFFFFFF
        for j in range(16, 68):
            a = w[j - 16] ^ w[j - 9] ^ _dy_left_rotate(w[j - 3], 15)
            a = a ^ _dy_left_rotate(a, 15) ^ _dy_left_rotate(a, 23)
            w[j] = (a ^ _dy_left_rotate(w[j - 13], 7) ^ w[j - 6]) & 0xFFFFFFFF
        for j in range(64):
            w[j + 68] = (w[j] ^ w[j + 4]) & 0xFFFFFFFF
        a, b, c, d, e, f, g, h = self.reg
        for j in range(64):
            ss1 = _dy_left_rotate(
                (_dy_left_rotate(a, 12) + e + _dy_left_rotate(_dy_get_t_j(j), j))
                & 0xFFFFFFFF,
                7,
            )
            ss2 = ss1 ^ _dy_left_rotate(a, 12)
            tt1 = (_dy_ff_j(j, a, b, c) + d + ss2 + w[j + 68]) & 0xFFFFFFFF
            tt2 = (_dy_gg_j(j, e, f, g) + h + ss1 + w[j]) & 0xFFFFFFFF
            d = c
            c = _dy_left_rotate(b, 9)
            b = a
            a = tt1
            h = g
            g = _dy_left_rotate(f, 19)
            f = e
            e = (tt2 ^ _dy_left_rotate(tt2, 9) ^ _dy_left_rotate(tt2, 17)) & 0xFFFFFFFF
        self.reg[0] ^= a
        self.reg[1] ^= b
        self.reg[2] ^= c
        self.reg[3] ^= d
        self.reg[4] ^= e
        self.reg[5] ^= f
        self.reg[6] ^= g
        self.reg[7] ^= h

    def sum(self, data=None):
        if data is not None:
            self.reset()
            self.write(data)
        self._fill()
        for f in range(0, len(self.chunk), 64):
            self._compress(self.chunk[f : f + 64])
        result = []
        for f in range(8):
            c = self.reg[f]
            result.extend(
                [(c >> 24) & 0xFF, (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF]
            )
        self.reset()
        return result


def _dy_get_long_int(round_num, long_str):
    round_num *= 3
    c1 = ord(long_str[round_num]) if round_num < len(long_str) else 0
    c2 = ord(long_str[round_num + 1]) if round_num + 1 < len(long_str) else 0
    c3 = ord(long_str[round_num + 2]) if round_num + 2 < len(long_str) else 0
    return (c1 << 16) | (c2 << 8) | c3


def _dy_result_encrypt(long_str, num):
    encoding_tables = {
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe",
    }
    masks = [16515072, 258048, 4032, 63]
    shifts = [18, 12, 6, 0]
    encoding_table = encoding_tables[num]
    result = ""
    round_num = 0
    long_int = _dy_get_long_int(round_num, long_str)
    total_chars = int(math.ceil(len(long_str) / 3.0 * 4))
    for i in range(total_chars):
        if i // 4 != round_num:
            round_num += 1
            long_int = _dy_get_long_int(round_num, long_str)
        index = i % 4
        char_index = (long_int & masks[index]) >> shifts[index]
        result += encoding_table[char_index]
    return result


def _dy_gener_random(random_num, option):
    byte1 = random_num & 255
    byte2 = (random_num >> 8) & 255
    return [
        (byte1 & 170) | (option[0] & 85),
        (byte1 & 85) | (option[0] & 170),
        (byte2 & 170) | (option[1] & 85),
        (byte2 & 85) | (option[1] & 170),
    ]


def _dy_generate_random_str():
    random_values = [0.123456789, 0.987654321, 0.555555555]
    random_bytes = []
    random_bytes.extend(_dy_gener_random(int(random_values[0] * 10000), [3, 45]))
    random_bytes.extend(_dy_gener_random(int(random_values[1] * 10000), [1, 0]))
    random_bytes.extend(_dy_gener_random(int(random_values[2] * 10000), [1, 5]))
    return "".join(chr(b) for b in random_bytes)


def _dy_generate_rc4_bb_str(
    url_search_params, user_agent, window_env_str, suffix="cus", arguments=None
):
    if arguments is None:
        arguments = [0, 1, 14]
    sm3 = _DySM3()
    start_time = int(time.time() * 1000)
    url_search_params_list = sm3.sum(sm3.sum(url_search_params + suffix))
    cus = sm3.sum(sm3.sum(suffix))
    ua_key = chr(0) + chr(1) + chr(14)
    ua = sm3.sum(_dy_result_encrypt(_dy_rc4_encrypt(user_agent, ua_key), "s3"))
    end_time = start_time + 100
    b = {
        8: 3,
        10: end_time,
        16: start_time,
        18: 44,
        19: [1, 0, 1, 5],
        15: {"aid": 6383, "pageId": 110624},
    }

    def split_to_bytes(num):
        return [(num >> 24) & 255, (num >> 16) & 255, (num >> 8) & 255, num & 255]

    start_time_bytes = split_to_bytes(b[16])
    b[20], b[21], b[22], b[23] = start_time_bytes
    b[24] = int(b[16] / 256 / 256 / 256 / 256) & 255
    b[25] = int(b[16] / 256 / 256 / 256 / 256 / 256) & 255
    arg0_bytes = split_to_bytes(arguments[0])
    b[26], b[27], b[28], b[29] = arg0_bytes
    b[30] = int(arguments[1] / 256) & 255
    b[31] = (arguments[1] % 256) & 255
    arg1_bytes = split_to_bytes(arguments[1])
    b[32] = arg1_bytes[0]
    b[33] = arg1_bytes[1]
    arg2_bytes = split_to_bytes(arguments[2])
    b[34], b[35], b[36], b[37] = arg2_bytes
    b[38] = url_search_params_list[21]
    b[39] = url_search_params_list[22]
    b[40] = cus[21]
    b[41] = cus[22]
    b[42] = ua[23]
    b[43] = ua[24]
    end_time_bytes = split_to_bytes(b[10])
    b[44], b[45], b[46], b[47] = end_time_bytes
    b[48] = b[8]
    b[49] = int(b[10] / 256 / 256 / 256 / 256) & 255
    b[50] = int(b[10] / 256 / 256 / 256 / 256 / 256) & 255
    b[51] = b[15]["pageId"]
    page_id_bytes = split_to_bytes(b[15]["pageId"])
    b[52], b[53], b[54], b[55] = page_id_bytes
    b[56] = b[15]["aid"]
    b[57] = b[15]["aid"] & 255
    b[58] = (b[15]["aid"] >> 8) & 255
    b[59] = (b[15]["aid"] >> 16) & 255
    b[60] = (b[15]["aid"] >> 24) & 255
    window_env_list = [ord(char) for char in window_env_str]
    b[64] = len(window_env_list)
    b[65] = b[64] & 255
    b[66] = (b[64] >> 8) & 255
    b[69] = 0
    b[70] = 0
    b[71] = 0
    b[72] = (
        b[18]
        ^ b[20]
        ^ b[26]
        ^ b[30]
        ^ b[38]
        ^ b[40]
        ^ b[42]
        ^ b[21]
        ^ b[27]
        ^ b[31]
        ^ b[35]
        ^ b[39]
        ^ b[41]
        ^ b[43]
        ^ b[22]
        ^ b[28]
        ^ b[32]
        ^ b[36]
        ^ b[23]
        ^ b[29]
        ^ b[33]
        ^ b[37]
        ^ b[44]
        ^ b[45]
        ^ b[46]
        ^ b[47]
        ^ b[48]
        ^ b[49]
        ^ b[50]
        ^ b[24]
        ^ b[25]
        ^ b[52]
        ^ b[53]
        ^ b[54]
        ^ b[55]
        ^ b[57]
        ^ b[58]
        ^ b[59]
        ^ b[60]
        ^ b[65]
        ^ b[66]
        ^ b[70]
        ^ b[71]
    )
    bb = [
        b[18],
        b[20],
        b[52],
        b[26],
        b[30],
        b[34],
        b[58],
        b[38],
        b[40],
        b[53],
        b[42],
        b[21],
        b[27],
        b[54],
        b[55],
        b[31],
        b[35],
        b[57],
        b[39],
        b[41],
        b[43],
        b[22],
        b[28],
        b[32],
        b[60],
        b[36],
        b[23],
        b[29],
        b[33],
        b[37],
        b[44],
        b[45],
        b[59],
        b[46],
        b[47],
        b[48],
        b[49],
        b[50],
        b[24],
        b[25],
        b[65],
        b[66],
        b[70],
        b[71],
    ]
    bb.extend(window_env_list)
    bb.append(b[72])
    return _dy_rc4_encrypt("".join(chr(byte) for byte in bb), chr(121))


def _dy_ab_sign(url_search_params, user_agent):
    window_env_str = "1920|1080|1920|1040|0|30|0|0|1872|92|1920|1040|1857|92|1|24|Win32"
    return (
        _dy_result_encrypt(
            _dy_generate_random_str()
            + _dy_generate_rc4_bb_str(url_search_params, user_agent, window_env_str),
            "s4",
        )
        + "="
    )


class Spider(Spider):

    # B站登录cookie（选填）：网页登录 bilibili.com 后从浏览器Cookie里复制 SESSDATA 的值填到引号内，
    # 即可解锁B站直播原画/4K；留空则使用游客身份（B站限制游客最高720P）
    BILI_SESSDATA = ""

    def init(self, extend=""):
        pass

    def getName(self):
        return "直播"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    headerx = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    }

    headers = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
        },
        {"User-Agent": "Dart/3.4 (dart:io)"},
    ]

    excepturl = "https://www.baidu.com"

    hosts = {
        "huya": ["https://www.huya.com", "https://mp.huya.com"],
        "douyu": "https://www.douyu.com",
        "wangyi": "https://cc.163.com",
        "bili": "https://api.live.bilibili.com",
        "douyin": "https://live.douyin.com",
    }

    referers = {
        "huya": "https://live.cdn.huya.com",
        "douyu": "https://m.douyu.com",
        "bili": "https://live.bilibili.com",
        "douyin": "https://live.douyin.com",
    }

    playheaders = {
        "wangyi": {
            "User-Agent": "ExoPlayer",
            "Connection": "Keep-Alive",
            "Icy-MetaData": "1",
        },
        "bili": {
            "Accept": "*/*",
            "Icy-MetaData": "1",
            "referer": "https://live.bilibili.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        },
        "huya": {
            "User-Agent": "ExoPlayer",
            "Connection": "Keep-Alive",
            "Icy-MetaData": "1",
        },
        "douyu": {
            # v6修复：改为斗鱼官方Web播放器UA（与getH5PlayV1接口请求UA一致，token=web-h5配套），
            # 并带 m.douyu.com Referer，规避CDN对非浏览器UA的防盗链校验
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
            "Referer": "https://m.douyu.com/",
            "Connection": "Keep-Alive",
        },
        "douyin": {
            "User-Agent": "ExoPlayer",
            "referer": "https://live.douyin.com/",
            "Connection": "Keep-Alive",
        },
    }

    def homeContent(self, filter):
        result = {}
        cateManual = {
            "虎牙": "huya",
            "斗鱼": "douyu",
            "B站": "bili",
            "网易": "wangyi",
            "抖音": "douyin",
        }
        classes = []
        filters = {
            "huya": [
                {
                    "key": "cate",
                    "name": "分类",
                    "value": [
                        {"n": "网游", "v": "1"},
                        {"n": "单机", "v": "2"},
                        {"n": "娱乐", "v": "8"},
                        {"n": "手游", "v": "3"},
                    ],
                }
            ],
            "douyin": [
                {
                    "key": "cate",
                    "name": "分类",
                    "value": [{"n": n, "v": v} for v, n in self._DY_CATES],
                }
            ],
        }

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self.process_douyu): "douyu",
                executor.submit(self.process_bili): "bili",
            }
            for future in futures:
                try:
                    platform, filter_data = future.result()
                    if filter_data:
                        filters[platform] = filter_data
                except Exception as e:
                    print(f"filters加载失败: {e}")

        for k in cateManual:
            classes.append({"type_name": k, "type_id": cateManual[k]})

        result["class"] = classes
        result["filters"] = filters
        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        vdata = []
        result = {}
        pagecount = 9999
        result["page"] = pg
        result["limit"] = 90
        result["total"] = 999999
        if tid == "wangyi":
            vdata, pagecount = self.wyccContent(tid, pg, filter, extend, vdata)
        elif tid == "bili":
            vdata, pagecount = self.biliContent(tid, pg, filter, extend, vdata)
        elif tid == "douyin":
            vdata, pagecount = self.douyinContent(tid, pg, filter, extend, vdata)
        elif "huya" in tid:
            vdata, pagecount = self.huyaContent(tid, pg, filter, extend, vdata)
        elif "douyu" in tid:
            vdata, pagecount = self.douyuContent(tid, pg, filter, extend, vdata)
        result["list"] = vdata
        result["pagecount"] = pagecount
        return result

    def wyccContent(self, tid, pg, filter, extend, vdata):
        params = {
            "format": "json",
            "start": (int(pg) - 1) * 20,
            "size": "20",
        }
        response = self.fetch(
            f"{self.hosts[tid]}/api/category/live/",
            params=params,
            headers=self.headers[0],
        ).json()
        for i in response["lives"]:
            if i.get("cuteid"):
                bvdata = self.buildvod(
                    vod_id=f"{tid}@@{i['cuteid']}",
                    vod_name=i.get("title"),
                    vod_pic=i.get("cover"),
                    vod_remarks=i.get("nickname"),
                    style={"type": "rect", "ratio": 1.33},
                )
                vdata.append(bvdata)
        return vdata, 9999

    def biliContent(self, tid, pg, filter, extend, vdata):
        """B站分类房间列表：Area/getRoomList 老接口（2026 实测可用）"""
        try:
            if extend and extend.get("cate"):
                parent_id, area_id = extend["cate"].split("-")
            else:
                parent_id, area_id = "9", "0"
            url = (
                f"{self.hosts[tid]}/room/v1/Area/getRoomList?parent_id={parent_id}"
                f"&area_id={area_id}&page={pg}&page_size=30&sort_type=online"
            )
            data = self.fetch(url, headers=self.headerx).json()
            if data.get("code") == 0:
                for i in data.get("data", []):
                    vdata.append(
                        self.buildvod(
                            vod_id=f"bili@@{i['roomid']}",
                            vod_name=i.get("title"),
                            vod_pic=i.get("cover").replace("http://", "https://"),
                            vod_remarks=i.get("uname"),
                            vod_year="在线"
                            + str(round(int(i.get("online", 0)) / 10000, 1))
                            + "万",
                            style={"type": "rect", "ratio": 1.33},
                        )
                    )
            return vdata, 9999
        except Exception as e:
            print(f"B站列表错误: {e}")
            return vdata, 1

    def _douyin_partition(self, cate_id, offset=0):
        """分类房间列表：amemv 移动网关 partition API（web 域被拒444，网关畅通）
        返回按人气降序的房间，room.id_str 为 reflow room_id"""
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "116.0.0.0",
            "partition": str(cate_id),
            "partition_type": "1",
            "req_from": "2",
            "count": "15",
            "offset": str(offset),
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "msToken": "",
        }
        api = (
            "https://webcast.amemv.com/webcast/web/partition/detail/room/?"
            + urllib.parse.urlencode(params)
        )
        j = self._douyin_api_get(api, "https://live.douyin.com/")
        data = j.get("data") or {}
        return data.get("data") or []

    def douyinContent(self, tid, pg, filter, extend, vdata):
        """抖音分类房间列表：partition API 按分类返回在播房间（客户端按观看人数降序）
        未选筛选时默认展示推荐(720)；extend['cate']含逗号则为旧版手动房间号列表"""
        cate = (extend.get("cate") or "").strip() if extend else ""
        if "," in cate:
            # 手动房间号列表（旧版兼容）
            for rid in [r.strip() for r in cate.split(",") if r.strip().isdigit()]:
                vdata.append(
                    self.buildvod(
                        vod_id=f"douyin@@{rid}",
                        vod_name=f"抖音直播间 {rid}",
                        vod_remarks="点击进入直播间",
                        style={"type": "rect", "ratio": 1.33},
                    )
                )
            return vdata, 1
        if not cate:
            # 未选分类：使用推荐流
            cate = "720"
        try:
            rooms = self._douyin_partition(cate, offset=(int(pg) - 1) * 15)

            # 一级娱乐分类：添加标签提示（API不保证精准分类，需用户自行判断）
            if cate in self._ENTERTAINMENT_TAG_MAP:
                # 标记这些房间为"娱乐分类"
                pass

            def _cnt_item(it):
                # user_count_str=当前在线人数(支持 "8000+"/"4w+"/"1.2亿+")，display_value 是累计观看不能用于排序
                s = (
                    str((it.get("room") or {}).get("user_count_str") or "")
                    .replace("+", "")
                    .strip()
                )
                try:
                    if s.endswith("w"):
                        return int(float(s[:-1]) * 10000)
                    if s.endswith("亿"):
                        return int(float(s[:-1]) * 100000000)
                    return int(s or 0)
                except Exception:
                    return 0

            rooms = sorted(rooms, key=_cnt_item, reverse=True)
            seen = set()
            for it in rooms:
                room = it.get("room") or {}
                rid = room.get("id_str")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                owner = room.get("owner") or {}
                web_rid = it.get("web_rid") or ""
                # 娱乐分类添加标签提示
                category_hint = ""
                if cate in self._ENTERTAINMENT_TAG_MAP:
                    category_hint = f"[{self._DY_CATES_DICT.get(cate, cate)}]"
                vdata.append(
                    self.buildvod(
                        vod_id=(
                            f"douyin@@r{rid}@{web_rid}"
                            if web_rid
                            else f"douyin@@r{rid}"
                        ),
                        vod_name=room.get("title") or "抖音直播间",
                        vod_pic=self._douyin_cover(room),
                        vod_remarks=f"{owner.get('nickname', '')} {room.get('user_count_str', '')}".strip()
                        or "点击进入",
                        style={"type": "rect", "ratio": 1.33},
                    )
                )
            if pg == "1":
                # 用法说明放列表末尾
                vdata.append(
                    self.buildvod(
                        vod_id="douyin@@help",
                        vod_name="🔍 搜索抖音直播间方法(点看说明)",
                        vod_remarks="分享链接/房间号均可",
                        vod_content=(
                            "抖音直播支持以下观看方式：\n\n"
                            "★ 方式一(最简单)：手机抖音打开直播间 → 分享 → 复制链接，"
                            "进入本源点击右上角放大镜(搜索)，把复制的内容整段粘贴进去搜索，"
                            "点搜索结果即可播放\n\n"
                            "★ 方式二：搜索框直接输入网页版直播间号"
                            "(live.douyin.com/后面的数字)\n\n"
                            "★ 方式三：把主播主页链接"
                            "(douyin.com/user/xxx)粘贴到搜索框搜索\n\n"
                            "★ 列表房间均按观看人数从高到低排序"
                        ),
                        style={"type": "rect", "ratio": 1.33},
                    )
                )
            return vdata, 9999
        except Exception as e:
            print(f"抖音列表错误: {e}")
            return vdata, 1

    @staticmethod
    def _douyin_cover(room):
        """提取房间封面图"""
        try:
            urls = (room.get("cover") or {}).get("url_list") or []
            for u in urls:
                if u.startswith("http"):
                    return u
        except Exception:
            pass
        return ""

    def huyaContent(self, tid, pg, filter, extend, vdata):
        if extend.get("cate") and pg == "1" and "click" not in tid:
            id = extend.get("cate")
            data = self.fetch(
                f"{self.referers[tid]}/liveconfig/game/bussLive?bussType={id}",
                headers=self.headers[1],
            ).json()
            for i in data["data"]:
                v = self.buildvod(
                    vod_id=f"click_{tid}@@{int(i['gid'])}",
                    vod_name=i.get("gameFullName"),
                    vod_pic=f'https://huyaimg.msstatic.com/cdnimage/game/{int(i["gid"])}-MS.jpg',
                    vod_tag=1,
                    style={"type": "oval", "ratio": 1},
                )
                vdata.append(v)
            return vdata, 1
        else:
            gid = ""
            if "click" in tid:
                ids = tid.split("_")[1].split("@@")
                tid = ids[0]
                gid = f"&gameId={ids[1]}"
            data = self.fetch(
                f"{self.hosts[tid][0]}/cache.php?m=LiveList&do=getLiveListByPage&tagAll=0{gid}&page={pg}",
                headers=self.headers[1],
            ).json()
            for i in data["data"]["datas"]:
                if i.get("profileRoom"):
                    v = self.buildvod(
                        f"{tid}@@{i['profileRoom']}",
                        i.get("introduction"),
                        i.get("screenshot"),
                        str(int(i.get("totalCount", "1")) / 10000) + "万",
                        0,
                        i.get("nick"),
                        style={"type": "rect", "ratio": 1.33},
                    )
                    vdata.append(v)
            return vdata, 9999

    def douyuContent(self, tid, pg, filter, extend, vdata):
        if extend.get("cate") and pg == "1" and "click" not in tid:
            for i in self.dyufdata["data"]["cate2Info"]:
                if str(i["cate1Id"]) == extend["cate"]:
                    v = self.buildvod(
                        vod_id=f"click_{tid}@@{i['cate2Id']}",
                        vod_name=i.get("cate2Name"),
                        vod_pic=i.get("icon"),
                        vod_remarks=i.get("count"),
                        vod_tag=1,
                        style={"type": "oval", "ratio": 1},
                    )
                    vdata.append(v)
            return vdata, 1
        else:
            path = f"/japi/weblist/apinc/allpage/6/{pg}"
            if "click" in tid:
                ids = tid.split("_")[1].split("@@")
                tid = ids[0]
                path = f"/gapi/rkc/directory/mixList/2_{ids[1]}/{pg}"
            url = f"{self.hosts[tid]}{path}"
            data = self.fetch(url, headers=self.headers[1]).json()
            for i in data["data"]["rl"]:
                v = self.buildvod(
                    vod_id=f"{tid}@@{i['rid']}",
                    vod_name=i.get("rn"),
                    vod_pic=i.get("rs16"),
                    vod_year=str(int(i.get("ol", 1)) / 10000) + "万",
                    vod_remarks=i.get("nn"),
                    style={"type": "rect", "ratio": 1.33},
                )
                vdata.append(v)
            return vdata, 9999

    def detailContent(self, ids):
        ids_split = ids[0].split("@@")
        if ids_split[0] == "wangyi":
            vod = self.wyccDetail(ids_split)
        elif ids_split[0] == "bili":
            vod = self.biliDetail(ids_split)
        elif ids_split[0] == "huya":
            vod = self.huyaDetail(ids_split)
        elif ids_split[0] == "douyu":
            vod = self.douyuDetail(ids_split)
        elif ids_split[0] == "douyin":
            vod = self.douyinDetail(ids_split)
        return {"list": [vod]}

    def wyccDetail(self, ids):
        """网易CC详情：新结构直接取 live.m3u8"""
        try:
            vdata = (
                self.getpq(f"{self.hosts[ids[0]]}/{ids[1]}/", self.headers[0])("script")
                .eq(-1)
                .text()
            )
            data = json.loads(vdata)["props"]["pageProps"]["roomInfoInitData"]
            live = data.get("live", {})
            m3u8 = live.get("m3u8") or live.get("sharefile") or ""
            if not m3u8.startswith("http"):
                return self.handle_exception(Exception("未获取到播放地址"))
            name = live.get("title", "网易CC直播")
            vod = self.buildvod(
                vod_name=name,
                vod_remarks=live.get("gamename", ""),
                vod_content=data.get("description_suffix", name),
                vod_pic=live.get("poster", live.get("cover", "")),
            )
            vod["vod_play_from"] = "网易CC"
            vod["vod_play_url"] = (
                f"{name}${ids[0]}@@{self.e64(json.dumps(['高清', m3u8]))}"
            )
            return vod
        except Exception as e:
            return self.handle_exception(e)

    def biliDetail(self, ids):
        """B站详情：playUrl老接口拿原画原始流(游客可用) + getRoomPlayInfo拿720P转码流
        填入 BILI_SESSDATA 后转码流档位可解锁更高"""
        try:
            did = ids[1]
            req_headers = dict(self.headerx)
            if self.BILI_SESSDATA:
                req_headers["Cookie"] = f"SESSDATA={self.BILI_SESSDATA}"

            # 房间信息（标题/主播），失败不阻塞播放
            name = f"B站直播间 {did}"
            remark = ""
            try:
                info = self.fetch(
                    f'{self.hosts["bili"]}/xlive/web-room/v1/index/getInfoByRoom?room_id={did}',
                    headers=req_headers,
                ).json()
                if info.get("code") == 0:
                    ri = info["data"]["room_info"]
                    name = ri.get("title", name)
                    remark = info["data"]["anchor_info"]["base_info"].get("uname", "")
            except Exception:
                pass

            qualities = []
            seen_stream = set()

            # 档1：playUrl 老接口（ptype=8），主播开原始流时返回原画1080P（游客可用）
            try:
                r1 = self.fetch(
                    f'{self.hosts["bili"]}/room/v1/Room/playUrl'
                    f"?cid={did}&qn=10000&platform=web&https_url_req=0&ptype=8&protocol=0,1&format=0,1&codec=0",
                    headers=req_headers,
                ).json()
                if r1.get("code") == 0 and r1.get("data", {}).get("durl"):
                    urls = [d["url"] for d in r1["data"]["durl"] if d.get("url")]
                    # 优选 cn-gotcha CDN（社区验证的稳定线路，排前）
                    urls.sort(key=lambda u: "d1--cn-gotcha" not in u)
                    m = re.search(r"(live_[^/?]+?)\.flv", urls[0])
                    stream_key = m.group(1) if m else ""
                    # 流名无码率后缀=原始流(原画)；有后缀按码率标注
                    if stream_key and re.search(r"_\d{3,4}$", stream_key):
                        bit = int(re.search(r"_(\d{3,4})$", stream_key).group(1))
                        qname = {
                            8000: "蓝光8M",
                            4000: "蓝光4M",
                            2500: "超清720P",
                            1500: "高清",
                        }.get(bit, f"{bit}kbps")
                    else:
                        qname = "原画"
                    for u in urls[:3]:
                        if self._probe_stream(u, self.playheaders["bili"]):
                            qualities.extend([qname, u])
                            seen_stream.add(stream_key)
                            break
            except Exception:
                pass

            # 档2：getRoomPlayInfo 转码流（与档1流名不同才加入）
            try:
                r2 = self.fetch(
                    f'{self.hosts["bili"]}/xlive/web-room/v2/index/getRoomPlayInfo'
                    f"?room_id={did}&platform=web&protocol=0,1&format=0,1,2&codec=0,1&qn=10000",
                    headers=req_headers,
                ).json()
                if r2.get("code") == 0 and r2.get("data", {}).get("playurl_info"):
                    streams = r2["data"]["playurl_info"]["playurl"]["stream"]
                    candidates = []
                    for st in streams:
                        proto = st.get("protocol_name", "")
                        if proto != "http_stream" and candidates:
                            break
                        for fmt in st.get("format", []):
                            for codec in fmt.get("codec", []):
                                base_url = codec.get("base_url", "")
                                for ui in codec.get("url_info", []):
                                    play_url = (
                                        ui.get("host", "")
                                        + base_url
                                        + ui.get("extra", "")
                                    )
                                    if play_url.startswith("http"):
                                        candidates.append(play_url)
                                if candidates:
                                    break
                            if candidates:
                                break
                        if candidates and proto == "http_stream":
                            break
                    m = (
                        re.search(r"(live_[^/?]+?)\.flv", candidates[0])
                        if candidates
                        else None
                    )
                    stream_key = m.group(1) if m else ""
                    if stream_key and stream_key not in seen_stream:
                        for u in candidates[:3]:
                            if self._probe_stream(u, self.playheaders["bili"]):
                                qualities.extend(["备选线路", u])
                                break
            except Exception:
                pass

            if not qualities:
                return self.handle_exception(Exception("无可用播放线路"))

            vod = self.buildvod(
                vod_id=f"bili@@{did}",
                vod_name=name,
                vod_remarks=remark,
                vod_content="欢迎观看哔哩直播",
            )
            vod["vod_play_from"] = "哔哩直播"
            vod["vod_play_url"] = f"{name}${ids[0]}@@{self.e64(json.dumps(qualities))}"
            return vod
        except Exception as e:
            print(f"B站详情错误: {e}")
            return self.handle_exception(e)

    @staticmethod
    def _probe_stream(url, headers, timeout=5):
        """轻量探测播放地址可用性（读取首块后立即断开）"""
        try:
            rr = requests.get(url, headers=headers, timeout=timeout, stream=True)
            chunk = next(rr.iter_content(16), b"")
            rr.close()
            return chunk.startswith(b"FLV") or chunk.startswith(b"#EXTM3U")
        except Exception:
            return False

    def huyaDetail(self, ids):
        """虎牙详情：直接使用 profileRoom 返回的 sFlvAntiCode（服务端即时签名）"""
        try:
            room_id = ids[1]
            api_url = f"{self.hosts[ids[0]][1]}/cache.php?m=Live&do=profileRoom&roomid={room_id}"
            data = self.fetch(api_url, headers=self.headers[1]).json()
            if not data or data.get("status") != 200 or not data.get("data"):
                return self.handle_exception(Exception("房间数据为空"))

            room_data = data["data"]
            stream_info = room_data.get("stream", {})
            live_data = room_data.get("liveData", {})
            base_stream_list = stream_info.get("baseSteamInfoList", [])
            if not base_stream_list:
                return self.handle_exception(Exception("无直播流信息"))

            vod = self.buildvod(
                vod_id=ids[0] + "@@" + ids[1],
                vod_name=live_data.get("introduction", "虎牙直播"),
                type_name=live_data.get("gameFullName", ""),
                vod_director=live_data.get("nick", ""),
                vod_remarks=live_data.get("contentIntro", ""),
            )

            # 清晰度列表：iBitRate 为 0 表示原画
            # 2026 结构：rateArray 位于 stream.flv.rateArray（旧版在 stream.rateArray）
            rate_array = (
                stream_info.get("flv", {}).get("rateArray")
                or stream_info.get("rateArray")
                or []
            )
            rates = []
            seen = set()
            for rate in rate_array:
                bit = int(rate.get("iBitRate", 0))
                if bit in seen:
                    continue
                seen.add(bit)
                name = "原画" if bit == 0 else rate.get("sDisplayName", f"{bit}P")
                rates.append({"name": name, "bit": bit})
            if not rates:
                rates = [{"name": "原画", "bit": 0}]
            # 默认档位蓝光4M(4000)优先：原画/蓝光6M高码率在部分网络下会导致ExoPlayer缓冲耗尽断流
            bit_order = {4000: 0, 2000: 1, 500: 2, 6000: 3, 0: 4}
            rates.sort(key=lambda x: (bit_order.get(x["bit"], 5), -x["bit"]))

            # 多 CDN 线路：每条流自带签名好的 antiCode，直接拼接
            # 实测：AL CDN 对转码流(ratio>0)不稳定403，仅保留原画；TX/HS稳定支持全清晰度
            no_transcode_cdns = {"AL"}
            lines = []
            transcode_bits = [r["bit"] for r in rates if r["bit"] > 0]
            for stream in base_stream_list[:4]:
                cdn_type = stream.get("sCdnType", "AL")
                flv_url = stream.get("sFlvUrl", "")
                stream_name = stream.get("sStreamName", "")
                anti_code = stream.get("sFlvAntiCode", "")
                if not (flv_url and stream_name and anti_code):
                    continue
                base_url = f"{flv_url}/{stream_name}.flv?{anti_code}"
                # TX/HW 线路：tars_mp/bhct 参数会触发 CDN 二次校验失败导致断流，
                # 必须替换为 huya_webh5/bgct（社区通用方案）
                if cdn_type in ("TX", "HW"):
                    base_url = base_url.replace(
                        "&ctype=tars_mp", "&ctype=huya_webh5"
                    ).replace("&fs=bhct", "&fs=bgct")
                # AL 固定仅原画，其余 CDN 按实测支持全部清晰度
                transcode_ok = cdn_type not in no_transcode_cdns
                qualities = []
                for rate in rates:
                    if rate["bit"] > 0 and not transcode_ok:
                        continue
                    qualities.extend([rate["name"], f"{base_url}&ratio={rate['bit']}"])
                if not qualities:
                    continue
                lines.append(
                    (
                        transcode_ok,
                        cdn_type,
                        f"{live_data.get('introduction', '直播')}${ids[0]}@@{self.e64(json.dumps(qualities))}",
                    )
                )
                if len(lines) >= 4:
                    break
            lines.sort(key=lambda x: not x[0])
            play_lines = [l[2] for l in lines[:3]]
            line_names = [f"线路{i + 1}({l[1]})" for i, l in enumerate(lines[:3])]

            if not play_lines:
                return self.handle_exception(Exception("无可用线路"))

            vod["vod_play_from"] = "$$$".join(line_names)
            vod["vod_play_url"] = "$$$".join(play_lines)
            return vod
        except Exception as e:
            return self.handle_exception(e)

    # ---------------- 斗鱼：getEncryption + getH5PlayV1 原方案 ----------------

    def douyuDetail(self, ids):
        """斗鱼详情：原方案getEncryption获取密钥，auth签名，getH5PlayV1播放"""
        try:
            channel = ids[1]
            headers = {
                "User-Agent": self.headers[0]["User-Agent"],
                "Referer": f'{self.hosts["douyu"]}/{channel}',
            }

            # 从cookie获取或生成device_id
            try:
                home_res = self.fetch(
                    f'{self.hosts["douyu"]}/{channel}', headers=headers
                )
                cookie_str = home_res.headers.get("Set-Cookie", "")
                did_match = re.search(r"dy_did=([a-f0-9]{32})", cookie_str)
                device_id = (
                    did_match.group(1)
                    if did_match
                    else "".join(random.choice("0123456789abcdef") for _ in range(32))
                )
            except Exception:
                device_id = "".join(
                    random.choice("0123456789abcdef") for _ in range(32)
                )

            betard = self.fetch(
                f'{self.hosts["douyu"]}/betard/{channel}', headers=headers
            ).json()
            room_info = betard.get("room", {})
            vname = room_info.get("room_name", "斗鱼直播")

            # v6新增：主播未开播时直接给出明确提示，
            # 不再白跑一遍签名流程然后报含糊的「翻车啦」(show_status: 1=开播)
            if str(room_info.get("show_status")) != "1":
                vod = self.buildvod(
                    vod_id=ids[0] + "@@" + ids[1],
                    vod_name=vname,
                    vod_remarks="未开播",
                    vod_director=room_info.get("nickname", ""),
                )
                vod["vod_play_from"] = "斗鱼直播"
                vod["vod_play_url"] = (
                    f"未开播${ids[0]}@@{self.e64('#-1')}@@{self.e64(channel)}"
                )
                return vod

            # 获取加密密钥
            sec_url = f'{self.hosts["douyu"]}/wgapi/livenc/liveweb/websec/getEncryption?did={device_id}'
            sec_res = self.fetch(sec_url, headers=headers).json()
            if sec_res.get("error") != 0:
                return self.handle_exception(Exception("获取加密密钥失败"))

            security_data = sec_res["data"]
            secret_key = security_data.get("key")
            random_str = security_data.get("rand_str")
            enc_time = security_data.get("enc_time", 1)
            enc_data = security_data.get("enc_data")

            # 计算签名
            current_time = int(time.time())
            current = random_str
            for _ in range(enc_time):
                current = hashlib.md5(f"{current}{secret_key}".encode()).hexdigest()
            signature = hashlib.md5(
                f"{current}{secret_key}{channel}{current_time}".encode()
            ).hexdigest()

            # 请求播放地址
            play_payload = {
                "enc_data": enc_data,
                "tt": str(current_time),
                "did": device_id,
                "auth": signature,
                "cdn": "",
                "rate": "0",
                "hevc": "0",
                "fa": "0",
                "ive": "0",
            }
            play_api = f'{self.hosts["douyu"]}/lapi/live/getH5PlayV1/{channel}'
            play_headers = headers.copy()
            play_headers["Cookie"] = (
                f"dy_did={device_id}; mantine-color-scheme-value=light"
            )
            play_headers["Content-Type"] = "application/x-www-form-urlencoded"

            play_res = requests.post(
                play_api, data=play_payload, headers=play_headers, timeout=10
            ).json()
            if play_res.get("error") != 0:
                # v6：带上斗鱼返回的错误码与原因，便于区分「未开播/需登录/风控」
                msg = play_res.get("msg") or "未知错误"
                return self.handle_exception(
                    Exception(f"获取播放地址失败({play_res.get('error')}): {msg}")
                )

            stream_info = play_res.get("data", {})
            rtmp_live = stream_info.get("rtmp_live", "")
            if rtmp_live:
                did_match2 = re.search(r"did=([a-f0-9]{32})", rtmp_live)
                if did_match2 and did_match2.group(1) != device_id:
                    device_id = did_match2.group(1)
                    play_payload["did"] = device_id
                    play_res = requests.post(
                        play_api, data=play_payload, headers=play_headers, timeout=10
                    ).json()
                    if play_res.get("error") == 0:
                        stream_info = play_res.get("data", {})

            stream_url = None
            if stream_info.get("rtmp_url") and stream_info.get("rtmp_live"):
                stream_url = f"{stream_info['rtmp_url']}/{stream_info['rtmp_live']}"
            elif stream_info.get("hls_url"):
                stream_url = stream_info["hls_url"]
            if not stream_url:
                return self.handle_exception(Exception("无法获取播放地址"))

            multirates = stream_info.get("multirates", [])
            qualities = []
            if multirates:
                sorted_rates = sorted(
                    multirates, key=lambda x: x.get("bit", 0), reverse=True
                )
                for rate in sorted_rates:
                    bit_rate = rate.get("rate", -1)
                    name = rate.get("name", f"{bit_rate}P")
                    qualities.extend([name, f"#{bit_rate}"])
            else:
                qualities = ["原画", "#-1"]

            session_info = {
                "channel": channel,
                "device_id": device_id,
                "secret_key": secret_key,
                "random_str": random_str,
                "enc_time": enc_time,
                "enc_data": enc_data,
            }
            encoded_session = self.e64(json.dumps(session_info))
            encoded_qualities = self.e64(json.dumps(qualities))
            vod = self.buildvod(
                vod_id=ids[0] + "@@" + ids[1],
                vod_name=vname,
                vod_remarks=room_info.get("second_lvl_name", ""),
                vod_director=room_info.get("nickname", ""),
            )
            vod["vod_play_from"] = "斗鱼直播"
            # v6修复：每个清晰度作为独立的一「集」，集内只携带该清晰度的标记；
            # 播放时才实时生成对应清晰度的全新地址。
            # （旧版把全部清晰度地址一次性生成并塞进同一集，地址会被播放器预连接/测速
            #   消耗掉唯一的「首次连接」配额，导致正式播放只剩 1 秒画面就断流）
            play_items = []
            for i in range(0, len(qualities), 2):
                qname = qualities[i]
                rate_marker = qualities[i + 1]
                # 结构：douyu@@<清晰度标记>@@<房间号>（首段必须是平台标识，供 playerContent 分发）
                play_items.append(
                    f"{qname}$douyu@@{self.e64(rate_marker)}@@{self.e64(channel)}"
                )
            vod["vod_play_url"] = "#".join(play_items)
            return vod
        except Exception as e:
            return self.handle_exception(e)

    def _douyu_get_encryption(self, device_id):
        """获取斗鱼加密密钥（与 did 绑定），失败返回 None"""
        sec_url = f'{self.hosts["douyu"]}/wgapi/livenc/liveweb/websec/getEncryption?did={device_id}'
        headers = {
            "User-Agent": self.headers[0]["User-Agent"],
            "Referer": f'{self.hosts["douyu"]}/',
            "Cookie": f"dy_did={device_id}; mantine-color-scheme-value=light",
        }
        sec_res = requests.get(sec_url, headers=headers, timeout=10).json()
        if sec_res.get("error") != 0:
            return None
        d = sec_res.get("data", {})
        if not d.get("key") or not d.get("enc_data"):
            return None
        return d.get("key"), d.get("rand_str"), d.get("enc_time", 1), d.get("enc_data")

    def _douyu_sign_and_fetch(
        self, channel, device_id, secret_key, random_str, enc_time, enc_data, rate=-1
    ):
        """计算签名并请求指定码率的播放地址（一次性、不可复用）"""

        def _sign(ts):
            cur = random_str
            for _ in range(enc_time):
                cur = hashlib.md5(f"{cur}{secret_key}".encode()).hexdigest()
            return hashlib.md5(f"{cur}{secret_key}{channel}{ts}".encode()).hexdigest()

        current_time = int(time.time())
        play_payload = {
            "enc_data": enc_data,
            "tt": str(current_time),
            "did": device_id,
            "auth": _sign(current_time),
            "cdn": "",
            "rate": str(rate) if rate and rate > 0 else "",
            "hevc": "0",
            "fa": "0",
            "ive": "0",
        }
        play_api = f'{self.hosts["douyu"]}/lapi/live/getH5PlayV1/{channel}'
        headers = {
            "User-Agent": self.headers[0]["User-Agent"],
            "Referer": f'{self.hosts["douyu"]}/{channel}',
            "Origin": self.hosts["douyu"],
            "Cookie": f"dy_did={device_id}; mantine-color-scheme-value=light",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        play_res = requests.post(
            play_api, data=play_payload, headers=headers, timeout=10
        ).json()
        if not play_res or play_res.get("error") != 0:
            return None

        # 若服务端返回了矫正后的 did，用新 did 重新签名再取一次
        rtmp_live = play_res.get("data", {}).get("rtmp_live", "")
        m = re.search(r"did=([a-f0-9]{32})", rtmp_live)
        if m and m.group(1) != device_id:
            device_id = m.group(1)
            current_time = int(time.time())
            play_payload.update(
                {"did": device_id, "tt": str(current_time), "auth": _sign(current_time)}
            )
            headers["Cookie"] = f"dy_did={device_id}; mantine-color-scheme-value=light"
            play_res = requests.post(
                play_api, data=play_payload, headers=headers, timeout=10
            ).json()
            if not play_res or play_res.get("error") != 0:
                return None

        info = play_res.get("data", {})
        if info.get("rtmp_url") and info.get("rtmp_live"):
            return f"{info['rtmp_url']}/{info['rtmp_live']}"
        if info.get("hls_url"):
            return info["hls_url"]
        return None

    def _get_douyu_play_url(self, channel, rate=-1):
        """生成【全新、从未被连接过】的斗鱼播放地址，最多重试 3 次。

        v6 修复核心（2026-08 实测）：
        斗鱼现已把 web-h5 线路统一到华为 CDN(hw-h5)，该 CDN 对每个播放地址
        **只允许第一次连接完整拉流**；同一地址的后续连接（不论间隔 30 秒还是 10 分钟）
        一律只推送约 390KB（约 1 秒画面）后 RST 断开。
        地址本身长期有效（放置 75 秒后首次连接仍可拉满），被限制的是「重连」而非「时效」。
        因此每次播放都必须实时走「新 did → getEncryption → 签名 → getH5PlayV1」生成全新地址。
        """
        for _ in range(3):
            try:
                device_id = "".join(
                    random.choice("0123456789abcdef") for _ in range(32)
                )
                enc = self._douyu_get_encryption(device_id)
                if not enc:
                    continue
                url = self._douyu_sign_and_fetch(
                    channel, device_id, enc[0], enc[1], enc[2], enc[3], rate
                )
                if url:
                    return url
            except Exception:
                pass
            time.sleep(0.2)
        return None

    def douyuplay(self, ids):
        """斗鱼播放：每次实时生成【单个】全新地址

        v6 修复（2026-08 实测）：
        1. 旧实现一次性生成全部清晰度地址并返回 [name, url, ...] 数组。
           FongMi/TVBox 会把该数组拆成多个「集」，播放器或壳子的预连接/测速
           会消耗掉这些地址唯一的「首次连接」配额；正式播放时只剩约 390KB
           （约 1 秒画面）即被 CDN 断开，播放器误判「本集播完」→ 弹下一集。
        2. 改为只返回当前清晰度的【单个地址字符串】，且每次播放都实时重新
           签名生成，保证交给播放器的永远是全新、未被连接过的地址。
        """
        try:
            rate = -1
            channel = None
            # 新结构：ids[1] = 清晰度标记('#0')，ids[2] = 房间号
            try:
                raw = self.d64(ids[1])
                if isinstance(raw, str) and raw.startswith("#"):
                    rate = int(raw[1:])
                channel = self.d64(ids[2])
            except Exception:
                channel = None
            # 兼容旧版缓存下来的播放项（ids[2] 为 session_info JSON）
            if not channel or not str(channel).strip().isdigit():
                try:
                    old = json.loads(self.d64(ids[2]))
                    if isinstance(old, dict) and old.get("channel"):
                        channel = str(old["channel"])
                        q = json.loads(self.d64(ids[1]))
                        if (
                            isinstance(q, list)
                            and len(q) > 1
                            and str(q[1]).startswith("#")
                        ):
                            rate = int(str(q[1])[1:])
                except Exception:
                    pass
            if not channel:
                return 1, self.excepturl

            play_url = self._get_douyu_play_url(channel, rate)
            if not play_url and rate != -1:
                play_url = self._get_douyu_play_url(channel, -1)  # 兜底：回退原画
            if not play_url:
                return 1, self.excepturl
            # 返回单个地址字符串（不再返回 [name, url, ...] 数组）
            return 0, play_url
        except Exception as e:
            print(f"斗鱼播放解析错误: {e}")
            return 1, self.excepturl

    def process_douyu(self):
        try:
            self.dyufdata = self.fetch(
                f'{self.referers["douyu"]}/api/cate/list', headers=self.headers[1]
            ).json()
            return (
                "douyu",
                [
                    {
                        "key": "cate",
                        "name": "分类",
                        "value": [
                            {"n": i["cate1Name"], "v": str(i["cate1Id"])}
                            for i in self.dyufdata["data"]["cate1Info"]
                        ],
                    }
                ],
            )
        except Exception as e:
            print(f"douyu错误: {e}")
            return "douyu", None

    def process_bili(self):
        """B站分类：Area/getList 老接口"""
        try:
            data = self.fetch(
                f'{self.hosts["bili"]}/room/v1/Area/getList', headers=self.headerx
            ).json()
            if data.get("code") != 0:
                return "bili", None
            values = [{"n": "全部", "v": "9-0"}]
            for cate in data["data"]:
                for sub in cate.get("list", [])[:6]:
                    values.append({"n": sub["name"], "v": f"{cate['id']}-{sub['id']}"})
            return ("bili", [{"key": "cate", "name": "分区", "value": values}])
        except Exception as e:
            print(f"bili错误: {e}")
            return "bili", None

    def _douyin_get_web_rid(self, session, url):
        """从抖音页面提取 web_rid（兜底方案）"""
        html = session.get(url, timeout=15).text
        if '"web_rid"' in html:
            m = re.search(r'"web_rid"\s*:\s*"(\d+)"', html)
            if m:
                return m.group(1), html
        return None, html

    # 抖音 API 方案：本地计算 a_bogus 签名 + 常驻 ttwid cookie，绕过页面风控
    _DY_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    _DY_TTWID = (
        "ttwid=1%7CmDcInbJ7AJ-2PGtsgrG4xj7SOiNMzePqQBF1LMO2Qkg%7C1761107324%7C"
        "bbf97c2cd9f8eae8e8c36db4ef50c323deaa4b161179170aaf659590867c162d"
    )

    def _dy_dialog(self, title="抖音直播间", prompt="粘贴抖音分享链接或房间号："):
        """弹窗收集输入：PC用tkinter，TV端通过searchContent传入"""
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.attributes("-fullscreen", False)
            result = simpledialog.askstring(title, prompt, parent=root)
            root.destroy()
            if result:
                return result
        except Exception:
            pass
        # TV端：返回空字符串，由用户通过搜索功能输入
        return ""

    # 娱乐分类关键词→标签映射（用于过滤一级分类的混合内容）
    _ENTERTAINMENT_TAG_MAP = {
        "101": ["聊天", "闲聊", "电台", "声音"],
        "102": ["唱歌", "音乐", "吉他", "钢琴", "乐器", "翻唱", "K歌", "乐队"],
        "105": ["舞蹈", "跳舞", "编舞", "街舞", "爵士", "古典舞", "古风舞"],
        "104": ["二次元", "cos", "漫展", "动漫", "宅舞", "虚拟主播", "Vtuber"],
        "106": ["时尚", "穿搭", "美妆", "化妆", "穿搭分享"],
        "107": ["运动", "健身", "瑜伽", "跑步", "篮球", "足球"],
        "108": ["美食", "烹饪", "吃播", "探店", "厨艺"],
    }

    # 抖音分类目录（amemv 网关 partition API，partition_type=1）
    # 叶子节点：经 game_tag 校验分类准确；一级娱乐分类（101-108）返回混合内容（游戏/娱乐/带货混合）
    _DY_CATES = [
        ("720", "推荐"),
        # 游戏子分类（经 game_tag 校验）
        ("1011032", "三角洲行动"),
        ("1010045", "王者荣耀"),
        ("1010017", "无畏契约"),
        ("1010014", "英雄联盟"),
        ("1010032", "和平精英"),
        ("1010003", "CSGO"),
        ("1010037", "穿越火线"),
        ("1010026", "绝地求生"),
        ("1010018", "暗区突围"),
        ("1010055", "金铲铲之战"),
        ("1010023", "英雄联盟手游"),
        ("1010039", "原神"),
        ("1010005", "云顶之弈"),
        ("1010041", "第五人格"),
        ("1010042", "火影忍者手游"),
        ("1010063", "JJ象棋"),
        ("1010061", "三国杀"),
        ("1010150", "魔兽世界"),
        ("1010350", "魔兽争霸3"),
        ("1010732", "梦三国"),
        # 一级娱乐分类（混合内容，包含聊天/跳舞/唱歌等）
        ("105", "跳舞"),
        ("102", "音乐"),
        ("101", "聊天"),
        ("104", "二次元"),
        ("106", "时尚"),
        ("107", "运动"),
        ("108", "美食"),
    ]
    # 分类ID→名称映射（用于标签提示）
    _DY_CATES_DICT = {v: k for k, v in _DY_CATES}

    def _douyin_api_get(self, url, referer):
        """带 a_bogus 签名请求抖音 webcast API"""
        signed = (
            url
            + "&a_bogus="
            + _dy_ab_sign(urllib.parse.urlparse(url).query, self._DY_UA)
        )
        headers = {
            "referer": referer,
            "user-agent": self._DY_UA,
            "cookie": self._DY_TTWID,
        }
        return requests.get(signed, headers=headers, timeout=15).json()

    def _douyin_enter(self, web_rid):
        """web_rid → (room, nickname)；web/enter 接口"""
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "116.0.0.0",
            "web_rid": web_rid,
            "is_need_double_stream": "false",
            "msToken": "",
        }
        api = (
            "https://live.douyin.com/webcast/room/web/enter/?"
            + urllib.parse.urlencode(params)
        )
        j = self._douyin_api_get(api, "https://live.douyin.com/")
        data = j.get("data") or {}
        rooms = data.get("data") or []
        if not rooms:
            raise Exception(data.get("prompts") or "房间数据为空")
        return rooms[0], (data.get("user") or {}).get("nickname", "")

    def _douyin_reflow(self, room_id="", sec_uid=""):
        """room_id/sec_uid → (room, nickname)；reflow info 接口（必须带 app_id=6383）"""
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "116.0.0.0",
            "app_id": "6383",
            "room_id": room_id,
            "sec_user_id": sec_uid,
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "msToken": "",
        }
        api = (
            "https://webcast.amemv.com/webcast/room/reflow/info/?"
            + urllib.parse.urlencode(params)
        )
        j = self._douyin_api_get(api, "https://live.douyin.com/")
        data = j.get("data") or {}
        room = data.get("room")
        if not room:
            raise Exception(data.get("prompts") or "房间数据为空")
        owner = room.get("owner") or {}
        return room, owner.get("nickname", "")

    def _douyin_page_stream(self, page_id):
        """直播间页面 SSR 提取 flv_pull_url 档位（API 被风控降流时的兜底）
        page_id 可为 web_rid 或 room_id，返回 [(档名, url), ...]"""
        import time as _t

        h = {
            "user-agent": self._DY_UA,
            "referer": "https://live.douyin.com/",
            "cookie": self._DY_TTWID,
        }
        for i in range(2):
            try:
                r = self.fetch(
                    "https://live.douyin.com/%s" % page_id, headers=h, timeout=15
                )
                t = r.text
                m = re.search(r'\\"flv_pull_url\\":(\{[^}]+\})', t)
                if m:
                    raw = m.group(1).replace('\\"', '"').replace("\\u0026", "&")
                    j = json.loads(raw)
                    names = {
                        "FULL_HD1": "蓝光1080P",
                        "HD1": "高清720P",
                        "SD1": "标清540P",
                        "SD2": "流畅360P",
                    }
                    result = [(names.get(k, k), u) for k, u in j.items()]
                    if result:
                        return result
            except Exception:
                pass
            _t.sleep(2.5)
        return []

    @staticmethod
    def _douyin_room_qualities(room):
        """从房间数据提取清晰度列表：转码流4档 + stream_data 提取原画"""
        quality_names = {
            "ORIGIN": "原画",
            "ORIGINE": "原画",
            "FULL_HD1": "蓝光1080P",
            "HD1": "高清720P",
            "SD1": "标清540P",
            "SD2": "流畅360P",
            "BD1": "超清",
        }
        stream_url = room.get("stream_url") or {}
        result = []
        # stream_data 里的 ORIGIN 原画（1080x1920 原始流）
        try:
            sdk = json.loads(
                stream_url["live_core_sdk_data"]["pull_data"]["stream_data"]
            )
            origin = sdk["data"]["origin"]["main"]
            codec = (json.loads(origin["sdk_params"]).get("VCodec")) or ""
            result.append(
                ("原画", origin["flv"] + ("&codec=" + codec if codec else ""))
            )
        except Exception:
            pass
        # 转码档位
        for key, url in (stream_url.get("flv_pull_url") or {}).items():
            result.append((quality_names.get(key, key), url))
        if len(result) < 2:
            for key, url in (stream_url.get("hls_pull_url_map") or {}).items():
                result.append((quality_names.get(key, key) + "(HLS)", url))
        # 原画码率过高，默认档给蓝光1080P（ExoPlayer 高码率缓冲易断流）
        if len(result) > 1 and result[0][0] == "原画":
            result.append(result.pop(0))
        return result

    def douyinDetail(self, ids):
        """抖音详情：webcast API 元数据 + 页面 SSR 提流兜底
        纯数字=web_rid；r{room_id}[@{web_rid}]=reflow；u{sec_uid}=用户主页"""
        try:
            rid = ids[1]
            if rid == "help":
                vod = self.buildvod(vod_id="douyin@@help", vod_name="抖音直播使用说明")
                vod["vod_play_from"] = "说明"
                vod["vod_play_url"] = f"说明${self.excepturl}"
                return vod

            room_id = sec_uid = web_rid = ""
            if rid.startswith("r"):
                parts = rid[1:].split("@")
                room_id = parts[0]
                web_rid = parts[1] if len(parts) > 1 else ""
            elif rid.startswith("u"):
                sec_uid = rid[1:]
            else:
                web_rid = rid

            room, nickname = None, ""
            try:
                if sec_uid:
                    room, nickname = self._douyin_reflow(sec_uid=sec_uid)
                elif room_id:
                    room, nickname = self._douyin_reflow(room_id=room_id)
                elif web_rid:
                    room, nickname = self._douyin_enter(web_rid)
            except Exception as e:
                print(f"抖音API元数据失败: {e}")

            if room and room.get("status") == 4:
                return self.handle_exception(Exception("当前未开播"))

            qualities = self._douyin_room_qualities(room) if room else []
            if not qualities:
                # API 被风控降流时走页面 SSR 兜底
                qualities = self._douyin_page_stream(web_rid or room_id)
            if not qualities:
                return self.handle_exception(Exception("未获取到流数据"))

            name = (room or {}).get("title") or "抖音直播间"
            vod = self.buildvod(
                vod_id=ids[0] + "@@" + ids[1],
                vod_name=name,
                vod_remarks=nickname,
                vod_content="抖音直播",
            )
            vod["vod_play_from"] = "抖音直播"
            play = []
            for qname, qurl in qualities:
                play.extend([qname, qurl])
            vod["vod_play_url"] = f"{name}${ids[0]}@@{self.e64(json.dumps(play))}"
            return vod
        except Exception as e:
            return self.handle_exception(e)

    def _douyin_resolve_share(self, key):
        """解析抖音分享口令/短链，返回 vod_id 后缀或 None
        支持格式：v.douyin.com短链(可带口令全文)、live.douyin.com/数字、MS4wLjAB开头的sec_uid"""
        try:
            # 分享口令里提取短链
            m = re.search(r"https?://v\.douyin\.com/([\w-]+)", key)
            if m:
                short = "https://v.douyin.com/" + m.group(1)
                r = requests.get(
                    short,
                    headers={"User-Agent": self.headerx["User-Agent"]},
                    timeout=10,
                    allow_redirects=False,
                )
                loc = (
                    r.headers.get("Location", "") if r.status_code in (301, 302) else ""
                )
                # 短链最终指向 reflow/{room_id}
                mr = re.search(r"reflow/(\d+)", loc)
                if mr:
                    return "r" + mr.group(1)
                # 或直接指向 live.douyin.com/{web_rid}
                ml = re.search(r"live\.douyin\.com/(\d+)", loc)
                if ml:
                    return ml.group(1)
                # 或指向用户主页
                ms = re.search(r"(MS4wLjABAAAA[\w-]+)", loc)
                if ms:
                    return "u" + ms.group(1)
                return None
            # 长链接
            m = re.search(r"live\.douyin\.com/(\d+)", key)
            if m:
                return m.group(1)
            # 用户主页链接或裸sec_uid
            m = re.search(
                r"(?:douyin\.com/user/|live\.douyin\.com/)?(MS4wLjABAAAA[\w-]{20,})",
                key,
            )
            if m:
                return "u" + m.group(1)
        except Exception as e:
            print(f"抖音分享解析失败: {e}")
        return None

    def searchContent(self, key, quick, pg="1"):
        """纯数字/分享口令/直播间链接搜索，直达对应直播间"""
        results = []
        if not key or not key.strip():
            return results
        key = key.strip()
        # 抖音分享口令/短链/链接解析
        dy = self._douyin_resolve_share(key)
        if dy:
            results.append(
                self.buildvod(
                    vod_id=f"douyin@@{dy}",
                    vod_name=f"抖音直播间",
                    vod_remarks="来自分享链接，点击进入",
                    style={"type": "rect", "ratio": 1.33},
                )
            )
            return results
        # 纯数字：抖音房间号
        if key.isdigit():
            results.append(
                self.buildvod(
                    vod_id=f"douyin@@{key}",
                    vod_name=f"抖音直播间 {key}",
                    vod_remarks="点击进入直播间",
                    style={"type": "rect", "ratio": 1.33},
                )
            )
        # 虎牙链接
        m = re.search(r"(?:huya\.com|live\.huya\.com)/(\w+)", key)
        if m:
            rid = m.group(1)
            results.append(
                self.buildvod(
                    vod_id=f"huya@@{rid}",
                    vod_name=f"虎牙直播间 {rid}",
                    vod_remarks="点击进入直播间",
                    style={"type": "rect", "ratio": 1.33},
                )
            )
        # 斗鱼链接
        m = re.search(r"(?:douyu\.com|www\.douyu\.com)/(\d+)", key)
        if m:
            rid = m.group(1)
            results.append(
                self.buildvod(
                    vod_id=f"douyu@@{rid}",
                    vod_name=f"斗鱼直播间 {rid}",
                    vod_remarks="点击进入直播间",
                    style={"type": "rect", "ratio": 1.33},
                )
            )
        # B站直播间URL
        m = re.search(r"(?:live\.bilibili\.com|bcd\.tv)/(\d+)", key)
        if m:
            rid = m.group(1)
            results.append(
                self.buildvod(
                    vod_id=f"bili@@{rid}",
                    vod_name=f"B站直播间 {rid}",
                    vod_remarks="点击进入直播间",
                    style={"type": "rect", "ratio": 1.33},
                )
            )
        return results

    def playerContent(self, flag, id, vipFlags):
        try:
            ids = id.split("@@")
            p = 1
            if ids[0] in ["wangyi", "huya", "bili", "douyin"]:
                decoded = json.loads(self.d64(ids[1]))
                p, url = 0, decoded
            elif ids[0] == "douyu":
                p, url = self.douyuplay(ids)
            return {
                "parse": p,
                "url": url,
                "header": self.playheaders.get(ids[0], self.headers[0]),
            }
        except Exception as e:
            return {"parse": 1, "url": self.excepturl, "header": self.headers[0]}

    def douyuplay(self, ids):
        """斗鱼播放：每次实时生成【单个】全新地址

        v6 修复（2026-08 实测）：
        1. 旧实现一次性生成全部清晰度地址并返回 [name, url, ...] 数组。
           FongMi/TVBox 会把该数组拆成多个「集」，播放器或壳子的预连接/测速
           会消耗掉这些地址唯一的「首次连接」配额；正式播放时只剩约 390KB
           （约 1 秒画面）即被 CDN 断开，播放器误判「本集播完」→ 弹下一集。
        2. 改为只返回当前清晰度的【单个地址字符串】，且每次播放都实时重新
           签名生成，保证交给播放器的永远是全新、未被连接过的地址。
        """
        try:
            rate = -1
            channel = None
            # 新结构：ids[1] = 清晰度标记('#0')，ids[2] = 房间号
            try:
                raw = self.d64(ids[1])
                if isinstance(raw, str) and raw.startswith("#"):
                    rate = int(raw[1:])
                channel = self.d64(ids[2])
            except Exception:
                channel = None
            # 兼容旧版缓存下来的播放项（ids[2] 为 session_info JSON）
            if not channel or not str(channel).strip().isdigit():
                try:
                    old = json.loads(self.d64(ids[2]))
                    if isinstance(old, dict) and old.get("channel"):
                        channel = str(old["channel"])
                        q = json.loads(self.d64(ids[1]))
                        if (
                            isinstance(q, list)
                            and len(q) > 1
                            and str(q[1]).startswith("#")
                        ):
                            rate = int(str(q[1])[1:])
                except Exception:
                    pass
            if not channel:
                return 1, self.excepturl

            play_url = self._get_douyu_play_url(channel, rate)
            if not play_url and rate != -1:
                play_url = self._get_douyu_play_url(channel, -1)  # 兜底：回退原画
            if not play_url:
                return 1, self.excepturl
            # 返回单个地址字符串（不再返回 [name, url, ...] 数组）
            return 0, play_url
        except Exception as e:
            print(f"斗鱼播放解析错误: {e}")
            return 1, self.excepturl

    def localProxy(self, param):
        """代理接口：处理图片代理等请求"""
        # 当前版本暂不支持弹窗输入代理
        return None

    def e64(self, text):
        try:
            return b64encode(text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            return b64decode(encoded_text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def buildvod(
        self,
        vod_id="",
        vod_name="",
        vod_pic="",
        vod_year="",
        vod_tag="",
        vod_remarks="",
        style="",
        type_name="",
        vod_area="",
        vod_actor="",
        vod_director="",
        vod_content="",
        vod_play_from="",
        vod_play_url="",
    ):
        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_year": vod_year,
            "vod_tag": "folder" if vod_tag else "",
            "vod_remarks": vod_remarks,
            "style": style,
            "type_name": type_name,
            "vod_area": vod_area,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_content": vod_content,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }
        vod = {key: value for key, value in vod.items() if value}
        return vod

    def getpq(self, url, headers=None, cookies=None):
        data = self.fetch(url, headers=headers, cookies=cookies).text
        try:
            return pq(data)
        except Exception as e:
            print(f"解析页面错误: {str(e)}")
            return pq(data.encode("utf-8"))

    def handle_exception(self, e):
        print(f"报错: {str(e)}")
        return {
            "vod_play_from": "哎呀翻车啦",
            "vod_play_url": f"翻车啦${self.excepturl}",
        }
