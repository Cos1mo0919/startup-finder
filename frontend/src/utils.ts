export function date(value: string | null | undefined, time = false) {
  return value
    ? new Intl.DateTimeFormat("uz-UZ", {
        timeZone: "Asia/Tashkent",
        day: "numeric",
        month: "long",
        year: "numeric",
        ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
      }).format(new Date(value))
    : "Hali mavjud emas";
}
export function time(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("uz-UZ", {
        timeZone: "Asia/Tashkent",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
}
