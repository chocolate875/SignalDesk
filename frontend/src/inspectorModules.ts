import { useCallback, useEffect, useState } from "react";

/** 右侧「综合研判」面板的所有可配置功能模块标识 */
export type InspectorModuleId =
  | "forecast"
  | "wave_trend"
  | "extended_hours"
  | "plan_range"
  | "daily_score"
  | "valuation_profile"
  | "risk_check";

/** 模块注册表元信息 */
export interface InspectorModuleMeta {
  id: InspectorModuleId;
  title: string;
  desc: string;
  /** 是否依赖特定数据存在才渲染卡片（例如盘外动态） */
  conditional?: boolean;
}

/**
 * 右侧综合研判默认模块顺序：
 * 优先将「买卖点位评级」与「波浪与趋势分析」置顶，便于 16:9 首屏直览核心买卖结构。
 */
export const INSPECTOR_MODULES: readonly InspectorModuleMeta[] = [
  {
    id: "forecast",
    title: "买卖点位评级",
    desc: "参考买卖区间、止损赔率、四维评级与风控警示",
  },
  {
    id: "wave_trend",
    title: "波浪与趋势分析",
    desc: "平行趋势通道、波浪拐点、失效位与斐波那契测算",
  },
  {
    id: "extended_hours",
    title: "盘外动态",
    desc: "夜盘 / 盘前 / 盘后异动结论与三段明细",
    conditional: true,
  },
  {
    id: "plan_range",
    title: "长期计划价位",
    desc: "个人失效价、持仓成本与目标观察价区间进度",
  },
  {
    id: "daily_score",
    title: "日线结构评分",
    desc: "趋势 / 动量 / 量价三维得分与原始技术指标",
  },
  {
    id: "valuation_profile",
    title: "估值与资产特征",
    desc: "个股 PE/美债对照，ETF 自动展示波动与回撤特征",
  },
  {
    id: "risk_check",
    title: "独立风险检查",
    desc: "独立技术规则与基础数据完整性检查",
  },
] as const;

export const INSPECTOR_MODULE_MAP: Record<
  InspectorModuleId,
  InspectorModuleMeta
> = Object.fromEntries(
  INSPECTOR_MODULES.map((item) => [item.id, item]),
) as Record<InspectorModuleId, InspectorModuleMeta>;

export const DEFAULT_INSPECTOR_ORDER: InspectorModuleId[] =
  INSPECTOR_MODULES.map((m) => m.id);

export interface InspectorLayoutConfig {
  order: InspectorModuleId[];
  hidden: InspectorModuleId[];
}

export const DEFAULT_INSPECTOR_LAYOUT: InspectorLayoutConfig = {
  order: [...DEFAULT_INSPECTOR_ORDER],
  hidden: [],
};

export const INSPECTOR_LAYOUT_STORAGE_KEY = "signaldesk:inspector-layout:v1";

const VALID_IDS = new Set<string>(DEFAULT_INSPECTOR_ORDER);

/** 清洗并补全本地持久化配置，确保未知或缺失模块不会导致异常 */
export function normalizeInspectorLayout(
  raw: unknown,
): InspectorLayoutConfig {
  if (!raw || typeof raw !== "object") {
    return { order: [...DEFAULT_INSPECTOR_ORDER], hidden: [] };
  }
  const record = raw as { order?: unknown; hidden?: unknown };

  const order: InspectorModuleId[] = [];
  const seen = new Set<InspectorModuleId>();
  if (Array.isArray(record.order)) {
    for (const item of record.order) {
      if (typeof item === "string" && VALID_IDS.has(item)) {
        const id = item as InspectorModuleId;
        if (!seen.has(id)) {
          seen.add(id);
          order.push(id);
        }
      }
    }
  }
  // 将未来新增或配置中遗漏的模块按默认顺序补齐至末尾
  for (const id of DEFAULT_INSPECTOR_ORDER) {
    if (!seen.has(id)) {
      seen.add(id);
      order.push(id);
    }
  }

  const hidden: InspectorModuleId[] = [];
  const hiddenSeen = new Set<InspectorModuleId>();
  if (Array.isArray(record.hidden)) {
    for (const item of record.hidden) {
      if (typeof item === "string" && VALID_IDS.has(item)) {
        const id = item as InspectorModuleId;
        if (!hiddenSeen.has(id)) {
          hiddenSeen.add(id);
          hidden.push(id);
        }
      }
    }
  }

  return { order, hidden };
}

