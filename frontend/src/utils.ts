const months = [
  "yanvar",
  "fevral",
  "mart",
  "aprel",
  "may",
  "iyun",
  "iyul",
  "avgust",
  "sentabr",
  "oktabr",
  "noyabr",
  "dekabr",
];

// Obtain numeric Tashkent components independently of Uzbek ICU/CLDR support.
// Some browsers fall back to synthetic month names such as M03 for uz-UZ.
const formatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Tashkent",
  calendar: "gregory",
  numberingSystem: "latn",
  day: "numeric",
  month: "numeric",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
function parts(value: string | null | undefined) {
  if (!value) return null;
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return null;
  return Object.fromEntries(
    formatter.formatToParts(instant).map((p) => [p.type, p.value]),
  );
}
export function date(value: string | null | undefined, withTime = false) {
  const p = parts(value);
  if (!p) return "Hali mavjud emas";
  const day = `${Number(p.day)} ${months[Number(p.month) - 1]} ${p.year}`;
  return withTime ? `${day}, ${p.hour}:${p.minute}` : day;
}
export function time(value: string | null | undefined) {
  const p = parts(value);
  return p ? `${p.hour}:${p.minute}` : "—";
}
