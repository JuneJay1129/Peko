"""
安慰打气（对话式）：分级语料 + 状态机驱动的引导式倾诉。

无 AI 也能实现多轮对话：桌宠每轮说话 + 选项按钮，用户点选推进；
自由文本输入通过关键词匹配分支。配了 AI 时由上层用模型生成每轮文本，
本模块负责状态推进与语料兜底。

4 阶段：intro(开场选主题) → empathize(共情倾听) → reframe(认知重塑/打气) → close(收尾)
4 主题：blame(被指责) / stress(压力) / down(低落) / cheer(打气)

兼容保留：should_comfort / build_comfort_text / active_care_text / trigger_words /
pick_comfort_states（快捷一次性安慰仍可用）。
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---- 触发关键词（nl_intent 与 should_comfort 共用）----
_TRIGGER_WORDS = (
    "好累", "太累", "累死", "压力", "焦虑", "崩溃", "撑不住", "扛不住",
    "喘不过气", "窒息", "内卷", "好卷", "被骂", "挨批", "被老师", "被老板",
    "被领导", "指责", "批评", "说教", "pua", "PUA", "甩锅", "背锅",
    "委屈", "难过", "伤心", "想哭", "emo", "EMO", "丧", "低气压",
    "安慰", "打气", "加油", "抱抱", "哄哄", "鼓励", "陪陪我", "陪我聊",
)
_NEGATIVE_HINTS = ("加油干", "加油写", "加油做")


# ---- 主题分级语料（每主题：empathize 共情 / reframe 认知重塑 / close 收尾）----
_TOPICS: Dict[str, Dict[str, Any]] = {
    "blame": {
        "label": "被指责 / 挨批了",
        "keywords": ("被骂", "挨批", "被老师", "被老板", "被领导", "指责", "批评", "说教", "pua", "PUA", "甩锅", "背锅"),
        "empathize": (
            "被那样说，心里肯定不好受。但那是别人的话，不能定义你。",
            "挨批的是事，不是你的全部。你已经很努力了。",
            "把那些难听的话先放一放，它们不该一直住你心里。",
            "被那样当众数落，谁都会难受，你不是玻璃心。",
            "这种事放谁身上都不好受，允许自己委屈一会儿。",
        ),
        "reframe": (
            "你不是那个「标签」，你只是今天遇到了一件难事。",
            "错的是那件事，不是你这个人的价值。",
            "下次再听到那些话，试着在心里回一句：这是我的事，不是我的全部。",
            "你不需要用别人的标准来审判自己，你已经够好了。",
            "一次做不好，不代表你不行；它只代表这次没成。",
        ),
        "close": (
            "把那些话留在今天吧，明天轻装出发。",
            "今天已经很难了，别再自己补刀了，抱抱你。",
            "去喝口水、伸个懒腰，那些话会慢慢淡掉的。",
            "把「不够好」那三个字从今天里删掉，明天重新算。",
            "你值得被好好对待，尤其是被你自己对待。",
        ),
    },
    "stress": {
        "label": "压力好大",
        "keywords": ("好累", "太累", "累死", "压力", "焦虑", "崩溃", "撑不住", "扛不住", "喘不过气", "窒息", "内卷", "好卷"),
        "empathize": (
            "压力大的时候，先停三秒，我陪你喘口气。",
            "你已经撑到现在了，真的很不容易。",
            "今天不用做超人，当个普通人也已经很棒了。",
            "事情堆成山的时候，先别急着爬，喘口气再出发。",
            "你已经连轴转很久了，累是正常的，不是矫情。",
        ),
        "reframe": (
            "任务再多，也是一个个完成的；先做眼下这一步就好。",
            "你已经把能做的都做了，剩下的是时间问题，不是你不够好。",
            "喘口气不是偷懒，是让接下来的路走得更稳。",
            "压力不是你不努力，是你扛的东西太多了。",
            "把大任务切成小块，先做完一小块，就算赢了一局。",
        ),
        "close": (
            "现在去喝口水、伸个懒腰吧，我等你回来。",
            "把今天的压力装进小盒子，明天再拆。",
            "你扛过的那些，最后都会变成你的底气。",
            "今天到此为止，剩下的交给明天的你。",
            "你已经尽力了，这就够了，剩下的交给时间。",
        ),
    },
    "down": {
        "label": "就是有点低落",
        "keywords": ("委屈", "难过", "伤心", "想哭", "emo", "EMO", "丧", "低气压", "低落", "不开心"),
        "empathize": (
            "有时候没来由地低落，也完全正常，不用逼自己立刻好起来。",
            "想哭就哭一会儿，眼泪也会累的。",
            "不用一直笑，我陪你安静待着也行。",
            "情绪低落的时候，连起床都是勇气，别责怪自己。",
            "今天提不起劲也没关系，我不催你。",
        ),
        "reframe": (
            "你不是不好，你只是需要休息一下。",
            "情绪会来，也会走，我就在这儿等它过去。",
            "今天允许自己「普通」一点，已经很勇敢了。",
            "低谷不会一直在，你也不会一直这样。",
            "允许自己「不行」一下，才能真的攒够力气。",
        ),
        "close": (
            "慢慢来，我会一直在你旁边。",
            "给自己一个抱抱，也让我抱抱你。",
            "明天醒来，说不定风就换方向了。",
            "在我这儿你不用强撑，随时可以靠一下。",
            "夜色再长，也会有天亮的时候，我陪你等。",
        ),
    },
    "cheer": {
        "label": "想打打气",
        "keywords": ("安慰", "打气", "加油", "抱抱", "哄哄", "鼓励", "陪陪我", "陪我聊", "坚持"),
        "empathize": (
            "先别急着证明自己，歇一口气不丢人。",
            "你来找我打气，说明你已经很努力了。",
            "吱吱先给你一个大大的抱抱！",
            "你能走到今天，靠的就是那股不服输的劲儿。",
            "你已经很努力了，这份努力值得被看见。",
        ),
        "reframe": (
            "你比你以为的更扛得住，真的。",
            "打气时间：你已经赢了今天的自己。",
            "加油不是为了别人，是为了不辜负这么拼的你。",
            "你比自己以为的更有力量，只是偶尔忘了。",
            "别人看结果，我看你这一路的不容易。",
        ),
        "close": (
            "去打气！你身后还有我呢，吱吱！",
            "带着这口气，去做今天想做的事吧。",
            "我永远站你这边，随时给你充电。",
            "带着这股劲，今天也会顺一点的，吱吱！",
            "我一直在这儿给你鼓掌，冲吧！",
        ),
    },
}


# ---- 开场 / 阶段引导 / 收尾框架 ----
_INTRO_OPENERS = (
    "感觉你有点不开心，我陪你坐会儿。现在心里是什么感觉？",
    "我猜你今天遇到什么事了。想跟我说说吗？先选一个最接近的吧：",
    "过来坐，把今天的事放一放。现在最难受的是哪种感觉？",
)
_EMPATHIZE_ASKS = (
    "愿意的话，跟我说说，发生了什么？",
    "我在听呢，慢慢说～",
    "嗯嗯，我在这儿，你说。",
)
_HEARD_LINES = (
    "嗯嗯，我听着呢。",
    "我懂，继续说。",
    "我在，不急着。",
)
_CLOSING_LINES = (
    "再陪你待一会儿，别怕。",
    "我今天会一直在旁边。",
    "抱抱你，会慢慢好起来的。",
)


# ---- 选项定义（框架层，与主题无关）----
_OPTIONS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "intro": (
        ("blame", "被指责 / 挨批了"),
        ("stress", "压力好大"),
        ("down", "就是有点低落"),
        ("cheer", "想打打气"),
    ),
    "empathize": (
        ("more", "继续说下去"),
        ("stuck", "说不清楚，心里堵"),
        ("small", "其实没多大事"),
        ("switch", "想换个心情"),
    ),
    "reframe": (
        ("hug", "再抱抱我"),
        ("stay", "陪我待会儿"),
        ("cheer", "好，去打气了"),
    ),
    "close": (
        ("stay_more", "再聊两句"),
        ("ok", "好呀"),
        ("done", "今天先这样"),
    ),
}

# 共情阶段的选项 → 认知重塑阶段的语气侧重（简单映射，先统一处理）
_STAGE_ORDER = ("intro", "empathize", "reframe", "close")


# ================= 兼容接口（一次性快捷安慰） =================

def trigger_words() -> Tuple[str, ...]:
    return _TRIGGER_WORDS


def should_comfort(text: str) -> bool:
    if not text:
        return False
    if any(h in text for h in _NEGATIVE_HINTS):
        return False
    return any(w in text for w in _TRIGGER_WORDS)


def _match_topic(text: str) -> str:
    for key, topic in _TOPICS.items():
        if any(k in text for k in topic["keywords"]):
            return key
    return ""


def build_comfort_text(user_text: str = "", ai_text: str = "") -> str:
    """一次性完整安慰文案（开场 → 暖心 → 收尾）。ai_text 非空时直接返回。"""
    user_text = (user_text or "").strip()
    ai_text = (ai_text or "").strip()
    if ai_text:
        return ai_text
    opener = random.choice(_LISTEN_OPENERS) if user_text else "我先抱你一下，再听你说。"
    topic = _match_topic(user_text)
    core = random.choice(_TOPICS[topic]["empathize"]) if topic else random.choice(_DEFAULT_PHRASES)
    closer = random.choice(_CLOSERS)
    return f"{opener}\n{core}\n{closer}"


_LISTEN_OPENERS = (
    "我在听呢，慢慢说～",
    "嗯嗯，我在这儿，你说。",
    "先深呼吸一下，我在。",
)
_CLOSERS = (
    "现在去喝口水、伸个懒腰吧，我等你回来。",
    "今天也要对自己好一点点哦。",
    "抱抱你，会慢慢好起来的。",
)
_DEFAULT_PHRASES = (
    "我在呢。不管发生什么，我都站你这边。",
    "先不急着想那些，让我陪你安静待一会儿。",
    "你已经做得很好了，剩下的慢慢来。",
    "难受就来跟我说说话，我都在。",
)


def active_care_text() -> str:
    """主动关心时用的轻量短句（温和低频）。"""
    return random.choice((
        "突然想跟你说：你今天辛苦了。",
        "不用一直那么拼，歇一歇也不会怎样。",
        "如果累了，就多靠着我一会儿吧。",
        "别太勉强自己，你已经做得很好了。",
    ))


def pick_comfort_states(available: Sequence[str]) -> List[str]:
    pool = set(available or [])
    order = ("listen", "stand", "wave", "longing")
    return [s for s in order if s in pool]


# ================= 对话式状态机 =================

def _pick_two(phrases: Sequence[str]) -> str:
    """从语料随机取 2 句（不重复）拼接成多行，让每轮话更充实。"""
    pool = list(phrases or ())
    if len(pool) >= 2:
        picked = random.sample(pool, 2)
    else:
        picked = pool
    return "\n".join(picked)


class ComfortSession:
    """引导式安慰对话状态机（纯 Python，可单测）。

    用法：
        s = ComfortSession()
        turn = s.start()                 # {'text','options','finished','stage'}
        turn = s.choose('blame')         # 点选项推进
        turn = s.respond('被老板骂了')    # 自由输入（关键词匹配）
    配 AI 时：用 context() 拿阶段上下文，由上层生成 text 覆盖。
    """

    def __init__(self):
        self.topic: Optional[str] = None
        self.stage: str = "intro"
        self.finished: bool = False

    # ---- 对外接口 ----
    def start(self) -> Dict[str, Any]:
        return self._turn(random.choice(_INTRO_OPENERS), _OPTIONS["intro"])

    def choose(self, option_id: str) -> Dict[str, Any]:
        """用户点击选项推进。"""
        if self.finished:
            return self._turn("", [], finished=True)
        if self.stage == "intro":
            return self._on_intro_choice(option_id)
        if self.stage == "empathize":
            return self._advance_to_reframe()
        if self.stage == "reframe":
            return self._advance_to_close()
        if self.stage == "close":
            return self._on_close_choice(option_id)
        return self._turn("", [], finished=True)

    def respond(self, text: str) -> Dict[str, Any]:
        """自由输入：关键词命中推进分支，否则回到当前选项。"""
        t = (text or "").strip()
        topic = _match_topic(t)
        if self.stage == "intro" and topic:
            return self.choose(topic)
        if self.stage == "empathize" and topic:
            self.topic = topic
            return self._advance_to_reframe()
        # 其余情况：承接一句，保留当前选项
        return self._turn(random.choice(_HEARD_LINES), _OPTIONS[self.stage])

    def context(self) -> str:
        """供 AI 生成每轮文本：当前主题与阶段描述。"""
        topic_label = _TOPICS.get(self.topic, {}).get("label", "低落")
        stage_label = {
            "intro": "开场（还不知道用户遇到什么）",
            "empathize": f"共情倾听（主题：{topic_label}）",
            "reframe": f"认知重塑/打气（主题：{topic_label}）",
            "close": f"收尾（主题：{topic_label}）",
        }.get(self.stage, self.stage)
        return f"安慰对话第{_STAGE_ORDER.index(self.stage) + 1}阶段：{stage_label}，请用 2~4 句温暖、简短、不说教的话回应。"

    # ---- 内部推进 ----
    def _on_intro_choice(self, option_id: str) -> Dict[str, Any]:
        if option_id not in _TOPICS:
            return self._turn("没看明白，你先选一个吧。", _OPTIONS["intro"])
        self.topic = option_id
        self.stage = "empathize"
        text = _pick_two(_TOPICS[option_id]["empathize"]) + "\n" + random.choice(_EMPATHIZE_ASKS)
        return self._turn(text, _OPTIONS["empathize"])

    def _advance_to_reframe(self) -> Dict[str, Any]:
        self.stage = "reframe"
        text = _pick_two(_TOPICS[self.topic]["reframe"])
        return self._turn(text, _OPTIONS["reframe"])

    def _advance_to_close(self) -> Dict[str, Any]:
        self.stage = "close"
        text = _pick_two(_TOPICS[self.topic]["close"])
        return self._turn(text, _OPTIONS["close"])

    def _on_close_choice(self, option_id: str) -> Dict[str, Any]:
        if option_id == "done":
            self.finished = True
            return self._turn("今天先陪你到这儿。记住，我一直都在。", [], finished=True)
        # 再聊两句 / 好呀：再来两句收尾，保持选项
        return self._turn(_pick_two(_TOPICS[self.topic]["close"]), _OPTIONS["close"])

    def _turn(self, text: str, options: Sequence[Tuple[str, str]], finished: bool = False) -> Dict[str, Any]:
        return {
            "text": (text or "").strip(),
            "options": [{"id": oid, "label": label} for oid, label in options],
            "finished": bool(finished),
            "stage": self.stage,
        }
