"""Local dialogue and declarative animation specifications."""

CLICK_REACTIONS = (
    ("paw", "握个爪！"),
    ("happy", "嘿嘿，见到你真开心！"),
    ("bounce", "汪！接住我的小跳跃。"),
    ("look", "我在认真看着你哦。"),
)
AMBIENT_DIALOGUES = (
    ("你今天心情怎么样？", "我陪着你，汪！"),
    ("忙完了要不要玩球？", "右键丢球，我去捡！"),
    ("我刚才梦到零食了。", "闻起来可香啦！"),
    ("要不要休息一下？", "伸伸懒腰，摸摸我。"),
    ("猜猜我在想什么？", "当然是和你一起玩！"),
)
MOOD_DIALOGUES = {
    "quiet": (
        ("今天想安静地陪着你。", "我就在这里，汪。"),
        ("摸摸我会舒服一点。", "谢谢你陪我。"),
    ),
    "cheerful": (
        ("见到你我就想摇尾巴！", "再玩一会儿吧！"),
        ("今天超想和你玩球！", "我已经准备好去捡啦！"),
        ("和你待在一起真开心！", "汪！我们是好朋友。"),
    ),
}
CLOSE_DIALOGUES = (
    ("你一来我就认出你啦！", "最喜欢和你待在一起。"),
    ("我们已经是老朋友了！", "再陪我一会儿，汪。"),
)
IDLE_ACTIONS = ("idle_blink", "idle_glance", "idle_scratch")
IDLE_ACTION_DURATION = {
    "idle_blink": 0.24,
    "idle_glance": 1.35,
    "idle_scratch": 1.75,
}
# State entry, timed events and deformation are declared together. Empty
# entries deliberately have no decorative effects.
STATE_EFFECTS = {
    state: {}
    for state in (
        "idle",
        "idle_blink",
        "idle_glance",
        "idle_scratch",
        "look",
        "paw",
        "handshake_offer",
        "yawn",
        "lie",
        "fetch",
        "perch",
    )
}
STATE_EFFECTS.update(
    {
        "happy": {"mark": ("heart", 1.4), "particles": (("heart", 3, "head"),)},
        "handshake": {"mark": ("heart", 1.4), "particles": (("heart", 3, "head"),)},
        "play": {"mark": ("note", 1.6), "particles": (("note", 2, "head"),)},
        "annoyed": {"mark": ("anger", 1.6)},
        "dizzy": {"mark": ("star", None)},
        "sleep": {"mark": ("snot", None)},
        "drag": {"mark": ("exclaim", 0.8)},
        "bounce": {"deform": "bounce", "events": ((0.12, "takeoff"), (0.55, "bounce_land"))},
        "eat": {"deform": "eat", "events": ((0, "crumbs"), (0.65, "crumbs"))},
        "drop": {"landing": "drop_land"},
        "tumble": {"landing": "tumble_land"},
    }
)
EVENT_EFFECTS = {
    "drop_land": {"squash": (0.14, 0.25, "y"), "particles": (("dust", 4, "feet"),)},
    "tumble_land": {
        "squash": (0.22, 0.4, "y"),
        "particles": (("dust", 8, "feet"), ("star", 3, "head")),
    },
    "takeoff": {"particles": (("dust", 3, "feet"),)},
    "bounce_land": {"squash": (0.14, 0.25, "y"), "particles": (("dust", 5, "feet"),)},
    "fetch_stop": {"squash": (0.1, 0.25, "x")},
    "crumbs": {"particles": (("crumb", 5, "mouth"),)},
}
