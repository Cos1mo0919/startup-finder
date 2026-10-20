import { test, expect } from "@playwright/test";
import { date, time } from "../src/utils";

// The "So‘nggi paytda" block depends on today's weekday; catalog tests here
// stub it so their card and link lookups stay deterministic.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/catalog/recent*", route => route.fulfill({ json: {
    period: "this_week", start: "2026-10-19", end: "2026-10-25", total: 0, items: [] } }));
});

test("Uzbek dates use explicit month names and Tashkent components", () => {
  expect(date("2026-03-10T00:00:00Z")).toBe("10 mart 2026");
  expect(date("2026-10-07T09:48:00Z", true)).toBe("7 oktabr 2026, 14:48");
  expect(date("2025-12-31T19:00:00Z", true)).toBe("1 yanvar 2026, 00:00");
  expect(time("2026-10-07T09:48:00Z")).toBe("14:48");
  for (const [month, name] of [
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
  ].entries()) {
    expect(
      date(`2026-${String(month + 1).padStart(2, "0")}-10T00:00:00Z`),
    ).toBe(`10 ${name} 2026`);
  }
  expect(date(null)).toBe("Hali mavjud emas");
  expect(date("invalid")).toBe("Hali mavjud emas");
  expect(time(undefined)).toBe("—");
});

test("feed, detail and status render Uzbek month names in the browser", async ({
  page,
}) => {
  await page.goto("/loyihalar");
  await expect(page.locator(".card-date").first()).toHaveText(
    /\d{1,2} [a-z]+ 20\d{2}/,
  );
  await page.getByRole("link", { name: "AgroKo‘mak" }).click();
  await expect(page.getByRole("heading", { name: "AgroKo‘mak" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/20\d{2} M\d{2}/);
  await page.route("**/api/admin/status", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.last_run = {
      id: 1,
      status: "completed",
      started_at: "2026-10-07T09:48:00Z",
      finished_at: "2026-10-07T09:49:00Z",
      counts: {},
      errors: [],
      duration_seconds: 60,
      details: {
        mode: "archive",
        window: ["2022-01-01", "2026-09-30"],
        summary: {
          source_errors: 0,
          parser_errors: 0,
          event_errors: 0,
          configuration_errors: 0,
          ai_unavailable: true,
          pending: 0,
        },
      },
    };
    body.runs = [body.last_run];
    await route.fulfill({ response, json: body });
  });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Bunday sahifa mavjud emas" })).toBeVisible();
  await page.keyboard.type("test-admin-key");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Qidiruv holati" }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator("body")).toContainText("7 oktabr 2026, 14:48");
  await expect(page.locator("body")).toContainText(
    "1 yanvar 2022 — 30 sentabr 2026",
  );
  await expect(page.locator("body")).not.toContainText(/20\d{2} M\d{2}/);
});
