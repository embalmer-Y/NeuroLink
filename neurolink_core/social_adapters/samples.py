from __future__ import annotations

from copy import deepcopy
from typing import Any


QQ_OFFICIAL_GROUP_MESSAGE_SAMPLE: dict[str, Any] = {
    "id": "qq-msg-sample-001",
    "group_id": "group-qq-001",
    "channel_id": "group-qq-001",
    "author": {"id": "alice"},
    "member": {"user": {"id": "alice"}, "roles": ["member"]},
    "content": "@NeuroLink please check current status",
    "mentions": [{"id": "bot-neurolink"}],
}


QQ_OFFICIAL_GROUP_MESSAGE_NO_MENTION_SAMPLE: dict[str, Any] = {
    "id": "qq-msg-sample-002",
    "group_id": "group-qq-001",
    "channel_id": "group-qq-001",
    "author": {"id": "alice"},
    "member": {"user": {"id": "alice"}, "roles": ["member"]},
    "content": "please check current status",
    "mentions": [],
}


QQ_OFFICIAL_DIRECT_MESSAGE_SAMPLE: dict[str, Any] = {
    "id": "qq-dm-sample-001",
    "direct_message_id": "dm-qq-001",
    "author": {"id": "alice"},
    "content": "please check my direct message status",
    "mentions": [],
}


ONEBOT_QQ_GROUP_MESSAGE_SAMPLE: dict[str, Any] = {
    "message_id": "onebot-msg-sample-001",
    "message_type": "group",
    "group_id": 42,
    "user_id": 1001,
    "self_id": 2002,
    "sender": {"role": "admin", "nickname": "alice"},
    "share_session_in_group": True,
    "message": [
        {"type": "at", "data": {"qq": "2002"}},
        {"type": "text", "data": {"text": " please"}},
        {"type": "text", "data": {"text": " check current status"}},
    ],
}


ONEBOT_QQ_GROUP_MESSAGE_NO_MENTION_SAMPLE: dict[str, Any] = {
    "message_id": "onebot-msg-sample-002",
    "message_type": "group",
    "group_id": 42,
    "user_id": 1001,
    "self_id": 2002,
    "sender": {"role": "member", "nickname": "alice"},
    "share_session_in_group": False,
    "message": [
        {"type": "text", "data": {"text": "please"}},
        {"type": "text", "data": {"text": "check current status"}},
    ],
}


ONEBOT_QQ_DIRECT_MESSAGE_SAMPLE: dict[str, Any] = {
    "message_id": "onebot-dm-sample-001",
    "message_type": "private",
    "user_id": 1001,
    "self_id": 2002,
    "sender": {"role": "friend", "nickname": "alice"},
    "share_session_in_group": False,
    "message": [
        {"type": "text", "data": {"text": "please"}},
        {"type": "text", "data": {"text": "check my direct status"}},
    ],
}


WECOM_GROUP_MESSAGE_SAMPLE: dict[str, Any] = {
    "msgid": "wecom-msg-sample-001",
    "conversation_type": "group",
    "roomid": "wecom-room-001",
    "from": "alice",
    "text": "@NeuroLink please check current status",
    "mentioned_list": ["neuro_bot"],
}


WECOM_GROUP_MESSAGE_NO_MENTION_SAMPLE: dict[str, Any] = {
    "msgid": "wecom-msg-sample-002",
    "conversation_type": "group",
    "roomid": "wecom-room-001",
    "from": "alice",
    "text": "please check current status",
    "mentioned_list": [],
}


WECOM_DIRECT_MESSAGE_SAMPLE: dict[str, Any] = {
    "msgid": "wecom-dm-sample-001",
    "conversation_type": "single",
    "from": "alice",
    "text": "please check my direct message status",
    "mentioned_list": [],
}


WECHAT_ILINK_GROUP_MESSAGE_SAMPLE: dict[str, Any] = {
    "msg_id": "wechat-ilink-msg-sample-001",
    "scene": "group",
    "room_id": "wechat-room-001",
    "from_user": "alice",
    "text": "please check current status",
    "mentioned_list": ["neuro_bot"],
    "share_session_in_group": True,
}


WECHAT_ILINK_GROUP_MESSAGE_NO_MENTION_SAMPLE: dict[str, Any] = {
    "msg_id": "wechat-ilink-msg-sample-002",
    "scene": "group",
    "room_id": "wechat-room-001",
    "from_user": "alice",
    "text": "please check current status",
    "mentioned_list": [],
    "share_session_in_group": False,
}


