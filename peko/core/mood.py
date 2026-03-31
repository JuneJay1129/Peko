"""Stat system for desktop pets."""

from __future__ import annotations

import copy
import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from .runtime_paths import get_writable_root

BASELINE_MOOD = 58
DEFAULT_SATIETY = 68
DEFAULT_ENERGY = 68
DECAY_INTERVAL_MINUTES = 30
MOOD_DECAY_PER_STEP = 2
SATIETY_DECAY_PER_STEP = 4
ENERGY_DECAY_PER_STEP = 3
MAX_RECENT_ACTIONS = 6
MOOD_FILE_VERSION = 2


CONFIG_DIR = os.path.join(get_writable_root(module_file=__file__), "config")
MOOD_STATE_PATH = os.path.join(CONFIG_DIR, "mood_state.json")


@dataclass
class MoodSnapshot:
    pet_id: str
    mood_score: int = BASELINE_MOOD
    satiety: int = DEFAULT_SATIETY
    energy: int = DEFAULT_ENERGY
    updated_at: str = ""
    last_interaction: str = ""
    last_interaction_at: str = ""
    interaction_counts: Dict[str, int] = field(default_factory=dict)
    recent_actions: List[str] = field(default_factory=list)
    daily_date: str = ""
    daily_interactions: int = 0


@dataclass
class MoodOutcome:
    snapshot: MoodSnapshot
    interaction_id: str
    bubble: str
    suggested_state: Optional[str]
    hold_ms: int
    label: str
    description: str
    effect_items: List[Dict[str, str]]


INTERACTION_DEFS: Dict[str, Dict[str, Any]] = {
    "pet": {
        "label": "摸摸头",
        "hold_ms": 2200,
        "states": ["wave", "stand_1", "stand"],
        "bubbles": ["被摸摸了，好舒服呀。", "嘿嘿，再摸一下也可以。", "我有被你照顾到耶。"],
        "delta": {"mood": 8, "satiety": -1, "energy": 2},
    },
    "praise": {
        "label": "夸夸它",
        "hold_ms": 2400,
        "states": ["wave", "student", "stand"],
        "bubbles": ["真的在夸我吗，我要飘起来啦。", "听到夸夸，心情立刻亮起来了。", "我会继续努力陪着你的。"],
        "delta": {"mood": 10, "satiety": 0, "energy": 4},
    },
    "play": {
        "label": "陪它玩",
        "hold_ms": 2800,
        "states": ["fight", "wave", "walk_right", "walk_left"],
        "bubbles": ["来呀来呀，一起动起来。", "陪玩时间到，我超有精神。", "今天也想和你一起闹腾。"],
        "delta": {"mood": 14, "satiety": -10, "energy": -12},
    },
    "snack": {
        "label": "喂点心",
        "hold_ms": 2600,
        "states": ["cooking", "obese", "stand"],
        "bubbles": ["啊呜，这口点心太幸福了。", "小肚子被照顾到了。", "谢谢投喂，我会乖一点点。"],
        "delta": {"mood": 9, "satiety": 20, "energy": 6},
    },
    "rest": {
        "label": "让它休息",
        "hold_ms": 3400,
        "states": ["sleep", "lieDown", "tired", "stand"],
        "bubbles": ["我先缓一缓，等会儿继续陪你。", "安静躺一下，心情会慢慢回暖。", "谢谢你提醒我休息。"],
        "delta": {"mood": 5, "satiety": -4, "energy": 18},
    },
    "chat": {
        "label": "聊聊天",
        "hold_ms": 1800,
        "states": ["listen", "wave", "stand"],
        "bubbles": ["我已经竖起耳朵啦。", "想听你说话，现在就开始。", "来聊天吧，我在认真听。"],
        "delta": {"mood": 9, "satiety": -2, "energy": -3},
    },
}


def list_interaction_options() -> List[Dict[str, str]]:
    return [
        {"id": action_id, "label": cfg["label"]}
        for action_id, cfg in INTERACTION_DEFS.items()
    ]


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now()


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_iso(value: str) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _clamp_stat(value: Any, default: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return max(0, min(100, score))


def _clean_counts(raw: Any) -> Dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        try:
            cleaned[key] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return cleaned


def _clean_recent_actions(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)][-MAX_RECENT_ACTIONS:]


