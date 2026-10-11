import json

from backend.app.collectors.sources import Discovery
from backend.app.db import RegistrySource, SourceBlock
from backend.app.registry import activate_validated_sources, seed_registry


def test_directory_selector_keeps_only_repository_cards(settings):
    class Web:
        def get(self, url):
            return (b'<a href="/features">Features</a>'
                    b'<article class="Box-row"><h2><a href="/owner/tool">Tool</a></h2></article>'
                    b'<a href="/other/thing">Noise</a>', url)

    discovery = Discovery(settings, Web())
    links = discovery.page_links("https://github.com/trending",
        "https://github[.]com/[^/?]+/[^/?]+$", selector="article.Box-row h2 a[href]")
    assert [item["url"] for item in links] == ["https://github.com/owner/tool"]


def test_explicit_source_activation_keeps_blocked_source_disabled(settings, factory, tmp_path):
    path = tmp_path / "sources.json"
    seeds = [dict(id=id, name=id, url=url, source_type="startup_platform",
                  region="International", priority=4, check_frequency=180,
                  enabled=True, collection_method="direct_page", kind="unknown",
                  options={"link_pattern": "/products/"}) for id, url in (
                      ("product-hunt", "https://www.producthunt.com/"),
                      ("betalist", "https://betalist.com/"))]
    path.write_text(json.dumps(seeds))
    with factory.begin() as session:
        for seed in seeds:
            session.add(RegistrySource(id=seed["id"], name=seed["name"], url=seed["url"],
                                       enabled=False, collection_method="manual_config"))
        session.flush()
        session.add(SourceBlock(source_id="betalist", action="BLOCK", actor="admin", reason="operator"))
    assert activate_validated_sources(factory, path) == ["product-hunt"]
    with factory() as session:
        assert session.get(RegistrySource, "product-hunt").enabled
        assert not session.get(RegistrySource, "betalist").enabled
    # Ordinary seeding does not undo the operator's disabled setting.
    assert seed_registry(factory, path) == 0
    with factory() as session:
        assert not session.get(RegistrySource, "betalist").enabled
