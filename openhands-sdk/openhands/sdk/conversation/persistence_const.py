import re


BASE_STATE = "base_state.json"
EVENTS_DIR = "events"
# 接受 5 位以上数字：书写器填充到最少 5 位数字，但不限制宽度。
EVENT_NAME_RE = re.compile(
    r"^event-(?P<idx>\d{5,})-(?P<event_id>[0-9a-fA-F\-]{8,})\.json$"
)
EVENT_FILE_PATTERN = "event-{idx:05d}-{event_id}.json"
