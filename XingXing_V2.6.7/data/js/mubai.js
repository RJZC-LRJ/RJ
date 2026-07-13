/*
 * @File   : mubai.js
 * @Author : opencode
 * @Date   : 2026-07-09
 * @Desc   : 幕白影视 (m2.mubai.link) TVBox T4(JS) 源 —— 自包含，无外部依赖
 *
 * 站点特征：
 *  - GoFilm 系统，全部走 REST JSON API，GET 即可响应，无防护盾、无加密。
 *  - 首页      : GET /api/index     → banners + category树 + content[](hot/movies)
 *  - 分类列表  : GET /api/filmClassifySearch?Pid&Category&page&Area&Year&Language&Sort
 *           返回 page{pageSize,current,pageCount,total} + list[{id,name,picture,remarks,...}]
 *  - 详情      : GET /api/filmDetail?id={mid}
 *           返回 detail{...,list[{id,name,linkList[{episode,link(m3u8直链)}]}]}
 *  - 搜索      : GET /api/searchFilm?keyword={关键词}
 *           返回 list[{id,name,picture,...}] + page{}
 *  - 分类导航  : GET /api/navCategory → [{id,name}]  4个一级分类
 *  - 首页自带 category 分类树（pid=一级分类id，children=二级分类列表）。
 *
 * 播放：
 *  详情 list.linkList[].link 是对应的 m3u8 直链，直接 parse=0 传回内核。
 *  剧集(.m3u8) 放到 vod_play_url 中，每集 name$link，不同源用 # 分隔，#$$$ 分隔源。
 *
 * 设计：
 *  一级分类 = pid (1=电影片 2=连续剧 3=综艺 4=动漫)
 *  筛选 = area/year/sort (sort 暂提供 update_stamp 默认/ hits 热门/ score 评分)
 *  分类加载（二级子类）在 init/home 从 /api/index 拉取 category 树缓存。
 */

var MB_VERSION = "20260709-js-1";
var HOST = "https://m2.mubai.link";
var API = HOST + "/api";
var UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

var CLASSES = [];
var CATEGORIES = {};    // pid -> [{type_id:cid, type_name:cName}]
var FILTERS = {};
var AREAS = [];
var YEARS = [];
var CAT_LOADED = false;

function log(msg) {
    try { console.log("[MB_JS " + MB_VERSION + "] " + msg); } catch (e) {}
}

/* ---------------- 通用工具 ---------------- */

function toStr(v) { return v === undefined || v === null ? "" : String(v); }
function encode(s) { return encodeURIComponent(toStr(s)); }

function fixUrl(u) {
    u = toStr(u).trim();
    if (!u) return "";
    if (u.indexOf("//") === 0) return "https:" + u;
    if (u.charAt(0) === "/") return HOST + u;
    return /^https?:\/\//i.test(u) ? u : "";
}

function requestJson(url) {
    var headers = {
        "User-Agent": UA,
        "Accept": "application/json,*/*;q=0.8",
        "Referer": HOST + "/"
    };
    try {
        var res = req(url, { method: "GET", headers: headers, timeout: 12000 });
        var body = (typeof res === "string") ? res : (res && (res.content || res.body || res.data));
        if (typeof body === "string") {
            try { return JSON.parse(body); } catch (e) { log("json_parse_error " + e); return null; }
        }
        return body || null;
    } catch (e) {
        log("fetch_error " + url + " " + e);
        return null;
    }
}

/* ---------------- 分类加载 ---------------- */

