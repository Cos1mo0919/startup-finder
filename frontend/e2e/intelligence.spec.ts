import { test, expect } from "@playwright/test";

test("public navigation stays focused on projects", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Asosiy menyu" });
  await expect(navigation.getByRole("link")).toHaveCount(5);
  for (const label of ["Bosh sahifa", "Loyihalar", "Boshqa", "Arxiv", "Manbalar"]) {
    await expect(navigation.getByRole("link", { name: label })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "izlanish." })).toBeVisible();
  // Fixture is dated two hours ago, which may fall on the previous Tashkent day.
  await expect(page.getByRole("heading", { name: /^(Bugungi|So‘nggi) loyihalar$/ })).toBeVisible();
  await expect(page.locator(".intel-metrics a")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "Eng kuchli imkoniyatlar" })).toHaveCount(0);
  await page.goto("/boshqa");
  await expect(page.getByRole("heading", { name: "Boshqa" })).toBeVisible();
  await page.goto("/manbalar");
  await expect(page.getByRole("heading", { name: "Manbalar" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("HTTP 403");
  await page.goto("/arxiv?year=2022");
  await expect(page.getByRole("heading", { name: "Arxiv" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Yil" })).toHaveValue("2022");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("unknown country with Global scope appears in catalog", async ({ page, request }) => {
  const listing = await (await request.get("/api/projects?period=all")).json();
  const globalProject = { ...listing.items[0], country: "", scope: "Global" };
  await page.route("**/api/catalog/home", route => route.fulfill({ json: {
    total: 1, uzbekistan_total: 0, global_total: 1, github_total: 0, boshqa_total: 0, fresh_period: "today", top: [globalProject],
    uzbekistan: [], global: [globalProject], github: [], sectors: [],
  } }));
  await page.route("**/api/projects?*", route => route.fulfill({ json: {
    ...listing, total: 1, items: [globalProject],
  } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bugungi loyihalar" })).toBeVisible();
  await expect(page.getByText("Global ·", { exact: false }).first()).toBeVisible();
  await page.goto("/loyihalar?country=global");
  await expect(page.getByRole("link", { name: globalProject.name }).first()).toBeVisible();
});

test("GitHub source has its own catalog tab and home counter", async ({ page, request }) => {
  const listing = await (await request.get("/api/projects?period=all")).json();
  const project = { ...listing.items[0], country: "Uzbekistan", scope: "GitHub" };
  await page.route("**/api/catalog/home", route => route.fulfill({ json: {
    total: 1, uzbekistan_total: 0, global_total: 0, github_total: 1, boshqa_total: 0, fresh_period: "today",
    top: [project], uzbekistan: [], global: [], github: [project], sectors: [],
  } }));
  await page.route("**/api/projects?*", route => route.fulfill({ json: {
    ...listing, total: 1, items: [project],
  } }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: /1\s*GitHub/ })).toBeVisible();
  await page.goto("/loyihalar?country=github");
  await expect(page.getByRole("combobox", { name: "Bo‘lim" })).toHaveValue("github");
  await expect(page.getByRole("link", { name: project.name }).first()).toBeVisible();
});

test("empty fresh window links to archive and catalog offers year and section counts", async ({ page }) => {
  await page.route("**/api/catalog/home", route => route.fulfill({ json: {
    total: 2, uzbekistan_total: 1, global_total: 0, github_total: 0,
    boshqa_total: 1, fresh_period: "empty", top: [],
  } }));
  await page.route("**/api/catalog/facets", route => route.fulfill({ json: {
    total: 2, years: {"2025": 1, "2026": 1},
    sections: {Uzbekistan: 1, Global: 0, GitHub: 0, Boshqa: 1},
  } }));
  await page.goto("/");
  await expect(page.getByText("Hozircha yangi loyihalar yo‘q.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Arxivga o‘ting →" })).toHaveAttribute("href", "/arxiv");
  await page.goto("/loyihalar");
  await expect(page.getByRole("combobox", { name: "Yil" }).getByRole("option", { name: "2025 (1)" })).toHaveCount(1);
  await expect(page.getByRole("combobox", { name: "Bo‘lim" }).getByRole("option", { name: "Boshqa (1)" })).toHaveCount(1);
});

test("Boshqa card explains uncertain section without altering project text", async ({ page, request }) => {
  const listing = await (await request.get("/api/projects?period=all")).json();
  const project = { ...listing.items[0], scope: "Boshqa", country: "",
                    section_reason: "Manba va mamlakat aniqlanmadi." };
  await page.route("**/api/projects?*", route => route.fulfill({ json: {
    ...listing, total: 1, items: [project],
  } }));
  await page.goto("/boshqa");
  await expect(page.getByRole("heading", { name: "Boshqa" })).toBeVisible();
  await expect(page.getByText("AI aniqlay olmadi.")).toBeVisible();
  await expect(page.getByText("Manba va mamlakat aniqlanmadi.")).toBeVisible();
});

test("home falls back to So‘nggi loyihalar and catalog offers the So‘nggi paytda filter", async ({ page, request }) => {
  const listing = await (await request.get("/api/projects?period=all")).json();
  const project = listing.items[0];
  await page.route("**/api/catalog/home", route => route.fulfill({ json: {
    total: 1, uzbekistan_total: 1, global_total: 0, github_total: 0, boshqa_total: 0,
    fresh_period: "yesterday", fresh_day: "2026-10-19", top: [project] } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "So‘nggi loyihalar" })).toBeVisible();
  // No explanation about the search not having run yet.
  await expect(page.locator(".intel-projects")).not.toContainText("qidiruv");
  await expect(page.locator(".intel-projects")).not.toContainText("ko‘rsatilmoqda");
  await page.route("**/api/catalog/facets", route => route.fulfill({ json: {
    total: 3, years: {"2026": 3}, sections: {Uzbekistan: 3, Global: 0, GitHub: 0, Boshqa: 0},
    recent: { period: "last_week", start: "2026-10-12", end: "2026-10-18", total: 1 } } }));
  await page.route("**/api/projects?*", route =>
    route.fulfill({ json: { items: [project], total: 1, page: 1, page_size: 12 } }));
  await page.goto("/loyihalar");
  const period = page.getByRole("combobox", { name: "Davr" });
  await expect(period.getByRole("option", { name: "So‘nggi paytda (1)" })).toHaveCount(1);
  const recentRequest = page.waitForRequest(request =>
    request.url().includes("/api/projects?") && request.url().includes("period=recent"));
  await period.selectOption("recent");
  await recentRequest;
  await expect(page).toHaveURL(/period=recent/);
  await expect(page.getByText("O‘tgan hafta: 12 oktabr 2026 — 18 oktabr 2026")).toBeVisible();
  // The other filters stay available and combine with it.
  await expect(page.getByRole("combobox", { name: "Yil" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Bo‘lim" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Loyiha nomini qidirish" })).toBeVisible();
  await page.getByRole("combobox", { name: "Bo‘lim" }).selectOption("Uzbekistan");
  await expect(page).toHaveURL(/period=recent/);
  await expect(page).toHaveURL(/country=Uzbekistan/);
});
