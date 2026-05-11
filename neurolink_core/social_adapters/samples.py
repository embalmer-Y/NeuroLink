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