from enum import StrEnum


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ChannelType(StrEnum):
    TEXT = "text"
    VOICE = "voice"