def snapshot_from_dict(pet_id: str, raw: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> MoodSnapshot:
    raw = raw or {}
    snapshot = MoodSnapshot(
        pet_id=pet_id,
        mood_score=_clamp_stat(raw.get("mood_score", BASELINE_MOOD), BASELINE_MOOD),
        satiety=_clamp_stat(raw.get("satiety", raw.get("hunger", DEFAULT_SATIETY)), DEFAULT_SATIETY),
        energy=_clamp_stat(raw.get("energy", DEFAULT_ENERGY), DEFAULT_ENERGY),
        updated_at=raw.get("updated_at", "") if isinstance(raw.get("updated_at", ""), str) else "",
        last_interaction=raw.get("last_interaction", "") if isinstance(raw.get("last_interaction", ""), str) else "",
        last_interaction_at=raw.get("last_interaction_at", "") if isinstance(raw.get("last_interaction_at", ""), str) else "",
        interaction_counts=_clean_counts(raw.get("interaction_counts")),
        recent_actions=_clean_recent_actions(raw.get("recent_actions")),
        daily_date=raw.get("daily_date", "") if isinstance(raw.get("daily_date", ""), str) else "",
        daily_interactions=max(0, int(raw.get("daily_interactions", 0) or 0)),
    )
    return refresh_snapshot(snapshot, now=now)


def _apply_time_decay(current: MoodSnapshot, steps: int) -> None:
    if steps <= 0:
        return

    current.satiety = _clamp_stat(current.satiety - (steps * SATIETY_DECAY_PER_STEP), DEFAULT_SATIETY)
    current.energy = _clamp_stat(current.energy - (steps * ENERGY_DECAY_PER_STEP), DEFAULT_ENERGY)

    adjustment = steps * MOOD_DECAY_PER_STEP
    if current.mood_score > BASELINE_MOOD:
        current.mood_score = max(BASELINE_MOOD, current.mood_score - adjustment)
    elif current.mood_score < BASELINE_MOOD:
        current.mood_score = min(BASELINE_MOOD, current.mood_score + adjustment)

    if current.satiety <= 15:
        current.mood_score = _clamp_stat(current.mood_score - min(steps * 3, 12), BASELINE_MOOD)
    elif current.satiety <= 30:
        current.mood_score = _clamp_stat(current.mood_score - min(steps * 2, 8), BASELINE_MOOD)

    if current.energy <= 15:
        current.mood_score = _clamp_stat(current.mood_score - min(steps * 3, 12), BASELINE_MOOD)
    elif current.energy <= 30:
        current.mood_score = _clamp_stat(current.mood_score - min(steps * 2, 8), BASELINE_MOOD)


def refresh_snapshot(snapshot: MoodSnapshot, now: Optional[datetime] = None) -> MoodSnapshot:
    current = copy.deepcopy(snapshot)
    current.mood_score = _clamp_stat(current.mood_score, BASELINE_MOOD)
    current.satiety = _clamp_stat(current.satiety, DEFAULT_SATIETY)
    current.energy = _clamp_stat(current.energy, DEFAULT_ENERGY)

    current_dt = _now(now)
    today = current_dt.date().isoformat()
    if current.daily_date != today:
        current.daily_date = today
        current.daily_interactions = 0

    updated_dt = _parse_iso(current.updated_at)
    if updated_dt is None:
        current.updated_at = _to_iso(current_dt)
        return current

    minutes = int(max(0, (current_dt - updated_dt).total_seconds()) // 60)
    steps = minutes // DECAY_INTERVAL_MINUTES
    _apply_time_decay(current, steps)
    if steps > 0:
        current.updated_at = _to_iso(current_dt)
    return current


def get_mood_label(score: int) -> str:
    if score < 30:
        return "低落"
    if score < 55:
        return "平静"
    if score < 80:
        return "开心"
    return "兴奋"


def get_satiety_label(satiety: int) -> str:
    if satiety < 20:
        return "快饿了"
    if satiety < 45:
        return "有点空腹"
    if satiety < 75:
        return "刚刚好"
    return "饱饱的"


def get_energy_label(energy: int) -> str:
    if energy < 20:
        return "快没电了"
    if energy < 45:
        return "有点困"
    if energy < 75:
        return "状态稳定"
    return "精神满满"


def get_mood_description(snapshot: MoodSnapshot) -> str:
    current = refresh_snapshot(snapshot)
    mood_label = get_mood_label(current.mood_score)
    satiety_label = get_satiety_label(current.satiety)
    energy_label = get_energy_label(current.energy)
    return f"现在是{mood_label}状态，{satiety_label}，{energy_label}。"


def get_daily_hint(snapshot: MoodSnapshot) -> str:
    current = refresh_snapshot(snapshot)
    if current.satiety <= 25:
        return "肚子开始咕咕叫了，喂点心会很有效。"
    if current.energy <= 30:
        return "我有点没电，让我休息一下会舒服很多。"
    if current.daily_interactions <= 0:
        return "今天还没互动，右边的按钮点一点吧。"
    if current.daily_interactions < 3:
        remain = 3 - current.daily_interactions
        return f"今天再陪我 {remain} 次，我会更有精神。"
    return "今天已经被你照顾得很好啦。"


def build_view(snapshot: MoodSnapshot, pet_name: str = "") -> Dict[str, Any]:
    current = refresh_snapshot(snapshot)
    action_id = current.last_interaction
    action_label = INTERACTION_DEFS.get(action_id, {}).get("label") if action_id else ""
    recent_text = action_label or "还没有记录"
    title_name = pet_name or current.pet_id
    return {
        "pet_name": title_name,
        "score": current.mood_score,
        "label": get_mood_label(current.mood_score),
        "description": get_mood_description(current),
        "recent_interaction": recent_text,
        "daily_hint": get_daily_hint(current),
        "satiety": current.satiety,
        "satiety_label": get_satiety_label(current.satiety),
        "energy": current.energy,
        "energy_label": get_energy_label(current.energy),
    }


def _repeat_multiplier(snapshot: MoodSnapshot, interaction_id: str) -> float:
    streak = 0
    for item in reversed(snapshot.recent_actions):
        if item != interaction_id:
            break
        streak += 1
    if streak <= 0:
        return 1.0
    if streak == 1:
        return 0.7
    if streak == 2:
        return 0.45
    return 0.25


def _pick_state(preferred_states: Sequence[str], available_states: Sequence[str]) -> Optional[str]:
    available = set(available_states)
    for state in preferred_states:
        if state in available:
            return state
    return None


def _pick_bubble(interaction_id: str, snapshot: MoodSnapshot) -> str:
    config = INTERACTION_DEFS[interaction_id]
    current = refresh_snapshot(snapshot)
    if interaction_id == "rest" and current.energy < 35:
        return "先让我充充电，马上就会精神回来。"
    if interaction_id == "snack" and current.satiety > 80:
        return "吃得刚刚好，肚子暖暖的。"
    if interaction_id == "play" and current.energy < 30:
        return "我会努力陪你玩，不过先别让我太累呀。"
    return random.choice(config["bubbles"])


def _format_effect_text(stat_name: str, delta: int) -> str:
    sign = "+" if delta > 0 else ""
    if stat_name == "mood":
        return f"{sign}{delta} 心情"
    if stat_name == "satiety":
        return f"{sign}{delta} 饥饿"
    return f"{sign}{delta} 精力"


def _effect_color(stat_name: str, delta: int) -> str:
    if stat_name == "mood":
        return "#d28e51" if delta >= 0 else "#c46a6a"
    if stat_name == "satiety":
        return "#6cb86f" if delta >= 0 else "#d48752"
    return "#5a91e0" if delta >= 0 else "#9c74d8"


def _build_effect_items(before: MoodSnapshot, after: MoodSnapshot) -> List[Dict[str, str]]:
    effect_items: List[Dict[str, str]] = []
    deltas = {
        "mood": after.mood_score - before.mood_score,
        "satiety": after.satiety - before.satiety,
        "energy": after.energy - before.energy,
    }
    for stat_name, delta in deltas.items():
        if delta == 0:
            continue
        effect_items.append(
            {
                "text": _format_effect_text(stat_name, delta),
                "color": _effect_color(stat_name, delta),
            }
        )
    return effect_items


def apply_interaction(
    snapshot: MoodSnapshot,
    interaction_id: str,
    available_states: Sequence[str],
    now: Optional[datetime] = None,
) -> MoodOutcome:
    if interaction_id not in INTERACTION_DEFS:
        raise KeyError(f"Unknown interaction: {interaction_id}")

    current_dt = _now(now)
    current = refresh_snapshot(snapshot, now=current_dt)
    config = INTERACTION_DEFS[interaction_id]
    multiplier = _repeat_multiplier(current, interaction_id)

    mood_delta = max(1, round(config["delta"]["mood"] * multiplier))
    satiety_delta = int(config["delta"]["satiety"])
    energy_delta = int(config["delta"]["energy"])

    if interaction_id == "snack" and current.satiety > 80:
        satiety_delta = min(10, satiety_delta // 2)
        mood_delta = max(1, mood_delta - 2)
    if interaction_id == "rest" and current.energy < 25:
        energy_delta += 6
        mood_delta += 2
    if interaction_id == "play" and current.energy < 35:
        mood_delta = max(2, mood_delta - 4)
        energy_delta -= 4
    if interaction_id == "play" and current.satiety < 25:
        mood_delta = max(2, mood_delta - 3)

    updated = copy.deepcopy(current)
    updated.mood_score = _clamp_stat(updated.mood_score + mood_delta, BASELINE_MOOD)
    updated.satiety = _clamp_stat(updated.satiety + satiety_delta, DEFAULT_SATIETY)
    updated.energy = _clamp_stat(updated.energy + energy_delta, DEFAULT_ENERGY)

    if updated.satiety <= 15:
        updated.mood_score = _clamp_stat(updated.mood_score - 4, BASELINE_MOOD)
    if updated.energy <= 15:
        updated.mood_score = _clamp_stat(updated.mood_score - 4, BASELINE_MOOD)

    updated.updated_at = _to_iso(current_dt)
    updated.last_interaction = interaction_id
    updated.last_interaction_at = updated.updated_at
    updated.daily_date = current_dt.date().isoformat()
    updated.daily_interactions = max(0, updated.daily_interactions) + 1
    updated.interaction_counts[interaction_id] = updated.interaction_counts.get(interaction_id, 0) + 1
    updated.recent_actions = (updated.recent_actions + [interaction_id])[-MAX_RECENT_ACTIONS:]

    return MoodOutcome(
        snapshot=updated,
        interaction_id=interaction_id,
        bubble=_pick_bubble(interaction_id, updated),
        suggested_state=_pick_state(config["states"], available_states),
        hold_ms=int(config["hold_ms"]),
        label=get_mood_label(updated.mood_score),
        description=get_mood_description(updated),
        effect_items=_build_effect_items(current, updated),
    )


def build_idle_bubble(snapshot: MoodSnapshot, pet_name: str = "") -> str:
    current = refresh_snapshot(snapshot)
    display_name = pet_name or current.pet_id

    if current.satiety <= 20:
        options = [
            f"{display_name} 的肚子有点空空的。",
            "我开始饿啦，喂点心会很开心。",
            "如果现在有零食，我会立刻贴贴你。",
        ]
    elif current.energy <= 25:
        options = [
            "我有点犯困了，想小睡一下。",
            "能量快见底啦，让我休息一会儿吧。",
            "现在更适合安安静静靠着你。",
        ]
    elif current.mood_score < 30:
        options = [
            f"{display_name} 想被你注意一下。",
            "抱抱我一下也可以吗。",
            "有点蔫蔫的，陪我聊聊吧。",
        ]
    elif current.mood_score < 55:
        options = [
            "我在旁边安安静静陪着你。",
            "状态还不错，想和你轻轻互动一下。",
            "右键点我，可以一起玩一会儿。",
        ]
    elif current.mood_score < 80:
        options = [
            "今天心情不错，想找你玩。",
            "被你陪着的时候，我会更开心。",
            "如果现在摸摸我，我会更有精神。",
        ]
    else:
        options = [
            "能量满格，随时准备和你一起冲。",
            "今天超开心，想和你热闹一下。",
            "右键点我，我还有好多活力没用完。",
        ]
    return random.choice(options)


def build_chat_context(snapshot: MoodSnapshot, pet_name: str = "") -> str:
    current = refresh_snapshot(snapshot)
    title_name = pet_name or current.pet_id
    last_action = INTERACTION_DEFS.get(current.last_interaction, {}).get("label") or "暂无"
    return (
        f"当前你扮演的宠物叫 {title_name}。"
        f"它的心情是“{get_mood_label(current.mood_score)}”，心情值 {current.mood_score}/100。"
        f"它的饱食度是 {current.satiety}/100（{get_satiety_label(current.satiety)}），"
        f"精力值是 {current.energy}/100（{get_energy_label(current.energy)}）。"
        f"最近一次互动是“{last_action}”。"
        "请在回答里自然体现这种状态，保持可爱、简短、像在陪伴用户。"
    )


def expand_action_pool_by_mood(snapshot: MoodSnapshot, pool: Sequence[str]) -> List[str]:
    current = refresh_snapshot(snapshot)
    weighted: List[str] = []
    for state in pool:
        weight = 1

        if current.satiety <= 30:
            if state in {"cooking", "stand"}:
                weight += 4
            elif state in {"fight", "walk_left", "walk_right", "walk_up", "walk_down"}:
                weight = max(1, weight - 0)

        if current.energy <= 30:
            if state in {"sleep", "lieDown", "tired", "stand"}:
                weight += 5
            elif state in {"fight", "walk_left", "walk_right", "walk_up", "walk_down"}:
                weight += 0

        if current.mood_score < 30:
            if state in {"sleep", "lieDown", "tired", "sulk", "cry"}:
                weight += 4
            elif state == "stand":
                weight += 2
        elif current.mood_score < 55:
            if state in {"stand", "listen", "student"}:
                weight += 3
        elif current.mood_score < 80:
            if state in {"wave", "cooking", "walk_left", "walk_right", "walk_up", "walk_down"}:
                weight += 3
            elif state == "stand":
                weight += 1
        else:
            if state in {"wave", "fight", "walk_left", "walk_right", "walk_up", "walk_down"}:
                weight += 4
            elif state == "stand":
                weight += 1

        weighted.extend([state] * max(1, weight))
    return weighted or list(pool)


class MoodStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or MOOD_STATE_PATH

    def _load_file(self) -> Dict[str, Any]:
        if not self.path or not os.path.isfile(self.path):
            return {"version": MOOD_FILE_VERSION, "pets": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {"version": MOOD_FILE_VERSION, "pets": {}}
        if not isinstance(data, dict):
            return {"version": MOOD_FILE_VERSION, "pets": {}}
        pets = data.get("pets")
        if not isinstance(pets, dict):
            pets = {}
        return {
            "version": data.get("version", MOOD_FILE_VERSION),
            "pets": pets,
        }

    def load(self, pet_id: str, now: Optional[datetime] = None) -> MoodSnapshot:
        data = self._load_file()
        raw = data.get("pets", {}).get(pet_id)
        return snapshot_from_dict(pet_id, raw, now=now)

    def save(self, snapshot: MoodSnapshot) -> None:
        current = refresh_snapshot(snapshot)
        data = self._load_file()
        pets = data.setdefault("pets", {})
        pets[current.pet_id] = asdict(current)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)


class MoodEngine:
    def __init__(self, pet_id: str, store: Optional[MoodStore] = None):
        self.pet_id = pet_id
        self.store = store or MoodStore()
        self.snapshot = self.store.load(pet_id)

    def refresh(self) -> MoodSnapshot:
        self.snapshot = refresh_snapshot(self.snapshot)
        return self.snapshot

    def save(self) -> None:
        self.store.save(self.refresh())

    def get_view(self, pet_name: str = "") -> Dict[str, Any]:
        self.snapshot = refresh_snapshot(self.snapshot)
        return build_view(self.snapshot, pet_name=pet_name)

    def get_idle_bubble(self, pet_name: str = "") -> str:
        self.snapshot = refresh_snapshot(self.snapshot)
        return build_idle_bubble(self.snapshot, pet_name=pet_name)

    def get_chat_context(self, pet_name: str = "") -> str:
        self.snapshot = refresh_snapshot(self.snapshot)
        return build_chat_context(self.snapshot, pet_name=pet_name)

    def expand_auto_action_pool(self, pool: Sequence[str]) -> List[str]:
        self.snapshot = refresh_snapshot(self.snapshot)
        return expand_action_pool_by_mood(self.snapshot, pool)

    def get_interaction_options(self) -> List[Dict[str, str]]:
        return list_interaction_options()

    def apply_interaction(self, interaction_id: str, available_states: Sequence[str]) -> MoodOutcome:
        outcome = apply_interaction(self.snapshot, interaction_id, available_states)
        self.snapshot = outcome.snapshot
        self.store.save(self.snapshot)
        return outcome
