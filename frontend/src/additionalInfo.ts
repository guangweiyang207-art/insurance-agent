import type { AdditionalInfo, AdditionalPolicy, AdditionalProduct, ClauseSource } from './types';

export function normalizeAdditionalInfo(raw: unknown): AdditionalInfo[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    if (looksLikePolicies(raw)) return policyInfo(raw);
    return productInfo(raw, inferProductTitle(raw));
  }
  if (typeof raw !== 'object') return [];

  const record = raw as Record<string, unknown>;
  const wrappedSources = record.clause_sources ?? record.sources;
  if (wrappedSources) {
    return sourceInfo(wrappedSources);
  }

  const wrappedProducts = record.plan_items ?? record.candidate_products ?? record.candidates_products;
  if (wrappedProducts) {
    return productInfo(wrappedProducts, record.plan_items ? '推荐方案产品' : '候选产品');
  }

  const wrappedPolicies = record.policies ?? record.policy_items;
  if (wrappedPolicies) {
    return policyInfo(wrappedPolicies);
  }

  if (looksLikePolicy(record)) {
    return policyInfo([record]);
  }

  return sourceInfo(record);
}

function sourceInfo(raw: unknown): AdditionalInfo[] {
  const sources = normalizeSources(raw);
  return sources.length ? [{ type: 'clause_sources', sources }] : [];
}

function productInfo(raw: unknown, title: string): AdditionalInfo[] {
  const products = normalizeProducts(raw);
  return products.length ? [{ type: 'products', title, products }] : [];
}

function policyInfo(raw: unknown): AdditionalInfo[] {
  const policies = normalizePolicies(raw);
  return policies.length ? [{ type: 'policies', title: '保单信息', policies }] : [];
}

function normalizeSources(raw: unknown): ClauseSource[] {
  const items = Array.isArray(raw) ? raw : Object.values(raw as Record<string, unknown>);
  return items
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((item) => ({
      ...item,
      source_id: String(item.source_id ?? ''),
    }))
    .filter((item) => item.source_id);
}

function normalizeProducts(raw: unknown): AdditionalProduct[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is AdditionalProduct => Boolean(item) && typeof item === 'object');
}

function normalizePolicies(raw: unknown): AdditionalPolicy[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is AdditionalPolicy =>
    Boolean(item) && typeof item === 'object' && looksLikePolicy(item as Record<string, unknown>),
  );
}

function looksLikePolicies(items: unknown[]): boolean {
  return items.some((item) =>
    Boolean(item) && typeof item === 'object' && looksLikePolicy(item as Record<string, unknown>),
  );
}

function looksLikePolicy(record: Record<string, unknown>): boolean {
  return Boolean(record.policy_number || record.effective_at || record.coverage_snapshot || record.policy_snapshot);
}

function inferProductTitle(items: unknown[]): string {
  const first = items.find((item) => Boolean(item) && typeof item === 'object') as
    | Record<string, unknown>
    | undefined;
  return first?.product_id ? '推荐方案产品' : '候选产品';
}

export function attachInfoToLastAssistantMessage<T extends { role: string; additionalInfo?: AdditionalInfo[] }>(
  messages: T[],
  info: AdditionalInfo[],
): T[] {
  if (info.length === 0) return messages;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      const next = [...messages];
      next[index] = {
        ...messages[index],
        additionalInfo: [...(messages[index].additionalInfo ?? []), ...info],
      };
      return next;
    }
  }
  return messages;
}
