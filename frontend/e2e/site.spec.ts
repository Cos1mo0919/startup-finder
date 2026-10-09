import { test, expect } from "@playwright/test";

test("project catalog and detail show the product before optional analysis", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/loyihalar");
  await expect(page.getByRole("heading", { name: "Loyihalar", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "uz");
  await expect(page.locator(".project-card .summary").first()).toBeVisible();
  await expect(page.locator(".project-card .card-evidence").first()).toContainText("Baholanmagan");
  await expect(page.locator(".project-card")).not.toContainText("Kutilmoqda");
  await page.getByRole("link", { name: "AgroKo‘mak" }).click();
  await expect(page.getByRole("heading", { name: "Loyiha nima qiladi?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Asl manbalar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tasdiqlangan asosiy faktlar" })).toBeVisible();
  await page.screenshot({ path: `test-results/detail-${info.project.name}.png`, fullPage: true });
  await page.goto("/loyihalar");
  await page.getByRole("textbox", { name: "Loyiha nomini qidirish" }).fill("unmatched-name");
  await page.getByRole("button", { name: "Qidirish" }).click();
  await expect(page.getByText("Mos loyiha topilmadi.")).toBeVisible();
  await page.getByRole("textbox", { name: "Loyiha nomini qidirish" }).fill("Agro");
  await page.getByRole("button", { name: "Qidirish" }).click();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toBeVisible();
  await page.getByRole("button", { name: "Global" }).click();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("admin access requires a key and keeps technical pages separate", async ({ page }) => {
  await page.goto("/muammolar");
  await expect(page).toHaveURL(/\/admin$/);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Egasi uchun boshqaruv" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Asosiy menyu" }).getByRole("link", { name: "Holat" })).toHaveCount(0);
  await page.getByRole("textbox", { name: "Admin kaliti" }).fill("test-admin-key");
  await page.getByRole("button", { name: "Kirish" }).click();
  await expect(page.getByRole("heading", { name: "Qidiruv holati" })).toBeVisible();
  await page.getByRole("link", { name: "Ko‘rib chiqish" }).click();
  await expect(page.getByRole("heading", { name: "Ko‘rib chiqish navbati" })).toBeVisible();
  await page.getByRole("link", { name: "Manbalar samarasi" }).click();
  await expect(page.getByRole("heading", { name: "Manbalar samarasi" })).toBeVisible();
  await page.getByRole("navigation", { name: "Admin menyusi" }).getByRole("link", { name: "Muammolar" }).click();
  await expect(page.getByRole("heading", { name: "Muammolar" })).toBeVisible();
  await page.getByRole("navigation", { name: "Admin menyusi" }).getByRole("link", { name: "Signallar" }).click();
  await expect(page.getByRole("heading", { name: "Signallar" })).toBeVisible();
});
