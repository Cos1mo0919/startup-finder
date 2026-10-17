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

test("admin daily budgets show usage and warnings without public exposure", async ({ page, request }) => {
  const response = await request.get("/api/admin/status", { headers: { "X-Admin-Key": "test-admin-key" } });
  expect(response.ok()).toBeTruthy();
  const status = await response.json();
  await page.route("**/api/admin/status", route => route.fulfill({ json: { ...status, free_daily: {
    day: "2026-10-14", timezone: "Asia/Tashkent", target: 20, published_today: 3,
    page_mode: "trial", candidate_budgets:{trial:{used:0,limits:[20,20]},daily:{used:8,limits:[80,120]}}, page_budgets: {trial: {used: 6, limits: [40,40], attempted: 20, refunded: 14}},
    found_24h: 12, published_24h: 3, usage_today: {"llm:gemini": 8}, usage_24h: {"llm:gemini": 9},
    limits: {"llm:gemini": [10,10]}, warnings: ["llm:gemini"],
    provider_quotas: {groq: {requests: 100, tokens: 80000, reported_tokens: 50000, unconfirmed_attempts: 3,
      limits: {requests: 500, tokens: 100000, rpm: 30, tpm: 8000}, warnings: ["tokens"],
      blocked_reason: "", timezone: "rolling_24h", reset_at: "2026-10-15T00:00:00Z"}},
    blocked_providers: {groq: "rate_limited"}, providers_enabled: {gemini: true, groq: true, openai: false},
    last_run: {id: 99, status: "completed", stop_reason: "daily_limit:llm:gemini", trial_evaluation:"partial",run_phases_ms:{initialization:100,discovery:200,processing:300,queue_selection:20,report:10,total:630},run_database:{sql_queries:12,commits:4,rollbacks:5,checkout_probes:1,elapsed_ms:200,by_component:{}},counts:{reached_llm:1,llm_validated:0,before_llm:2}, before_llm_reasons:{article_body_missing:2}, candidate_runs:[{candidate_id:"fixture",stage:"review_required",reason:"llm_unavailable",source:{name:"Fixture source",domain:"fixture.example",page_type:"project_page"},timings_ms:{robots:10,page_read:20,extraction:5,llm:30,pauses:0,lock_wait:1,total:70},database:{sql_queries:6,commits:2,rollbacks:3,checkout_probes:0,elapsed_ms:40,by_component:{quota_before_http:{sql_queries:2,elapsed_ms:10}}},provider_waits:[{provider:"groq",reason:"tpm_reserved_tokens",requested_seconds:6,skipped:false}],provider_attempts:[{provider:"gemini",outcome:"business_validation_failed",rule_code:"score_reason_length",http_status:200,elapsed_ms:10,finish_reason:"STOP"},{provider:"groq",outcome:"output_truncated",http_status:200,elapsed_ms:30,finish_reason:"length"}]}]},
  } } }));
  await page.goto("/admin");
  await page.getByRole("textbox", { name: "Admin kaliti" }).fill("test-admin-key");
  await page.getByRole("button", { name: "Kirish" }).click();
  const panel = page.locator("section").filter({has: page.getByRole("heading", {name: "Bepul kunlik ish"})});
  await expect(panel).toContainText("Nashr: 3/20");
  await expect(panel).toContainText("Sinov sahifa budjeti: 6 / 40");
  await expect(panel).toContainText("Sinov nomzod budjeti: 0 / 20");
  await expect(panel).toContainText("Oddiy nomzod budjeti: 8 / 120");
  await expect(panel).toContainText("8 / 10");
  await expect(panel).toContainText("LLM ga yetdi: 1");
  await expect(panel).toContainText("Sinov natijasi: partial");
  await expect(panel).toContainText("Jami SQL: 12");
  await panel.getByText("Fixture source · review_required · llm_unavailable").click();
  await expect(panel).toContainText("page_read: 20");
  await expect(panel).toContainText("SQL: 6");
  await expect(panel).toContainText("quota_before_http: SQL 2");
  await expect(panel).toContainText("tpm_reserved_tokens");
  await expect(panel).toContainText("score_reason_length");
  await expect(panel).toContainText("output_truncated · HTTP 200");
  await expect(panel.getByRole("alert").first()).toContainText("80%");
  await expect(panel).toContainText("Tokenlar: 80000 / 100000");
  await expect(panel.getByRole("alert").filter({hasText: "groq API"})).toContainText("80%");
  await expect(panel).toContainText("Kunlik limiti: Gemini");
  await expect(panel).toContainText("openai: o‘chirilgan");
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Bepul kunlik ish"})).toHaveCount(0);
});