function loadCategories() {
    if (CAT_LOADED) return;
    var data = requestJson(API + "/index");
    if (!data || !data.code || !data.data || !data.data.content) return;
    CAT_LOADED = true;

    var content = data.data.content;
    var classes = [];
    var cats = {};
    var filters = {};
    var areasSet = {};
    var yearsSet = {};

    for (var i = 0; i < content.length; i++) {
        var tab = content[i];
        var nav = tab.nav;
        if (!nav || !nav.id) continue;
        var pid = nav.id;
        var pname = toStr(nav.name);
        classes.push({ type_id: pid, type_name: pname });

        // 二级子类（合并导航 API 子类 + 分类树 subcats）
        var subcats = [];
        var seenIds = {};

        // 从 tab.movies 提取最常用分类
        var allMovies = (tab.movies || []).concat(tab.hot || []);
        for (var j = 0; j < allMovies.length; j++) {
            var m = allMovies[j];
            if (m.cid && !seenIds[m.cid]) {
                seenIds[m.cid] = 1;
                subcats.push({ type_id: m.cid, type_name: toStr(m.cName) });
            }
            if (m.area && !areasSet[m.area]) areasSet[m.area] = 1;
            if (m.year && !yearsSet[m.year]) yearsSet[m.year] = 1;
        }

        // 从首页 category 树提取该 pid 的 children
        if (data.data.category && data.data.category.children) {
            var roots = data.data.category.children;
            for (var k = 0; k < roots.length; k++) {
                if (roots[k].id === pid && roots[k].children) {
                    var ch = roots[k].children;
                    for (var ci = 0; ci < ch.length; ci++) {
                        var cnode = ch[ci];
                        if (cnode.id && !seenIds[cnode.id]) {
                            seenIds[cnode.id] = 1;
                            subcats.push({ type_id: cnode.id, type_name: toStr(cnode.name) });
                        }
                    }
                }
            }
        }

        cats[pid] = subcats;

        // 筛选
        var areaOpts = [{ n: "全部", v: "" }];
        var ks = Object.keys(areasSet);
        for (var a = 0; a < ks.length; a++) areaOpts.push({ n: ks[a], v: ks[a] });
        AREAS = areaOpts;

        var yearOpts = [{ n: "全部", v: "" }];
        var yks = Object.keys(yearsSet);
        for (var y = 0; y < yks.length; y++) {
            if (parseInt(yks[y]) >= 2000) yearOpts.push({ n: yks[y], v: yks[y] });
        }
        YEARS = yearOpts;

        var fid = [
            { key: "cate", name: "分类", value: subcats },
            { key: "area", name: "地区", value: areaOpts },
            { key: "year", name: "年份", value: yearOpts },
            {
                key: "sort", name: "排序", value: [
                    { n: "默认", v: "" },
                    { n: "热门", v: "hits" },
                    { n: "评分", v: "score" }
                ]
            }
        ];
        filters[pid] = fid;
    }

    CLASSES = classes;
    CATEGORIES = cats;
    FILTERS = filters;
    log("cat_loaded classes=" + CLASSES.length + " subcats=" + JSON.stringify(Object.keys(cats)));
}

/* ---------------- 列表格式化 ---------------- */

function formatListItem(m) {
    var vid = toStr(m.id || m.mid);
    var remark = toStr(m.remarks || "");
    if (!remark && m.year) remark = String(m.year);
    return {
        vod_id: vid,
        vod_name: toStr(m.name || vid),
        vod_pic: fixUrl(m.picture || ""),
        vod_remarks: remark
    };
}

/* ---------------- 接口实现 ---------------- */

function init(ext) {
    if (typeof ext === "string" && /^https?:\/\//i.test(ext.trim())) {
        HOST = ext.trim().replace(/\/+$/, "");
        API = HOST + "/api";
    }
    CAT_LOADED = false;
    CLASSES = [];
    CATEGORIES = {};
    FILTERS = {};
    loadCategories();
    log("init host=" + HOST);
}

function home(filter) {
    loadCategories();
    return JSON.stringify({ class: CLASSES, filters: FILTERS });
}

function homeVod() {
    log("homeVod");
    var data = requestJson(API + "/index");
    var list = [];
    if (data && data.data && data.data.content) {
        for (var i = 0; i < data.data.content.length; i++) {
            var tab = data.data.content[i];
            var items = (tab.hot || []).concat(tab.movies || []);
            for (var j = 0; j < items.length; j++) list.push(formatListItem(items[j]));
        }
    }
    // 去重 id
    var seen = {};
    var out = [];
    for (var k = 0; k < list.length; k++) {
        if (!seen[list[k].vod_id]) { seen[list[k].vod_id] = 1; out.push(list[k]); }
    }
    log("homeVod count=" + out.length);
    return JSON.stringify({ list: out });
}

