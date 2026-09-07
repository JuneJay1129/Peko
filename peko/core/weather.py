"""
天气播报（L1 免 Key 方案）：公开数据源 + 缓存降级 + 本地推断兜底。

设计要点
--------
- **免注册、免 Key**：主源 wttr.in 公开接口（`requests` 已在 requirements，零新增依赖）。
  实测 wttr.in 的 `lang=zh` 对天气描述无效（仍返回英文），因此现象名由本地关键词表转中文。
- **三级降级**：联网取数 → 本地缓存（data/weather_cache.json）→ 按月份本地推断。
  任何一级失败都不会让桌宠崩掉。
- **城市记忆**：首次由 IP 定位（ip-api.com，`lang=zh-CN` 返回中文城市名）并写入
  config/weather.json；之后直接用配置里的城市，不再重复定位。
- 纯 Python（不依赖 Qt），网络/文件/解析均可单元测试。

已知限制
--------
- wttr.in 是个人开源项目，接口可能变动；itboy 是中国天气网的非官方镜像，可能失效。
  这正是设计三级降级的原因：源挂了也只会退到缓存，不影响桌宠运行。
- 若配置了 `citykey`（中国天气网城市代码），会额外启用 itboy 作为备源，
  可拿到 7 天预报与中文贴心提示；默认不填也能用。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from .runtime_paths import get_writable_root

CACHE_TTL_MINUTES = 30       # 缓存新鲜期：此期内直接读缓存，不联网
CACHE_MAX_AGE_HOURS = 24     # 缓存可作为降级数据的最长时限
REQUEST_TIMEOUT = 6          # 单次网络请求超时（秒）

# %l 位置 | %C 现象 | %t 温度 | %f 体感 | %h 湿度 | %w 风
_WTTR_URL = "https://wttr.in/{city}?format=%l|%C|%t|%f|%h|%w"
_IPAPI_URL = "http://ip-api.com/json/?lang=zh-CN"
_ITBOY_URL = "http://t.weather.itboy.net/api/weather/city/{citykey}"

# 「我在XX」纠错用的已知城市表。
# 为什么需要它：wttr.in 会把「上班」这类词也当有效地点返回天气（实测 HTTP 200），
# 光靠数据源校验挡不住「我在上班」被误设成城市，因此口语纠错必须命中城市表才生效。
# 想设表里没有的城市，用明确动词：「城市改成 XX」。
_KNOWN_CITIES = (
    "北京", "上海", "天津", "重庆",
    "石家庄", "唐山", "保定", "邯郸", "秦皇岛", "廊坊",
    "太原", "大同", "临汾",
    "呼和浩特", "包头",
    "沈阳", "大连", "鞍山", "锦州", "营口",
    "长春", "吉林",
    "哈尔滨", "大庆", "齐齐哈尔",
    "南京", "无锡", "徐州", "常州", "苏州", "南通", "扬州", "镇江", "盐城", "泰州", "淮安",
    "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "台州", "丽水", "衢州", "舟山",
    "合肥", "芜湖", "蚌埠", "安庆", "黄山",
    "福州", "厦门", "泉州", "漳州", "莆田",
    "南昌", "赣州", "九江", "上饶",
    "济南", "青岛", "烟台", "潍坊", "淄博", "临沂", "济宁", "泰安", "威海", "聊城",
    "郑州", "洛阳", "开封", "新乡", "南阳", "许昌",
    "武汉", "宜昌", "襄阳", "荆州", "黄石", "十堰",
    "长沙", "株洲", "湘潭", "衡阳", "岳阳", "常德",
    "广州", "深圳", "珠海", "东莞", "佛山", "中山", "惠州", "汕头", "湛江", "江门", "肇庆",
    "南宁", "桂林", "柳州", "北海",
    "海口", "三亚",
    "成都", "绵阳", "德阳", "宜宾", "南充", "乐山",
    "贵阳", "遵义",
    "昆明", "大理", "丽江", "曲靖",
    "拉萨",
    "西安", "咸阳", "宝鸡", "渭南", "榆林", "汉中",
    "兰州", "天水",
    "西宁",
    "银川",
    "乌鲁木齐", "喀什", "伊犁",
    "香港", "澳门", "台北", "高雄", "台中", "台南",
)

_UA = {"User-Agent": "curl/7.0"}

# 天气现象关键词 → 中文。顺序敏感：先特殊后一般（haze 必须在 cloudy 之前）。
_COND_RULES = (
    ("thunder", "雷阵雨"),
    ("storm", "暴风雨"),
    ("blizzard", "暴风雪"),
    ("sleet", "雨夹雪"),
    ("hail", "冰雹"),
    ("freezing", "冻雨"),
    ("ice", "结冰"),
    ("snow", "雪"),
    ("drizzle", "毛毛雨"),
    ("rain", "雨"),
    ("shower", "阵雨"),
    ("fog", "雾"),
    ("mist", "薄雾"),
    ("haze", "霾"),
    ("smoke", "烟霾"),
    ("overcast", "阴"),
    ("cloudy", "多云"),
    ("clear", "晴"),
    ("sunny", "晴"),
)

# 程度词：仅对可加程度的降水类现象生效（torrential 自身已是完整词，不再拼接）
_DEGREE_RULES = (
    ("torrential", "暴雨"),
    ("heavy", "大"),
    ("moderate", "中"),
    ("light", "小"),
    ("patchy", "局部"),
)
_DEGREE_APPLIES_TO = ("rain", "snow", "sleet", "drizzle")

# 月份 → 粗略温度区间（中国大陆大部分地区，仅用于完全离线时的兜底）
_MONTH_TEMP = {
    1: (2, 10), 2: (4, 13), 3: (9, 18), 4: (15, 24),
    5: (20, 29), 6: (24, 32), 7: (27, 34), 8: (26, 33),
    9: (22, 29), 10: (16, 24), 11: (10, 18), 12: (4, 12),
}


def _cond_to_zh(desc: str) -> str:
    """把 wttr.in 的英文天气描述转中文；无法识别时原样返回。"""
    d = (desc or "").strip().lower()
    if not d:
        return ""
    for key, zh in _COND_RULES:
        if key in d:
            if key in _DEGREE_APPLIES_TO:
                for dk, dzh in _DEGREE_RULES:
                    if dk in d:
                        # "torrential" 已译作「暴雨」，末尾同字则不再拼接，避免「暴雨雨」
                        return dzh if dzh.endswith(zh[-1]) else dzh + zh
            return zh
    return desc.strip()


def normalize_city(name: str) -> str:
    """去掉行政区划后缀并去空白：'宁波市 ' → '宁波'。"""
    out = (name or "").strip()
    for suffix in ("特别行政区", "自治州", "自治区", "地区", "市", "省", "区", "县", "镇"):
        if out.endswith(suffix) and len(out) > len(suffix):
            out = out[: -len(suffix)]
            break
    return out.strip()


def is_known_city(name: str) -> bool:
    """是否在内置城市表中（用于「我在XX」口语纠错，避免误伤「我在上班」）。"""
    return normalize_city(name) in _KNOWN_CITIES


def match_city(text: str) -> Optional[str]:
    """从一段文本里找出内置城市表中的城市名；找不到返回 None。"""
    norm = normalize_city(text)
    for city in _KNOWN_CITIES:
        if city == norm or city in (text or ""):
            return city
    return None


def _parse_temp(text: str) -> Optional[int]:
    """从 '+24°C' / '-3°C' 中取出整数温度。"""
    m = re.search(r"([+-]?\d+)", (text or "").replace("−", "-"))
    return int(m.group(1)) if m else None


def _parse_humidity(text: str) -> Optional[int]:
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else None


class WeatherService:
    """天气读写与降级。所有方法都不抛异常，失败时返回 None 或降级结果。"""

    def __init__(self, module_file: Optional[str] = None):
        root = Path(get_writable_root(module_file or __file__))
        self.config_path = root / "config" / "weather.json"
        self.cache_path = root / "data" / "weather_cache.json"

    # ----- 配置 -----
    def load_config(self) -> Dict[str, Any]:
        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def save_config(self, config: Dict[str, Any]) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.config_path)
        except OSError:
            pass

    def get_city(self) -> str:
        return str(self.load_config().get("city") or "").strip()

    def set_city(self, city: str, region: Optional[str] = None,
                 country: Optional[str] = None, by_ip: bool = False) -> None:
        cfg = self.load_config()
        cfg["city"] = city
        if region:
            cfg["region"] = region
        if country:
            cfg["country"] = country
        cfg["by_ip"] = bool(by_ip)
        cfg["announced"] = False   # 换了城市就重新交代一次
        self.save_config(cfg)

    # ----- 缓存 -----
    def load_cache(self) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def save_cache(self, payload: Dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    @staticmethod
    def _age_of(payload: Dict[str, Any]) -> Optional[timedelta]:
        ts = payload.get("fetched_at")
        if not ts:
            return None
        try:
            return datetime.now() - datetime.fromisoformat(str(ts))
        except ValueError:
            return None

    def is_cache_fresh(self, payload: Optional[Dict[str, Any]] = None) -> bool:
        """缓存是否在新鲜期内（可直接用、不必联网）。"""
        payload = payload if payload is not None else self.load_cache()
        if not payload:
            return False
        age = self._age_of(payload)
        return age is not None and age < timedelta(minutes=CACHE_TTL_MINUTES)

    def is_cache_usable(self, payload: Optional[Dict[str, Any]] = None) -> bool:
        """缓存是否还能作为降级数据（超出新鲜期但未过期太久）。"""
        payload = payload if payload is not None else self.load_cache()
        if not payload:
            return False
        age = self._age_of(payload)
        return age is not None and age < timedelta(hours=CACHE_MAX_AGE_HOURS)

    # ----- 城市定位 -----
    def locate(self) -> Optional[Dict[str, str]]:
        """IP 定位，返回 {country, region, city, ip}。失败返回 None。

        注意：企业内网/代理的出口 IP 归属地常与真实位置不符，这就是提供
        「我在XX」口语纠错的原因。
        """
        try:
            r = requests.get(_IPAPI_URL, timeout=REQUEST_TIMEOUT, headers=_UA)
            if r.status_code != 200:
                return None
            data = r.json()
            city = str(data.get("city") or "").strip()
            if not city:
                return None
            return {
                "country": str(data.get("country") or "").strip(),
                "region": str(data.get("regionName") or "").strip(),
                "city": city,
                "ip": str(data.get("query") or "").strip(),
            }
        except Exception:
            return None

    def locate_city(self) -> Optional[str]:
        d = self.locate()
        return d["city"] if d else None

    def ensure_city(self) -> str:
        """优先用配置里的城市；没有才定位一次并记住。都失败则回退「北京」。"""
        city = self.get_city()
        if city:
            return city
        loc = self.locate()
        if loc:
            self.set_city(loc["city"], region=loc.get("region"), country=loc.get("country"), by_ip=True)
            return loc["city"]
        return "北京"

    # ----- IP 定位的告知与纠正 -----
    def ip_location_line(self) -> str:
        """IP 定位出来的城市，在向用户交代过之前返回说明文案；否则返回空串。"""
        cfg = self.load_config()
        if not cfg.get("by_ip") or cfg.get("announced"):
            return ""
        city = str(cfg.get("city") or "")
        area = " · ".join(x for x in (str(cfg.get("country") or ""), str(cfg.get("region") or "")) if x)
        where = f"：{area}" if area else ""
        return f"吱吱～我按网络嗅了嗅，猜你在 {city}（IP 归属地{where}）\n要是不对，跟我说「我在某某」就好啦～"

    def mark_announced(self) -> None:
        """标记「IP 定位结果已向用户交代过」，之后不再重复提示。"""
        cfg = self.load_config()
        cfg["announced"] = True
        self.save_config(cfg)

    def set_city_by_user(self, city: str) -> str:
        """用户手动指定城市（纠正 IP 定位）。返回给用户的确认文案。"""
        name = normalize_city(city) or city
        self.set_city(name, by_ip=False)
        return f"好嘞，记住啦！以后我都报{name}的天气，吱吱～"

    # ----- 数据源 -----
    def _fetch_wttr(self, city: str) -> Optional[Dict[str, Any]]:
        """主源：wttr.in。支持中文城市名，一行格式，无需 Key。"""
        for name in self._city_variants(city):
            try:
                r = requests.get(
                    _WTTR_URL.format(city=name), timeout=REQUEST_TIMEOUT, headers=_UA
                )
                if r.status_code != 200:
                    continue
                parts = [p.strip() for p in r.text.strip().split("|")]
                if len(parts) < 6:
                    continue
                city_name, cond_en, temp_s, feels_s, hum_s, wind_s = parts[:6]
                temp = _parse_temp(temp_s)
                if temp is None:
                    continue
                return {
                    "city": city_name or name,
                    "cond": _cond_to_zh(cond_en),
                    "temp_c": temp,
                    "feels_c": _parse_temp(feels_s),
                    "humidity": _parse_humidity(hum_s),
                    "wind": wind_s,
                    "source": "wttr.in",
                    "fetched_at": datetime.now().isoformat(timespec="minutes"),
                }
            except Exception:
                continue
        return None

    def _fetch_itboy(self, citykey: str) -> Optional[Dict[str, Any]]:
        """备源：中国天气网镜像（需城市代码），可拿 7 天预报与中文贴心提示。"""
        if not citykey:
            return None
        try:
            r = requests.get(
                _ITBOY_URL.format(citykey=citykey),
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                return None
            data = r.json().get("data") or {}
            forecast = (data.get("forecast") or [{}])[0]
            wendu = data.get("wendu")
            temp = None
            try:
                temp = int(float(wendu)) if wendu not in (None, "") else None
            except (TypeError, ValueError):
                temp = None
            if temp is None:
                # wendu 缺失时用当日高低温取中值
                temp = _avg_of(forecast.get("high"), forecast.get("low"))
            return {
                "city": (r.json().get("cityInfo") or {}).get("city") or "",
                "cond": str(forecast.get("type") or ""),
                "temp_c": temp,
                "humidity": _parse_humidity(data.get("shidu")),
                "notice": str(forecast.get("notice") or ""),
                "source": "itboy",
                "fetched_at": datetime.now().isoformat(timespec="minutes"),
            }
        except Exception:
            return None

    @staticmethod
    def _city_variants(city: str) -> Tuple[str, ...]:
        """城市名候选：原名 + 去掉行政区划后缀（"北京市" → "北京市", "北京"）。"""
        name = (city or "").strip()
        if not name:
            return ()
        variants = [name]
        for suffix in ("市", "省", "区", "县", "自治区", "特别行政区"):
            if name.endswith(suffix) and len(name) > len(suffix):
                variants.append(name[: -len(suffix)])
                break
        return tuple(dict.fromkeys(variants))

    # ----- 取数（可能耗时，调用方应放子线程）-----
    def fetch(self, city: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """取一份天气数据。返回结构必含 `level` 字段：live / cache / guess。

        - city 为 None：用默认（IP 定位/配置）城市，三级降级（live → 缓存 → 估算）。
        - city 指定时：一次性查该城市，跳过默认缓存的读取与写入（避免把别的城市
          当默认城市缓存），取数失败直接按该城市本地估算。
        """
        effective_city = city or self.ensure_city()

        if not force and city is None:
            cached = self.load_cache()
            if self.is_cache_fresh(cached):
                out = dict(cached or {})
                out["level"] = "cache"
                return out

        cfg = self.load_config()

        if city is None:
            # 默认城市：走完整三级降级
            live = self._fetch_wttr(effective_city)
            if live is None:
                live = self._fetch_itboy(str(cfg.get("citykey") or ""))
            if live is not None:
                live["level"] = "live"
                self.save_cache(live)
                return live
            cached = self.load_cache()
            if self.is_cache_usable(cached):
                out = dict(cached or {})
                out["level"] = "cache"
                out["stale"] = True
                return out
            return self._guess(effective_city)

        # 显式城市：只联网取一次，失败直接本地估算该城市，不污染默认缓存
        live = self._fetch_wttr(effective_city)
        if live is not None:
            live["level"] = "live"
            live["city"] = effective_city   # 以用户输入的城市名展示
            return live
        return self._guess(effective_city)

    def _guess(self, city: str) -> Dict[str, Any]:
        month = datetime.now().month
        low, high = _MONTH_TEMP.get(month, (15, 25))
        return {
            "city": city,
            "cond": "",
            "temp_c": (low + high) // 2,
            "temp_low": low,
            "temp_high": high,
            "source": "local-guess",
            "fetched_at": datetime.now().isoformat(timespec="minutes"),
            "level": "guess",
        }

    # ----- 文案 -----
    @staticmethod
    def _advice(data: Dict[str, Any]) -> str:
        """按天气给一句 BB 鼠口吻的贴心话（小仓鼠，天真、温暖、偶尔犯傻）。"""
        cond = str(data.get("cond") or "")
        temp = data.get("temp_c")
        feels = data.get("feels_c")
        # 体感比实测温度更能反映冷热，优先用它判断
        t = feels if isinstance(feels, int) else temp

        if "雪" in cond:
            return "下雪啦！吱吱，想堆雪人～你出门要小心路滑哦！"
        if "雷" in cond:
            return "打雷了呜呜，我有点怕怕，你别站在树下呀！"
        if "冰雹" in cond:
            return "下冰雹！快躲进屋，我帮你望风！"
        if "暴雨" in cond:
            return "雨好大好大！今天别出门啦，在家陪我玩吧～"
        if "雨" in cond:
            return "出门记得带伞哦，别淋成落汤鼠啦～吱吱"
        if "霾" in cond or "烟霾" in cond:
            return "外面灰蒙蒙的，记得戴口罩哦，护好小鼻子～"
        if "雾" in cond or "薄雾" in cond:
            return "起雾啦，走路慢吞吞的，注意安全哦！"
        if "结冰" in cond or "冻雨" in cond:
            return "地面会结冰，千万别跑跳，摔屁墩儿就不好啦！"
        if isinstance(t, int):
            if t >= 32:
                return "好热好热！我要躲进凉凉的窝里了…你也要多喝水哦！"
            if t <= 5:
                return "好冷好冷！我把自己卷成一颗毛球了，你也多穿点哦！"
            if t >= 26:
                return "有点热呢，喝口凉水歇一歇吧～"
        if "晴" in cond:
            return "今天天气超——棒！适合出去玩，带上我呀！"
        if "多云" in cond or "阴" in cond:
            return "不晒也不热，刚刚好～出去散散步？"
        return "今天也要开开心心的呀～吱吱"

    def report(self, data: Optional[Dict[str, Any]] = None) -> str:
        """把天气数据渲染成桌宠气泡文案（含降级标注）。"""
        if data is None:
            data = self.fetch()
        city = str(data.get("city") or "").strip()
        cond = str(data.get("cond") or "").strip()
        temp = data.get("temp_c")
        level = data.get("level") or "cache"

        if level == "guess":
            low, high = data.get("temp_low"), data.get("temp_high")
            where = city or "你那里"
            return (f"吱吱…连不上网，查不到{where}的天气啦。\n"
                    f"按 {datetime.now().month} 月估个大概：{low}~{high}℃吧～凑合看看哦！")

        feels = data.get("feels_c")
        lines = [f"{city}今天{cond}呀～" if cond else f"{city}的天气来啦～"]

        temp_s = f"{temp}℃" if isinstance(temp, int) else "温度未知"
        if isinstance(feels, int) and isinstance(temp, int) and feels != temp:
            temp_s += f"（体感 {feels}℃）"
        lines.append(temp_s)

        bits = []
        hum = data.get("humidity")
        if isinstance(hum, int):
            bits.append(f"湿度 {hum}%")
        wind = str(data.get("wind") or "").strip()
        if wind:
            bits.append(f"风 {wind}")
        if bits:
            lines.append(" · ".join(bits))

        notice = str(data.get("notice") or "").strip()
        lines.append(notice or self._advice(data))

        text = "\n".join(line for line in lines if line)

        # 只有过期缓存才标注；30 分钟内的新鲜缓存本身是准的，不必打扰用户
        if level == "cache" and data.get("stale"):
            ts = str(data.get("fetched_at") or "")
            time_s = ts[11:16] if len(ts) >= 16 else ""
            text += f"\n（连不上网，这是{' ' + time_s if time_s else ''}的旧数据）"
        return text


def _avg_of(high: Any, low: Any) -> Optional[int]:
    """从 '高温 30℃' / '低温 19℃' 解析并取中值；失败返回 None。"""
    try:
        h = re.search(r"(-?\d+)", str(high or ""))
        lo = re.search(r"(-?\d+)", str(low or ""))
        if h and lo:
            return (int(h.group(1)) + int(lo.group(1))) // 2
    except (TypeError, ValueError):
        pass
    return None
