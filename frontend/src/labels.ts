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
  candidates: "Topilgan nomzodlar",
  rejected: "Rad etilgan",
  duplicates: "Birlashtirilgan dublikatlar",
  new_projects: "Yangi loyihalar",
  pending: "Tahlil kutilmoqda",
};
export const errorLabels: Record<string, string> = {
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
