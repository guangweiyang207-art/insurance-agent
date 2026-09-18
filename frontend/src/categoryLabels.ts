export const CATEGORY_LABELS: Record<string, string> = {
  critical_illness: '重疾险',
  medical: '百万医疗险',
  accident: '意外险',
  life: '寿险',
};

export function formatCategoryLabel(value: unknown): string {
  if (value === null || value === undefined) return '保险产品';
  const key = String(value);
  return CATEGORY_LABELS[key] ?? key;
}