WECHAT_ILINK_DIRECT_MESSAGE_SAMPLE: dict[str, Any] = {
    "msg_id": "wechat-ilink-dm-sample-001",
    "scene": "direct",
    "from_user": "alice",
    "text": "please check my direct status",
    "mentioned_list": [],
    "share_session_in_group": False,
}


QQ_OPENCLAW_GROUP_MESSAGE_SAMPLE: dict[str, Any] = {
    "msg_id": "qq-openclaw-msg-sample-001",
    "scene": "group",
    "room_id": "qq-openclaw-room-001",
    "from_user": "alice",
    "text": "please check current status",
    "mentioned_list": ["neuro_bot"],
    "share_session_in_group": True,
    "plugin_id": "qq_openclaw",
    "plugin_package": "operator-supplied-qq-openclaw-package",
    "installer_package": "operator-supplied-qq-openclaw-installer",
}


QQ_OPENCLAW_GROUP_MESSAGE_NO_MENTION_SAMPLE: dict[str, Any] = {
    "msg_id": "qq-openclaw-msg-sample-002",
    "scene": "group",
    "room_id": "qq-openclaw-room-001",
    "from_user": "alice",
    "text": "please check current status",
    "mentioned_list": [],
    "share_session_in_group": False,
    "plugin_id": "qq_openclaw",
}


QQ_OPENCLAW_DIRECT_MESSAGE_SAMPLE: dict[str, Any] = {
    "msg_id": "qq-openclaw-dm-sample-001",
    "scene": "direct",
    "from_user": "alice",
    "text": "please check my direct status",
    "mentioned_list": [],
    "share_session_in_group": False,
    "plugin_id": "qq_openclaw",
    "plugin_package": "operator-supplied-qq-openclaw-package",
}


def qq_official_group_message_sample() -> dict[str, Any]:
    return deepcopy(QQ_OFFICIAL_GROUP_MESSAGE_SAMPLE)


def qq_official_group_message_no_mention_sample() -> dict[str, Any]:
    return deepcopy(QQ_OFFICIAL_GROUP_MESSAGE_NO_MENTION_SAMPLE)


def qq_official_direct_message_sample() -> dict[str, Any]:
    return deepcopy(QQ_OFFICIAL_DIRECT_MESSAGE_SAMPLE)


def onebot_group_message_sample() -> dict[str, Any]:
    return deepcopy(ONEBOT_QQ_GROUP_MESSAGE_SAMPLE)


def onebot_group_message_no_mention_sample() -> dict[str, Any]:
    return deepcopy(ONEBOT_QQ_GROUP_MESSAGE_NO_MENTION_SAMPLE)


def onebot_direct_message_sample() -> dict[str, Any]:
    return deepcopy(ONEBOT_QQ_DIRECT_MESSAGE_SAMPLE)


def wecom_group_message_sample() -> dict[str, Any]:
    return deepcopy(WECOM_GROUP_MESSAGE_SAMPLE)


def wecom_group_message_no_mention_sample() -> dict[str, Any]:
    return deepcopy(WECOM_GROUP_MESSAGE_NO_MENTION_SAMPLE)


def wecom_direct_message_sample() -> dict[str, Any]:
    return deepcopy(WECOM_DIRECT_MESSAGE_SAMPLE)


def wechat_ilink_group_message_sample() -> dict[str, Any]:
    return deepcopy(WECHAT_ILINK_GROUP_MESSAGE_SAMPLE)


def wechat_ilink_group_message_no_mention_sample() -> dict[str, Any]:
    return deepcopy(WECHAT_ILINK_GROUP_MESSAGE_NO_MENTION_SAMPLE)


def wechat_ilink_direct_message_sample() -> dict[str, Any]:
    return deepcopy(WECHAT_ILINK_DIRECT_MESSAGE_SAMPLE)


def qq_openclaw_group_message_sample() -> dict[str, Any]:
    return deepcopy(QQ_OPENCLAW_GROUP_MESSAGE_SAMPLE)


def qq_openclaw_group_message_no_mention_sample() -> dict[str, Any]:
    return deepcopy(QQ_OPENCLAW_GROUP_MESSAGE_NO_MENTION_SAMPLE)


def qq_openclaw_direct_message_sample() -> dict[str, Any]:
    return deepcopy(QQ_OPENCLAW_DIRECT_MESSAGE_SAMPLE)