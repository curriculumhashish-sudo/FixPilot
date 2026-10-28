import type { SecretObject } from './conversation';

/** ACP 服务器提供的一种模型； 镜子`openhands.sdk.agent.acp_models.ACPModelInfo`。*/
export interface ACPModelInfo {
  model_id: string;
  name?: string | null;
  description?: string | null;
}

export interface ACPModelDiscoveryError {
  /** `ACPAuthRequired`、`ACPStartupTimeout`、`ACPSpawnError` 或 `ACPInitError`。*/
  code: string;
  detail: string;
}

/** `POST /api/acp/models`的响应； 镜子`openhands.sdk.agent.acp_models.ACPModelDiscovery`。*/
export interface ACPModelDiscovery {
  agent_name: string | null;
  agent_version: string | null;
  /** 服务器自身对于给定的默认值凭据； 可以是别名，例如 `default`。*/
  current_model_id: string | null;
  available_models: ACPModelInfo[];
  supports_runtime_model_switch: boolean;
  error: ACPModelDiscoveryError | null;
}

export interface ACPModelDiscoveryRequest {
  agent_settings: {
    agent_kind: 'acp';
    acp_server: string;
    acp_command?: string[] | null;
    acp_args?: string[];
  };
  /** 与对话开始请求的 `secrets` 形状相同。*/
  secrets?: Record<string, SecretObject>;
  /** 再次询问服务器，而不是重复使用缓存的结果。*/
  refresh?: boolean;
}
