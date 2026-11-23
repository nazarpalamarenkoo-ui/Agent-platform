export function plural(count: number, forms: readonly [string, string, string]): string {
  const n = Math.abs(count) % 100
  const last = n % 10
  if (n > 10 && n < 20) return forms[2]
  if (last === 1) return forms[0]
  if (last >= 2 && last <= 4) return forms[1]
  return forms[2]
}

export function countLabel(count: number, forms: readonly [string, string, string]): string {
  return `${count} ${plural(count, forms)}`
}

export const SKILL_FORMS = ["skill", "skills", "skill"] as const
export const TOOL_FORMS = ["tool", "tools", "tools"] as const
export const PACK_FORMS = ["knowledge base", "knowledges bases", "knowledge bases"] as const