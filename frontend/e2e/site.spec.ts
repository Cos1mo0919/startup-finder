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
  await page.getByRole("combobox", { name: "Bo‘lim" }).selectOption("global");
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("catalog cards shorten presentation while detail retains source description", async ({ page, request }) => {
  const original = await (await request.get("/api/projects?period=all")).json();
  const longDescription = Array.from({ length: 45 }, (_, i) => `tavsif${i}`).join(" ");
  const item = { ...original.items[0], short_description: longDescription,
                 summary_uz: longDescription, problem_statement: longDescription };
  await page.route("**/api/projects?*", route => route.fulfill({ json: { ...original, items: [item], total: 1 } }));
  await page.goto("/loyihalar");
  const card = page.locator(".project-card").first();
  await expect(card.locator(".summary")).toContainText("tavsif19");
  await expect(card.locator(".summary")).not.toContainText("tavsif20");
  await expect(card.locator(".card-problem")).not.toContainText("tavsif24");
  await expect(card.getByRole("link", { name: "Batafsil" })).toBeVisible();
  await page.route("**/api/projects/*", route => route.fulfill({ json: item }));
  await card.getByRole("link", { name: "Batafsil" }).click();
  await expect(page.locator("body")).toContainText("tavsif44");
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
