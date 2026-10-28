"""报告模型的最小 stdio ACP 服务器，用于模型发现测试。

``FAKE_ACP_MODELS`` 选择模型的报告方式：``config``（``model``configOptions 选择）或
``legacy``（
UNSTABLE``models`` 块）。 A
``FAKE_ACP_KEY`` 在环境中解锁 ``premium`` 模型； 与
``FAKE_ACP_REQUIRE_KEY`` 设置，``session/new`` 没有它就会失败。
"""

import json
import os
import sys
from typing import Any


MODELS = ["m1", "m2"] + (["premium"] if os.environ.get("FAKE_ACP_KEY") else [])


def respond(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        message["result"] = result if result is not None else {}
    else:
        message["error"] = error
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def model_select(current: str) -> dict[str, Any]:
    return {
        "id": "model",
        "name": "Model",
        "type": "select",
        "currentValue": current,
        "options": [{"value": m, "name": m.upper()} for m in MODELS],
    }


def new_session():
    if os.environ.get("FAKE_ACP_REQUIRE_KEY") and not os.environ.get("FAKE_ACP_KEY"):
        return None, {"code": -32000, "message": "Authentication required"}
    result: dict[str, Any] = {"sessionId": "fake-session"}
    if os.environ.get("FAKE_ACP_MODELS") == "legacy":
        result["models"] = {
            "currentModelId": "m1",
            "availableModels": [
                {"modelId": m, "name": m.upper(), "description": f"{m} model"}
                for m in MODELS
            ],
        }
    else:
        result["configOptions"] = [model_select("m1")]
    return result, None


def main():
    for line in sys.stdin:
        message = json.loads(line)
        request_id = message.get("id")
        if request_id is None:
            continue
        method = message["method"]
        params = message.get("params") or {}
        if method == "initialize":
            respond(
                request_id,
                {
                    "protocolVersion": 1,
                    "agentInfo": {"name": "fake-acp", "version": "1.2.3"},
                },
            )
        elif method == "session/new":
            result, error = new_session()
            respond(request_id, result, error)
        elif method in ("session/set_model", "session/set_config_option"):
            model = params.get("modelId") or params.get("value")
            if model not in MODELS:
                respond(request_id, error={"code": -32602, "message": "Unknown model"})
            elif method == "session/set_model":
                respond(request_id)
            else:
                respond(request_id, {"configOptions": [model_select(model)]})
        else:
            respond(request_id, error={"code": -32601, "message": "Method not found"})


if __name__ == "__main__":
    main()