/** 切换单个模块的显示/隐藏状态 */
export function toggleInspectorModule(
  cfg: InspectorLayoutConfig,
  id: InspectorModuleId,
): InspectorLayoutConfig {
  const isHidden = cfg.hidden.includes(id);
  return {
    order: cfg.order,
    hidden: isHidden
      ? cfg.hidden.filter((item) => item !== id)
      : [...cfg.hidden, id],
  };
}

/** 按步进上移（-1）或下移（+1）指定模块 */
export function moveInspectorModule(
  cfg: InspectorLayoutConfig,
  id: InspectorModuleId,
  delta: -1 | 1,
): InspectorLayoutConfig {
  const idx = cfg.order.indexOf(id);
  if (idx < 0) return cfg;
  const target = idx + delta;
  if (target < 0 || target >= cfg.order.length) return cfg;
  const next = [...cfg.order];
  const [moved] = next.splice(idx, 1);
  next.splice(target, 0, moved);
  return { order: next, hidden: cfg.hidden };
}

/** 拖拽重排：将 fromId 移动至 toId 所在位置 */
export function reorderInspectorModule(
  cfg: InspectorLayoutConfig,
  fromId: InspectorModuleId,
  toId: InspectorModuleId,
): InspectorLayoutConfig {
  if (fromId === toId) return cfg;
  const fromIdx = cfg.order.indexOf(fromId);
  const toIdx = cfg.order.indexOf(toId);
  if (fromIdx < 0 || toIdx < 0) return cfg;
  const next = [...cfg.order];
  const [moved] = next.splice(fromIdx, 1);
  next.splice(toIdx, 0, moved);
  return { order: next, hidden: cfg.hidden };
}

function readStoredLayout(): InspectorLayoutConfig {
  try {
    const raw = window.localStorage.getItem(INSPECTOR_LAYOUT_STORAGE_KEY);
    if (!raw) return { order: [...DEFAULT_INSPECTOR_ORDER], hidden: [] };
    return normalizeInspectorLayout(JSON.parse(raw));
  } catch {
    return { order: [...DEFAULT_INSPECTOR_ORDER], hidden: [] };
  }
}

/** 管理右侧模块显示开关、排序与本地持久化的状态 Hook */
export function useInspectorLayout() {
  const [layout, setLayout] = useState<InspectorLayoutConfig>(readStoredLayout);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        INSPECTOR_LAYOUT_STORAGE_KEY,
        JSON.stringify(layout),
      );
    } catch {
      // 隐私模式或存储受限时静默保持内存态
    }
  }, [layout]);

  const toggle = useCallback((id: InspectorModuleId) => {
    setLayout((prev) => toggleInspectorModule(prev, id));
  }, []);

  const move = useCallback((id: InspectorModuleId, delta: -1 | 1) => {
    setLayout((prev) => moveInspectorModule(prev, id, delta));
  }, []);

  const reorder = useCallback(
    (fromId: InspectorModuleId, toId: InspectorModuleId) => {
      setLayout((prev) => reorderInspectorModule(prev, fromId, toId));
    },
    [],
  );

  const reset = useCallback(() => {
    setLayout({ order: [...DEFAULT_INSPECTOR_ORDER], hidden: [] });
  }, []);

  const showAll = useCallback(() => {
    setLayout((prev) => ({ order: prev.order, hidden: [] }));
  }, []);

  return { layout, toggle, move, reorder, reset, showAll };
}
