// Shared with backend lib/role_families.py — keep these lists in sync.

export const ROLE_FAMILIES = [
  { value: "financial_analyst", label: "Financial Analyst" },
  { value: "software_engineer", label: "Software Engineer" },
  { value: "product_manager", label: "Product Manager" },
  { value: "data_scientist", label: "Data Scientist" },
  { value: "operations_manager", label: "Operations Manager" },
  { value: "marketing_manager", label: "Marketing Manager" },
  { value: "sales_executive", label: "Sales Executive" },
  { value: "hr_business_partner", label: "HR Business Partner" },
  { value: "legal_counsel", label: "Legal Counsel" },
  { value: "strategy_consultant", label: "Strategy Consultant" },
];

export const SENIORITY_LEVELS = [
  { value: "junior", label: "Junior (0–2 yrs)" },
  { value: "mid", label: "Mid-level (2–5 yrs)" },
  { value: "senior", label: "Senior (5–9 yrs)" },
  { value: "lead", label: "Lead / Principal (9+ yrs)" },
];

export const ROLE_FAMILY_BY_VALUE = Object.fromEntries(
  ROLE_FAMILIES.map((r) => [r.value, r.label]),
);

export const SENIORITY_BY_VALUE = Object.fromEntries(
  SENIORITY_LEVELS.map((s) => [s.value, s.label]),
);
