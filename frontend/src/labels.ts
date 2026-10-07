export const audienceLabels: Record<string, string> = {
  individual: "Jismoniy shaxslar",
  business: "Yuridik shaxslar",
  both: "Ikkalasi uchun",
  unknown: "Aniqlanmagan",
};
export const statusLabels: Record<string, string> = {
  completed: "Yakunlandi",
  partial: "Qisman bajarildi",
  failed: "Xatolik",
  running: "Qidirilmoqda",
  interrupted: "Uzilib qolgan",
};
export const countLabels: Record<string, string> = {
  sources_checked: "Tekshirilgan manbalar",
  candidates_found: "Topilgan URL",
  candidates: "Qayta ishlangan nomzodlar",
  processed_ai: "AI bilan ishlangan",
  processed_fallback: "Qoidalar bilan ishlangan",
  event_projects: "Tadbir orqali yangi loyihalar",
  university_projects: "Universitet orqali yangi loyihalar",
  ai_errors: "AI xatolari",
  translation_errors: "Tarjima xatolari",
  rejected: "Rad etilgan",
  duplicates: "Birlashtirilgan dublikatlar",
  new_projects: "Yangi loyihalar",
  pending: "Tahlil kutilmoqda",
};
export const errorLabels: Record<string, string> = {
  requires_api_key: "Qidiruv API kaliti kerak",
  event_requires_search_key: "Tadbir bo‘yicha qidiruv kaliti kerak",
  article_body_missing: "Maqola matni ajratilmadi",
  source_requires_configuration: "Manba adapterini sozlash kerak",
  translation_not_uzbek: "Tarjima o‘zbekcha tekshiruvdan o‘tmadi",
  fact_translation_not_uzbek: "Fakt tarjimasi o‘zbekcha emas",

  network_unavailable: "Manbaga ulanish imkoni bo‘lmadi",
  search_unavailable: "Qidiruv xizmati mavjud emas",
  robots_disallowed: "Manba avtomatik o‘qishga ruxsat bermadi",
  invalid_feed: "RSS formati mos kelmadi",
  ai_unavailable_or_invalid: "AI javobi olinmadi yoki tekshiruvdan o‘tmadi",
  processing_failed: "Materialni qayta ishlashda xatolik",
  pipeline_failed: "Qidiruv yakunlanmadi",
  previous_run_interrupted: "Oldingi qidiruv uzilib qolgan",
  dns_failed: "Manba manzili aniqlanmadi",
};
