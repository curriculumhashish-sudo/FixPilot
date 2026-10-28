/** `GET /api/tools/catalog` 的一项； 镜子`openhands.sdk.tool.registry.ToolCatalogEntry`。*/
export interface ToolCatalogEntry {
  name: string;
  user_selectable: boolean;
  usable: boolean;
  description: string;
  /** 未设置 `tools` 的配置文件是否使该工具可用。*/
  in_default_set: boolean;
}

export interface ToolCatalogResponse {
  tools: ToolCatalogEntry[];
}