function category(tid, pg, filter, extend) {
    tid = toStr(tid || "1");
    pg = parseInt(pg || 1);
    if (!pg || pg < 1) pg = 1;
    extend = extend || {};

    var cate = toStr(extend.cate || "");
    var area = toStr(extend.area || "");
    var year = toStr(extend.year || "");
    var sort = toStr(extend.sort || "");

    var url = API + "/filmClassifySearch?Pid=" + encode(tid) + "&page=" + pg;
    if (cate) url += "&Category=" + encode(cate);
    if (area) url += "&Area=" + encode(area);
    if (year) url += "&Year=" + encode(year);
    if (sort) url += "&Sort=" + encode(sort);

    var res = requestJson(url);
    var listData = (res && res.data && res.data.list) || [];
    var pgInfo = (res && res.data && res.data.page) || {};

    var list = listData.map(formatListItem); 

    var pagecount = parseInt(pgInfo.pageCount || 1) || 1;
    var limit = parseInt(pgInfo.pageSize || list.length) || list.length;
    var total = parseInt(pgInfo.total || list.length) || list.length;

    log("category pid=" + tid + " pg=" + pg + " count=" + list.length + " pages=" + pagecount);
    return JSON.stringify({ page: pg, pagecount: pagecount, limit: limit, total: total, list: list });
}

function detail(id) {
    var mid = toStr(id);
    log("detail mid=" + mid);

    var data = requestJson(API + "/filmDetail?id=" + encode(mid));
    var d = (data && data.code === 0 && data.data && data.data.detail) ? data.data.detail : null;
    if (!d) {
        return JSON.stringify({ list: [{ vod_id: mid, vod_name: mid, vod_play_from: "提示", vod_play_url: "无资源$" }] });
    }

    var vod = {
        vod_id: mid,
        vod_name: toStr(d.name || mid),
        vod_pic: fixUrl(d.picture),
        vod_remarks: toStr(d.remarks || d.year || ""),
        type_name: toStr(d.cName || ""),
        vod_year: toStr(d.year || ""),
        vod_area: toStr(d.area || ""),
        vod_director: toStr(d.director || ""),
        vod_actor: toStr(d.actor || ""),
        vod_content: toStr(d.content || d.blurb || "")
    };

    if (d.list && d.list.length > 0) {
        var playFrom = [];
        var playUrl = [];
        for (var i = 0; i < d.list.length; i++) {
            var src = d.list[i];
            if (!src || !src.linkList || src.linkList.length === 0) continue;
            playFrom.push(toStr(src.name || "源" + (i + 1)));
            var eps = [];
            for (var j = 0; j < src.linkList.length; j++) {
                var ep = src.linkList[j];
                var epName = toStr(ep.episode || ep.name || "第" + (j + 1) + "集");
                var epLink = toStr(ep.link);
                if (epName && epLink) eps.push(epName + "$" + epLink);
            }
            playUrl.push(eps.join("#"));
        }
        vod.vod_play_from = playFrom.join("$$$");
        vod.vod_play_url = playUrl.join("$$$");
    } else {
        vod.vod_play_from = "提示";
        vod.vod_play_url = "暂无资源$";
    }

    return JSON.stringify({ list: [vod] });
}

function play(flag, id, flags) {
    // id 直接是 m3u8/mp4 直链
    var url = toStr(id);
    log("play flag=" + flag + " url=" + url.slice(0, 80));
    var header = { "User-Agent": UA, "Referer": HOST + "/" };
    return JSON.stringify({ parse: 0, url: url, header: header });
}

function search(wd, quick, pg) {
    pg = parseInt(pg || 1);
    if (!pg || pg < 1) pg = 1;
    wd = toStr(wd).trim();
    log("search wd=" + wd + " pg=" + pg);
    if (!wd) return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 0, total: 0 });

    var url = API + "/searchFilm?keyword=" + encode(wd);
    var res = requestJson(url);
    var listData = (res && res.data && res.data.list) || [];
    var pgInfo = (res && res.data && res.data.page) || {};

    var list = listData.map(function (m) {
        return {
            vod_id: toStr(m.id || m.mid),
            vod_name: toStr(m.name),
            vod_pic: fixUrl(m.picture),
            vod_remarks: toStr(m.remarks || m.year || "")
        };
    });

    var page = parseInt(pgInfo.current || 1) || 1;
    var pagecount = parseInt(pgInfo.pageCount || 1) || 1;
    var total = parseInt(pgInfo.total || list.length) || list.length;

    log("search result count=" + list.length);
    return JSON.stringify({ list: list, page: page, pagecount: pagecount, limit: list.length || 1, total: total });
}

/* ---------------- 导出 ---------------- */

__JS_SPIDER__ = {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    play: play,
    search: search
};