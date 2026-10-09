import { test, expect } from "@playwright/test";

test("public navigation stays focused on projects", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Asosiy menyu" });
  await expect(navigation.getByRole("link")).toHaveCount(4);
  for (const label of ["Bosh sahifa", "Loyihalar", "Arxiv", "Manbalar"]) {
    await expect(navigation.getByRole("link", { name: label })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "izlanish." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tanlangan loyihalar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Eng kuchli imkoniyatlar" })).toHaveCount(0);
  await page.goto("/manbalar");
  await expect(page.getByRole("heading", { name: "Manbalar" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("HTTP 403");
  await page.goto("/arxiv?year=2022");
  await expect(page.getByRole("heading", { name: "Arxiv" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Yil" })).toHaveValue("2022");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
