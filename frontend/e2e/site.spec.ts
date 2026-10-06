import { test, expect } from "@playwright/test";

test("Uzbek feed, search, filters and project evidence", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Bugun O‘zbekistonda" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "uz");
  await expect(page.getByText("Rasm mavjud emas").first()).toBeVisible();
  await page.getByRole("link", { name: "Batafsil", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AgroKo‘mak" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tasdiqlangan faktlar" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "AI tahlili", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Manbani o‘qish" }),
  ).toHaveAttribute("href", "https://news.example/article");
  await page.screenshot({
    path: `test-results/detail-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "Loyihalar lentasiga" }).click();
  await page
    .getByRole("textbox", { name: "Loyihalarni qidirish" })
    .fill("no-such-project");
  await page.getByRole("button", { name: "Qidirish", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Mos loyiha topilmadi" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Loyihalarni qidirish" })
    .fill("Agro");
  await page.getByRole("button", { name: "Qidirish", exact: true }).click();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toBeVisible();
  await page.getByRole("combobox", { name: "Nashr yili" }).selectOption("2022");
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toHaveCount(0);
  await page.getByRole("button", { name: "Barchasi", exact: true }).click();
  await expect(page.getByRole("link", { name: "AgroKo‘mak" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("status and empty-state layouts are usable", async ({ page }, info) => {
  await page.goto("/status");
  await expect(
    page.getByRole("heading", { name: "Qidiruv holati", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Kalit kutilmoqda")).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "Ulangan xizmatlar" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.goto("/?period=all&q=missing");
  await expect(
    page.getByRole("heading", { name: "Mos loyiha topilmadi" }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/feed-${info.project.name}.png`,
    fullPage: true,
  });
});
